from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from difflib import SequenceMatcher
from hashlib import sha256
from io import BytesIO
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.inventory import InventoryItem, InventoryItemLocation
from app.models.receipts import Receipt, ReceiptItem
from app.models.stock_mutations import StockMutationRequest
from app.schemas.receipts import InvoiceReceiptCommitRequest, InvoiceReceiptReversalRequest
from app.schemas.woocommerce import WooStockSyncRequest
from app.services.bulk_receiving import commit_bulk_receipt, next_bulk_receipt_number, resolve_receiving_item
from app.services.location_inventory import adjust_location_stock, create_audit_event, find_item_location, lock_inventory_stock, lock_stock_mutation_scope, to_decimal
from app.services.receiving import receipt_to_detail
from app.services.stock_mutation_guard import begin_stock_mutation, complete_stock_mutation, mutation_request_hash, validate_existing_mutation
from app.services.woocommerce_stock_sync_jobs import create_stock_sync_job, stock_sync_job_read

PACK_SIZE = re.compile(r"(?:^|\s)(\d{1,3})\s*(?:/|x|×)\s*\d", re.IGNORECASE)
UPC_VALUE = re.compile(r"(?<!\d)(\d{8,14})(?!\d)")
PRICE_VALUE = re.compile(r"\$?[\d,]+\.\d{2}")
DATE_VALUE = re.compile(r"\b([A-Z][a-z]{2,8}\s+\d{1,2},\s+\d{4})\b")
INVOICE_VALUE = re.compile(r"\bIN\d{5,}\b", re.IGNORECASE)
GENERIC_INVOICE_VALUE = re.compile(r"\b(?:invoice|inv)\s*(?:number|no\.?|#)?\s*[:#-]?\s*([A-Z0-9-]*\d[A-Z0-9-]*)", re.IGNORECASE)
NUMERIC_DATE_VALUE = re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
UOM_VALUE = re.compile(r"\b(EA|EACH|CS|CASE|CASES)\b", re.IGNORECASE)
PLAIN_NUMBER = re.compile(r"(?<![\w./-])\d+(?:\.\d+)?(?![\w./-])")
PRODUCT_SIZE = re.compile(r"\d+(?:\.\d+)?\s*(?:kg|g|lb|lbs|oz|ml|l)\b", re.IGNORECASE)
DOCUMENT_MARKER = "invoice-sha256:"
CONTINUATION_STOPS = (
    "jf dry",
    "invoice continued",
    "order subtotal",
    "royal canin outdate",
    "***please",
    "tax summary",
    "sold to:",
    "ship to:",
)


def _money(value: str | float | Decimal) -> Decimal:
    return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalized_name(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).split())


def _name_similarity(invoice_name: str, item: InventoryItem) -> float:
    return round(SequenceMatcher(None, _normalized_name(invoice_name), _normalized_name(item.woo_name or item.description)).ratio(), 2)


def _parse_quantity_first_product_line(raw: str, line_number: int) -> dict[str, Any] | None:
    upc_match = UPC_VALUE.search(raw)
    if upc_match is None:
        return None
    prefix_tokens = raw[: upc_match.start()].split()
    if not prefix_tokens or re.fullmatch(r"\d+(?:\.\d+)?", prefix_tokens[0]) is None:
        return None
    shipped = prefix_tokens[0]
    cursor = 1
    backordered = "0"
    if cursor < len(prefix_tokens) and re.fullmatch(r"\d+(?:\.\d+)?", prefix_tokens[cursor]):
        backordered = prefix_tokens[cursor]
        cursor += 1
    item_number = " ".join(prefix_tokens[cursor:])
    suffix = raw[upc_match.end() :].strip()
    prices = list(PRICE_VALUE.finditer(suffix))
    if not prices:
        return None
    description = suffix[: prices[0].start()].strip()
    uom_match = re.search(r"\b(EA|EACH|CS|CASE|CASES)\s*$", description, re.IGNORECASE)
    uom_inferred = uom_match is None
    if uom_match:
        uom = "CS" if uom_match.group(1).upper() in {"CS", "CASE", "CASES"} else "EA"
        description = description[: uom_match.start()].strip()
    else:
        uom = "CS" if PACK_SIZE.search(description) else "EA"
    price_values = [_money(match.group(0)) for match in prices]
    net_price = price_values[-2] if len(price_values) >= 2 else price_values[-1]
    wholesale = price_values[-3] if len(price_values) >= 3 else net_price
    return {
        "line_number": line_number,
        "shipped_quantity": float(shipped),
        "backordered_quantity": float(backordered),
        "supplier_item_number": item_number,
        "upc": upc_match.group(1),
        "invoice_description": " ".join(description.split()),
        "uom": uom,
        "uom_inferred": uom_inferred,
        "wholesale_price": float(wholesale),
        "net_price": float(net_price),
        "extended_price": float(price_values[-1]),
        "extraction_warnings": [],
    }


def _generic_quantity(raw: str, upc_match: re.Match[str], prices: list[re.Match[str]], uom_match: re.Match[str] | None) -> re.Match[str] | None:
    first_price_start = prices[0].start() if prices else len(raw)
    candidates = [
        match
        for match in PLAIN_NUMBER.finditer(raw)
        if match.start() >= upc_match.end()
        and match.end() <= first_price_start
        and PRODUCT_SIZE.fullmatch(raw[match.start() : min(first_price_start, match.end() + 6)].strip()) is None
    ]
    if uom_match and candidates:
        before_uom = [match for match in candidates if match.end() <= uom_match.start()]
        if before_uom:
            return before_uom[-1]
        after_uom = [match for match in candidates if match.start() >= uom_match.end()]
        if after_uom:
            return after_uom[0]
    return candidates[0] if candidates else None


def _parse_generic_product_line(raw: str, line_number: int) -> dict[str, Any] | None:
    upc_matches = list(UPC_VALUE.finditer(raw))
    prices = list(PRICE_VALUE.finditer(raw))
    if not upc_matches or not prices:
        return None
    upc_match = max(upc_matches, key=lambda match: (len(match.group(1)) >= 12, match.start()))
    uom_match = UOM_VALUE.search(raw)
    quantity_match = _generic_quantity(raw, upc_match, prices, uom_match)
    if quantity_match is None:
        return None
    shipped = _money(quantity_match.group(0))
    if shipped < 0:
        return None

    price_values = [_money(match.group(0)) for match in prices]
    extended = price_values[-1]
    unit_price = None
    if shipped > 0 and len(price_values) >= 2:
        for candidate in reversed(price_values[:-1]):
            if abs((candidate * shipped) - extended) <= Decimal("0.02"):
                unit_price = candidate
                break
    net_price = unit_price or (price_values[-2] if len(price_values) >= 2 else price_values[-1])

    removable = [upc_match, quantity_match, *prices]
    if uom_match:
        removable.append(uom_match)
    description = raw
    for match in sorted(removable, key=lambda candidate: candidate.start(), reverse=True):
        description = f"{description[:match.start()]} {description[match.end():]}"
    description = " ".join(description.split()).strip(" -|")
    if not description or not re.search(r"[A-Za-z]", description):
        return None
    warnings = ["A nonstandard invoice row layout was detected; verify the extracted quantity and price."]
    if len(price_values) == 1:
        warnings.append("Only one price was found; verify that it is the unit net price.")
    return {
        "line_number": line_number,
        "shipped_quantity": float(shipped),
        "backordered_quantity": 0.0,
        "supplier_item_number": "",
        "upc": upc_match.group(1),
        "invoice_description": description,
        "uom": "CS" if uom_match and uom_match.group(1).upper() in {"CS", "CASE", "CASES"} else "EA",
        "uom_inferred": uom_match is None,
        "wholesale_price": float(net_price),
        "net_price": float(net_price),
        "extended_price": float(extended),
        "extraction_warnings": warnings,
    }


def _parse_product_line(raw: str, line_number: int) -> dict[str, Any] | None:
    return _parse_quantity_first_product_line(raw, line_number) or _parse_generic_product_line(raw, line_number)


def _invoice_date(text: str) -> str | None:
    date_match = DATE_VALUE.search(text)
    candidates = [(date_match.group(1), ("%b %d, %Y", "%B %d, %Y"))] if date_match else []
    numeric_match = NUMERIC_DATE_VALUE.search(text)
    if numeric_match:
        candidates.append((numeric_match.group(1), ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y")))
    for value, formats in candidates:
        for date_format in formats:
            try:
                return datetime.strptime(value, date_format).date().isoformat()
            except ValueError:
                continue
    return None


def _supplier_name(text: str) -> str:
    labeled = re.search(r"^[ \t]*(?:supplier|vendor|from)[ \t]*:[ \t]*(.+?)[ \t]*$", text, re.MULTILINE | re.IGNORECASE)
    if labeled:
        return labeled.group(1).strip()
    heading = re.search(r"^[ \t]*([^\r\n]+?)[ \t]+Invoice(?:[ \t]+|$)", text, re.MULTILINE | re.IGNORECASE)
    if heading:
        return heading.group(1).strip()
    for raw in text.splitlines()[:12]:
        candidate = raw.strip()
        lowered = candidate.casefold()
        if (
            2 <= len(candidate) <= 120
            and re.search(r"[a-z]", candidate, re.IGNORECASE)
            and not any(token in lowered for token in ("invoice", "date", "page", "sold to", "ship to", "quantity", "description", "address"))
            and not UPC_VALUE.search(candidate)
            and not PRICE_VALUE.search(candidate)
        ):
            return candidate
    return "Unknown supplier"


def parse_invoice_text(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    parsed: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in lines:
        product_line = _parse_product_line(raw, len(parsed) + 1)
        if product_line:
            current = product_line
            parsed.append(current)
            continue
        stripped = raw.strip()
        if current and stripped and len(raw) - len(raw.lstrip()) >= 10:
            lowered = stripped.casefold()
            if lowered.startswith(CONTINUATION_STOPS) or "quantity qty" in lowered or "invoice number" in lowered:
                current = None
            elif not re.search(r"\b(?:phone|fax|gst|amount due|damage/outdate|misc\. charges)\b", lowered):
                current["invoice_description"] += f" {stripped}"

    invoice_match = INVOICE_VALUE.search(text)
    if invoice_match is None:
        invoice_match = GENERIC_INVOICE_VALUE.search(text)
    return {
        "supplier": _supplier_name(text),
        "invoice_number": (invoice_match.group(0) if invoice_match and invoice_match.lastindex is None else invoice_match.group(1)) if invoice_match else "",
        "invoice_date": _invoice_date(text),
        "lines": parsed,
    }


def extract_invoice_pdf(document: bytes) -> tuple[str, dict[str, Any]]:
    if not document:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
    if len(document) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Invoice PDFs must be 10 MB or smaller.")
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(document)) as pdf:
            text = "\n".join(page.extract_text(layout=True) or "" for page in pdf.pages)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The invoice PDF could not be read.") from exc
    parsed = parse_invoice_text(text)
    if not parsed["invoice_number"]:
        raise HTTPException(status_code=400, detail="No invoice number was detected. This invoice needs manual receiving.")
    if not parsed["lines"]:
        raise HTTPException(status_code=400, detail="No invoice product rows were detected. This invoice needs manual receiving.")
    return sha256(document).hexdigest(), parsed


def _duplicate_receipts(db: Session, supplier: str, invoice_number: str, document_hash: str) -> list[Receipt]:
    marker = f"[{DOCUMENT_MARKER}{document_hash}]"
    return list(
        db.scalars(
            select(Receipt)
            .where(
                Receipt.receipt_type == "invoice",
                Receipt.status.in_(("committed", "reversed")),
                or_(
                    (func.lower(Receipt.client) == supplier.casefold()) & (Receipt.reference_number == invoice_number),
                    Receipt.notes.contains(marker),
                ),
            )
            .order_by(Receipt.created_at.desc())
        ).all()
    )


def preview_invoice_pdf(document: bytes, db: Session, *, warehouse: str, inventory_location: str) -> dict[str, Any]:
    document_hash, invoice = extract_invoice_pdf(document)
    upc_counts: dict[str, int] = {}
    for row in invoice["lines"]:
        upc_counts[row["upc"]] = upc_counts.get(row["upc"], 0) + 1

    rows = []
    for row in invoice["lines"]:
        shipped = to_decimal(row["shipped_quantity"])
        reasons: list[str] = list(row.get("extraction_warnings") or [])
        item, match_error = resolve_receiving_item(db, {"barcode": row["upc"]})
        pack_match = PACK_SIZE.search(row["invoice_description"])
        pack_multiplier = int(pack_match.group(1)) if pack_match else 1
        if row["uom"] == "CS":
            reasons.append(f"Case converted to {pack_multiplier} individual pieces; verify the pack size.")
            if pack_match is None:
                reasons.append("No pack size was detected for this case.")
        if row.get("uom_inferred"):
            reasons.append(f"Unit of measure was not labeled; {row['uom']} was inferred from the description.")
        if upc_counts[row["upc"]] > 1:
            reasons.append("This UPC appears more than once on the invoice.")

        status = "ready"
        similarity = None
        if shipped <= 0:
            status = "excluded"
            reasons = ["Not shipped; excluded from receiving."]
        elif item is None:
            status = "unmatched"
            reasons = [match_error or "UPC was not found in Pongo OS."]
        else:
            similarity = _name_similarity(row["invoice_description"], item)
            if similarity < 0.3:
                reasons.append("UPC matched, but the invoice and Pongo product names differ; verify the product.")
            if reasons:
                status = "review"

        quantity_pieces = shipped * pack_multiplier
        unit_cost = _money(row["net_price"]) / Decimal(pack_multiplier)
        item_location = find_item_location(db, item.id, warehouse, inventory_location) if item and inventory_location else None
        old_location_stock = to_decimal(item_location.in_stock) if item_location else Decimal("0")
        old_item_stock = to_decimal(item.in_stock) if item else Decimal("0")
        rows.append(
            {
                **row,
                "status": status,
                "selected": status in {"ready", "review"},
                "review_required": status == "review",
                "human_verified": False,
                "reasons": reasons,
                "pack_multiplier": pack_multiplier,
                "quantity_pieces": float(quantity_pieces),
                "unit_cost": float(unit_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "name_similarity": similarity,
                "warehouse": warehouse,
                "inventory_location": inventory_location,
                "item": {
                    "id": item.id,
                    "sku": item.sku,
                    "barcode": item.barcode,
                    "description": item.woo_name or item.description,
                    "old_item_stock": float(old_item_stock),
                    "new_item_stock": float(old_item_stock + quantity_pieces),
                    "old_location_stock": float(old_location_stock),
                    "new_location_stock": float(old_location_stock + quantity_pieces),
                }
                if item
                else None,
            }
        )

    duplicates = _duplicate_receipts(db, invoice["supplier"], invoice["invoice_number"], document_hash)
    counts = {status: sum(row["status"] == status for row in rows) for status in ("ready", "review", "unmatched", "excluded")}
    return {
        **invoice,
        "document_sha256": document_hash,
        "warehouse": warehouse,
        "inventory_location": inventory_location,
        "duplicate": bool(duplicates),
        "duplicate_receipts": [
            {"id": receipt.id, "receipt_number": receipt.receipt_number, "status": receipt.status, "received_at": receipt.received_at}
            for receipt in duplicates
        ],
        "counts": counts,
        "total_pieces": float(sum((to_decimal(row["quantity_pieces"]) for row in rows if row["selected"]), Decimal("0"))),
        "lines": rows,
    }


def _queue_stock_sync(db: Session, item_ids: list[int], key: str, actor: str) -> dict[str, Any]:
    job = create_stock_sync_job(
        db,
        WooStockSyncRequest(force=True, requested_by=actor, idempotency_key=key[:120], item_ids=item_ids),
    )
    return stock_sync_job_read(job).model_dump(mode="json")


def _verified_invoice(payload: InvoiceReceiptCommitRequest, document: bytes) -> dict[str, Any]:
    document_hash, invoice = extract_invoice_pdf(document)
    if document_hash != payload.document_sha256:
        raise HTTPException(status_code=409, detail="The committed PDF does not match the reviewed invoice.")
    if invoice["invoice_number"].casefold() != payload.invoice_number.casefold():
        raise HTTPException(status_code=409, detail="The invoice number changed after preview. Review the PDF again.")
    if _normalized_name(invoice["supplier"]) != _normalized_name(payload.supplier):
        raise HTTPException(status_code=409, detail="The supplier changed after preview. Review the PDF again.")
    if invoice["invoice_date"] != (payload.invoice_date.isoformat() if payload.invoice_date else None):
        raise HTTPException(status_code=409, detail="The invoice date changed after preview. Review the PDF again.")

    source_lines = {line["line_number"]: line for line in invoice["lines"]}
    seen_lines: set[int] = set()
    for index, line in enumerate(payload.lines, start=1):
        source = source_lines.get(line.source_line_number)
        if source is None or line.source_line_number in seen_lines:
            raise HTTPException(status_code=400, detail=f"Line {index} does not identify one unique row in the reviewed PDF.")
        seen_lines.add(line.source_line_number)
        immutable_matches = (
            source["upc"] == line.upc
            and _normalized_name(source["invoice_description"]) == _normalized_name(line.invoice_description)
            and source["uom"].upper() == line.uom.upper()
            and to_decimal(source["shipped_quantity"]) == to_decimal(line.shipped_quantity)
            and _money(source["net_price"]) == _money(line.net_price)
        )
        if not immutable_matches:
            raise HTTPException(status_code=409, detail=f"Line {index} changed after PDF review. Upload and review the invoice again.")
    return invoice


def _attach_stock_sync(
    db: Session,
    result: dict[str, Any],
    *,
    requested: bool,
    item_ids: list[int],
    key: str,
    actor: str,
    failure_message: str,
) -> dict[str, Any]:
    result = dict(result)
    result["woocommerce_sync"] = None
    result["woocommerce_sync_requested"] = requested
    if requested:
        try:
            result["woocommerce_sync"] = _queue_stock_sync(db, item_ids, key, actor)
        except Exception as exc:
            db.rollback()
            result.setdefault("warnings", []).append(f"{failure_message}: {exc}")
    return result


def commit_invoice_receipt(payload: InvoiceReceiptCommitRequest, document: bytes, db: Session, actor: str) -> dict[str, Any]:
    if payload.duplicate_override and not (payload.override_reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required to override the duplicate invoice warning.")
    _verified_invoice(payload, document)
    bulk_lines = []
    upc_counts = {line.upc: sum(candidate.upc == line.upc for candidate in payload.lines) for line in payload.lines}
    for index, line in enumerate(payload.lines, start=1):
        item, match_error = resolve_receiving_item(db, {"item_id": line.item_id, "barcode": line.upc})
        if item is None:
            raise HTTPException(status_code=400, detail=f"Line {index}: {match_error or 'UPC no longer matches a Pongo item.'}")
        expected_pieces = to_decimal(line.shipped_quantity) * line.pack_multiplier
        manually_adjusted = to_decimal(line.quantity_pieces) != expected_pieces
        expected_unit_cost = (_money(line.net_price) / Decimal(line.pack_multiplier)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cost_adjusted = _money(line.unit_cost) != expected_unit_cost
        server_review_required = (
            line.review_required
            or line.uom.upper() == "CS"
            or manually_adjusted
            or cost_adjusted
            or upc_counts[line.upc] > 1
            or _name_similarity(line.invoice_description, item) < 0.3
        )
        if server_review_required and not line.human_verified:
            raise HTTPException(status_code=400, detail=f"Line {index} requires staff verification before receiving.")
        bulk_lines.append(
            {
                "item_id": item.id,
                "barcode": line.upc,
                "scan_input": line.upc,
                "inventory_location": line.inventory_location,
                "quantity": line.quantity_pieces,
                "unit_cost": line.unit_cost,
                "notes": line.notes or f"Invoice: {line.invoice_description}; {line.shipped_quantity:g} {line.uom} × {line.pack_multiplier} = {line.quantity_pieces:g} pieces.",
            }
        )

    notes = [f"[{DOCUMENT_MARKER}{payload.document_sha256}]", "Received from reviewed invoice PDF."]
    if payload.duplicate_override:
        notes.append(f"Duplicate override: {payload.override_reason.strip()}")
    bulk_payload = {
        "idempotency_key": payload.idempotency_key,
        "mutation_type": "invoice_receipt",
        "receipt_type": "invoice",
        "reference_type": "invoice_receipt",
        "source": "invoice_upload",
        "client": payload.supplier,
        "warehouse": payload.warehouse,
        "reference_number": payload.invoice_number,
        "receipt_date": payload.invoice_date.isoformat() if payload.invoice_date else None,
        "notes": " ".join(notes),
        "created_by": actor,
        "lines": bulk_lines,
    }
    # Serialize the duplicate check with every stock mutation in production.
    lock_stock_mutation_scope(db)
    existing_mutation = db.scalar(
        select(StockMutationRequest).where(
            StockMutationRequest.operation == "invoice_receipt",
            StockMutationRequest.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_mutation is not None:
        _, replay = validate_existing_mutation(existing_mutation, mutation_request_hash(bulk_payload))
        result = replay
    else:
        duplicates = _duplicate_receipts(db, payload.supplier, payload.invoice_number, payload.document_sha256)
        if duplicates and not payload.duplicate_override:
            raise HTTPException(status_code=409, detail="This supplier invoice was already received. Enable duplicate override and provide a reason only if it is a separate delivery.")
        result = commit_bulk_receipt(bulk_payload, db)
    result.setdefault("receipt_id", result.get("id"))
    return _attach_stock_sync(
        db,
        result,
        requested=payload.sync_woocommerce,
        item_ids=[line.item_id for line in payload.lines],
        key=f"invoice-receipt-{result['receipt_id']}",
        actor=actor,
        failure_message="Stock was received locally, but WooCommerce sync could not be queued",
    )


def _receipt_cost_changes(receipt: Receipt, db: Session) -> dict[int, dict[str, Any]]:
    changes: dict[int, dict[str, Any]] = {}
    for line in sorted(receipt.items, key=lambda candidate: candidate.id):
        if line.inventory_item_id is None:
            continue
        change = changes.setdefault(
            line.inventory_item_id,
            {
                "item_id": line.inventory_item_id,
                "inventory_item_location_id": line.inventory_item_location_id,
                "previous_unit_cost": line.previous_unit_cost,
                "received_unit_cost": line.unit_cost,
            },
        )
        change["received_unit_cost"] = line.unit_cost
    for item_id, change in changes.items():
        item = db.get(InventoryItem, item_id)
        previous = to_decimal(change["previous_unit_cost"]) if change["previous_unit_cost"] is not None else None
        received = to_decimal(change["received_unit_cost"]) if change["received_unit_cost"] is not None else None
        current = to_decimal(item.unit_cost) if item else None
        errors = []
        if previous is None:
            errors.append("The pre-receipt unit cost was not recorded, so a complete reversal is unavailable.")
        elif item is None:
            errors.append("The product no longer exists.")
        elif received is not None and previous != received and current != received:
            errors.append("Unit cost changed after this receipt; restoring the older cost would overwrite a later change.")
        change.update(
            {
                "previous_unit_cost": float(previous) if previous is not None else None,
                "received_unit_cost": float(received) if received is not None else None,
                "current_unit_cost": float(current) if current is not None else None,
                "will_restore": previous is not None and received is not None and previous != received,
                "errors": errors,
            }
        )
    return changes


def invoice_reversal_preview(receipt_id: int, db: Session) -> dict[str, Any]:
    receipt = db.scalars(select(Receipt).where(Receipt.id == receipt_id).options(selectinload(Receipt.items))).one_or_none()
    if receipt is None or receipt.receipt_type != "invoice":
        raise HTTPException(status_code=404, detail="Invoice receipt not found.")
    if receipt.status != "committed":
        raise HTTPException(status_code=409, detail="Only a committed invoice receipt can be reverted, and it can be reverted only once.")
    cost_changes = _receipt_cost_changes(receipt, db)
    lines = []
    for receipt_line in receipt.items:
        item = db.get(InventoryItem, receipt_line.inventory_item_id)
        row = db.get(InventoryItemLocation, receipt_line.inventory_item_location_id)
        quantity = to_decimal(receipt_line.quantity_received or receipt_line.quantity)
        errors = []
        if item is None or row is None:
            errors.append("The original item or location no longer exists.")
        current = to_decimal(row.in_stock) if row else Decimal("0")
        allocated = to_decimal(row.allocated) if row else Decimal("0")
        after = current - quantity
        if row and after < 0:
            errors.append("Current stock is lower than the quantity originally received.")
        if row and after < allocated:
            errors.append("Reverting would reduce stock below allocated quantity.")
        errors.extend(cost_changes.get(receipt_line.inventory_item_id, {}).get("errors", []))
        lines.append(
            {
                "receipt_item_id": receipt_line.id,
                "item_id": receipt_line.inventory_item_id,
                "sku": receipt_line.sku,
                "description": receipt_line.description,
                "inventory_location": receipt_line.inventory_location_name,
                "quantity_to_remove": float(quantity),
                "current_stock": float(current),
                "allocated": float(allocated),
                "stock_after_reversal": float(after),
                "errors": errors,
            }
        )
    return {
        "receipt_id": receipt.id,
        "receipt_number": receipt.receipt_number,
        "invoice_number": receipt.reference_number,
        "supplier": receipt.client,
        "can_revert": bool(lines) and not any(line["errors"] for line in lines),
        "cost_changes": list(cost_changes.values()),
        "lines": lines,
    }


def revert_invoice_receipt(receipt_id: int, payload: InvoiceReceiptReversalRequest, db: Session, actor: str) -> dict[str, Any]:
    mutation, replay = begin_stock_mutation(db, "invoice_receipt_reversal", payload.idempotency_key, {"receipt_id": receipt_id, **payload.model_dump()})
    if replay is not None:
        original = db.scalars(select(Receipt).where(Receipt.id == receipt_id).options(selectinload(Receipt.items))).one_or_none()
        item_ids = [line.inventory_item_id for line in original.items if line.inventory_item_id] if original else []
        return _attach_stock_sync(
            db,
            replay,
            requested=payload.sync_woocommerce,
            item_ids=item_ids,
            key=f"invoice-reversal-{receipt_id}",
            actor=actor,
            failure_message="Stock was reverted locally, but WooCommerce sync could not be queued",
        )
    original = db.scalars(select(Receipt).where(Receipt.id == receipt_id).options(selectinload(Receipt.items)).with_for_update()).one_or_none()
    if original is None or original.receipt_type != "invoice":
        raise HTTPException(status_code=404, detail="Invoice receipt not found.")
    lock_inventory_stock(db, {line.inventory_item_id for line in original.items if line.inventory_item_id})
    preview = invoice_reversal_preview(receipt_id, db)
    if not preview["can_revert"]:
        raise HTTPException(status_code=409, detail=preview)

    now = datetime.now(timezone.utc)
    reversal = Receipt(
        receipt_number=next_bulk_receipt_number(db, now),
        receipt_type="invoice_reversal",
        status="committed",
        source="invoice_reversal",
        client=original.client,
        warehouse=original.warehouse,
        reference_number=original.reference_number,
        created_by=actor,
        received_by=actor,
        received_date=now.date(),
        received_at=now,
        committed_at=now,
        notes=f"Reversal of {original.receipt_number}. Reason: {payload.reason.strip()}",
    )
    db.add(reversal)
    db.flush()
    item_ids = []
    for source_line in original.items:
        item = db.get(InventoryItem, source_line.inventory_item_id)
        row = db.get(InventoryItemLocation, source_line.inventory_item_location_id)
        quantity = to_decimal(source_line.quantity_received or source_line.quantity)
        change = adjust_location_stock(
            db,
            item,
            row,
            -quantity,
            adjustment_type="correction",
            reason=payload.reason,
            reference_number=reversal.receipt_number,
            reference_type="invoice_receipt_reversal",
            reference_id=reversal.id,
            notes=f"Reversal of {original.receipt_number}",
            created_by=actor,
        )
        db.add(
            ReceiptItem(
                receipt_id=reversal.id,
                inventory_item_id=item.id,
                inventory_location_id=row.location_id,
                inventory_item_location_id=row.id,
                line_status="reversed",
                scan_input=source_line.scan_input,
                sku=item.sku,
                category=item.category,
                description=item.description,
                quantity=quantity,
                quantity_received=quantity,
                uom=item.unit_of_measurement,
                unit_cost=source_line.unit_cost,
                previous_unit_cost=source_line.unit_cost,
                unit_cost_total=source_line.unit_cost_total,
                brand=item.brand,
                client=item.client,
                warehouse=row.warehouse,
                inventory_location_name=row.inventory_location,
                default_location=item.default_location,
                received_date=now.date(),
                po_or_receipt_number=reversal.receipt_number,
                name=item.description,
                notes=f"Removed from {float(change.old_location_stock):g} to {float(change.new_location_stock):g}; original {original.receipt_number}.",
            )
        )
        item_ids.append(item.id)

    restored_unit_costs = 0
    for cost_change in preview["cost_changes"]:
        if not cost_change["will_restore"]:
            continue
        item = db.get(InventoryItem, cost_change["item_id"])
        row = db.get(InventoryItemLocation, cost_change["inventory_item_location_id"])
        previous_cost = to_decimal(cost_change["previous_unit_cost"])
        current_cost = to_decimal(item.unit_cost)
        item.unit_cost = previous_cost
        create_audit_event(
            db,
            item,
            row,
            "receiving_unit_cost_reversal",
            Decimal("0"),
            reversal.receipt_number,
            "invoice_receipt_reversal",
            reversal.id,
            f"Unit cost restored from {current_cost} to {previous_cost}; reversal of {original.receipt_number}.",
            actor,
        )
        restored_unit_costs += 1

    original.status = "reversed"
    original.cancelled_at = now
    original.notes = f"{original.notes or ''}\nReverted by {actor}: {payload.reason.strip()}".strip()
    db.flush()
    reversal = db.scalars(select(Receipt).where(Receipt.id == reversal.id).options(selectinload(Receipt.items).selectinload(ReceiptItem.inventory_item))).one()
    result = receipt_to_detail(reversal).model_dump(mode="json")
    result.update({"reversed_receipt_id": original.id, "reversed_receipt_number": original.receipt_number, "total_quantity_reversed": sum(line["quantity_to_remove"] for line in preview["lines"]), "restored_unit_costs": restored_unit_costs})
    complete_stock_mutation(mutation, result)
    db.commit()
    return _attach_stock_sync(
        db,
        result,
        requested=payload.sync_woocommerce,
        item_ids=item_ids,
        key=f"invoice-reversal-{original.id}",
        actor=actor,
        failure_message="Stock was reverted locally, but WooCommerce sync could not be queued",
    )
