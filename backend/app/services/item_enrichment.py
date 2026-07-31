import csv
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.imports import ImportError as ImportErrorRow
from app.models.imports import ImportJob
from app.models.inventory import InventoryItem, InventoryLocation, MovementType, StockMovement
from app.services.location_inventory import create_stock_movement, get_or_create_item_location, lock_inventory_stock, recalculate_item_location, recalculate_item_totals

PROTECTED_COLUMNS = ["Pongo Item ID", "Woo Product ID", "Woo Variation ID", "Woo Mapping Type", "Woo Mapping Status"]
ENRICHMENT_COLUMNS = [
    *PROTECTED_COLUMNS,
    "SKU", "Description", "Category", "Unit of Measurement", "Barcode", "Brand", "Manufacturer", "Manufacturer Website",
    "Recommended Retail Price", "Sales Price", "Unit Cost", "Weight", "Warehouse", "Inventory Location", "Default Location",
    "In Stock", "On Order", "Par Level", "Default Econ Order", "Default Lead Time Days", "Assembly", "Serializable", "Re-Order",
    "Storage Length", "Storage Width", "Storage Height", "Active",
]
REFERENCE_COLUMNS = {"SKU", "Description", "Category", "Recommended Retail Price", "Sales Price", "Weight"}
LOCAL_FIELDS = {
    "Unit of Measurement": ("unit_of_measurement", "text"),
    "Barcode": ("barcode", "text"),
    "Brand": ("brand", "text"),
    "Manufacturer": ("manufacturer", "text"),
    "Manufacturer Website": ("manufacturer_website", "text"),
    "Unit Cost": ("unit_cost", "decimal"),
    "Warehouse": ("warehouse", "text"),
    "Inventory Location": ("inventory_location", "text"),
    "Default Location": ("default_location", "text"),
    "On Order": ("on_order", "decimal"),
    "Par Level": ("par_level", "decimal"),
    "Default Econ Order": ("default_econ_order", "decimal"),
    "Default Lead Time Days": ("default_lead_time_days", "integer"),
    "Assembly": ("assembly", "boolean"),
    "Serializable": ("serializable", "boolean"),
    "Re-Order": ("reorder", "boolean"),
    "Storage Length": ("storage_length", "decimal"),
    "Storage Width": ("storage_width", "decimal"),
    "Storage Height": ("storage_height", "decimal"),
    "Active": ("active", "boolean"),
}
CLEARABLE_FIELDS = {field for field, kind in LOCAL_FIELDS.values() if kind in {"text", "decimal", "integer"}}
TRUE_VALUES = {"true", "yes", "1", "y"}
FALSE_VALUES = {"false", "no", "0", "n"}


@dataclass
class EnrichmentRow:
    row_number: int
    action: str
    match_method: str | None
    item: InventoryItem | None
    raw_row: dict[str, str]
    changes: dict[str, object] = field(default_factory=dict)
    current_values: dict[str, object] = field(default_factory=dict)
    imported_values: dict[str, object] = field(default_factory=dict)
    opening_stock: Decimal | None = None
    location_id: int | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ParsedEnrichment:
    rows: list[EnrichmentRow]
    skipped_count: int


def enrichment_csv(items: list[InventoryItem]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ENRICHMENT_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(enrichment_row(item))
    return buffer.getvalue()


def enrichment_row(item: InventoryItem) -> dict[str, object]:
    mapping_type = "variation" if item.woo_variation_id is not None else "simple"
    values = {
        "Pongo Item ID": item.id,
        "Woo Product ID": item.woo_product_id or "",
        "Woo Variation ID": item.woo_variation_id or "",
        "Woo Mapping Type": mapping_type,
        "Woo Mapping Status": item.woo_sync_status or "",
        "SKU": item.sku or "",
        "Description": item.description or "",
        "Category": item.category or "",
        "Recommended Retail Price": item.recommended_retail_price,
        "Sales Price": item.sales_price,
        "Weight": item.weight,
        "In Stock": item.in_stock,
    }
    for column, (attribute, _) in LOCAL_FIELDS.items():
        values[column] = getattr(item, attribute)
    return values


def parse_enrichment_csv(csv_text: str, db: Session, *, import_opening_stock: bool = False) -> ParsedEnrichment:
    reader = csv.reader(StringIO(csv_text.lstrip("\ufeff")))
    try:
        header = [column.strip() for column in next(reader)]
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail="CSV file is empty.") from exc
    if len(header) != len(set(header)):
        raise HTTPException(status_code=400, detail="CSV header contains duplicate columns.")
    missing = [column for column in PROTECTED_COLUMNS if column not in header]
    if missing:
        raise HTTPException(status_code=400, detail={"message": "Enrichment CSV is missing protected identity columns.", "missing_columns": missing})

    items = list(db.scalars(select(InventoryItem)).all())
    by_id = {item.id: item for item in items}
    by_woo = grouped(items, lambda item: (item.woo_product_id, item.woo_variation_id) if item.woo_product_id else None)
    by_sku = grouped(items, lambda item: normalized(item.sku))
    by_barcode = grouped(items, lambda item: normalized(item.barcode))
    rows: list[EnrichmentRow] = []
    rows_by_item_id: dict[int, EnrichmentRow] = {}
    skipped = 0

    for row_number, values in enumerate(reader, start=2):
        raw = {column: (values[index].strip() if index < len(values) else "") for index, column in enumerate(header)}
        if not any(raw.values()):
            skipped += 1
            continue
        row = EnrichmentRow(row_number=row_number, action="invalid", match_method=None, item=None, raw_row=raw)
        identifiers: list[tuple[str, list[InventoryItem]]] = []
        item_id = parse_int(raw.get("Pongo Item ID"), "Pongo Item ID", row.errors, allow_blank=True)
        product_id = parse_int(raw.get("Woo Product ID"), "Woo Product ID", row.errors, allow_blank=True)
        variation_id = parse_int(raw.get("Woo Variation ID"), "Woo Variation ID", row.errors, allow_blank=True)
        if item_id is not None:
            identifiers.append(("pongo_item_id", [by_id[item_id]] if item_id in by_id else []))
        if product_id is not None:
            identifiers.append(("woo_identity", by_woo.get((product_id, variation_id), [])))
        if raw.get("SKU"):
            identifiers.append(("sku", by_sku.get(normalized(raw["SKU"]), [])))
        if raw.get("Barcode"):
            identifiers.append(("barcode", by_barcode.get(normalized(raw["Barcode"]), [])))

        ambiguous = [method for method, matches in identifiers if len(matches) > 1]
        resolved_ids = {matches[0].id for _, matches in identifiers if len(matches) == 1}
        if ambiguous:
            row.errors.append(f"Ambiguous identifier match: {', '.join(ambiguous)}.")
            row.action = "conflict"
        elif len(resolved_ids) > 1:
            row.errors.append("CSV identifiers match different local items.")
            row.action = "conflict"
        elif not resolved_ids:
            row.errors.append("No existing Woo-mapped Pongo item matched this row.")
            row.action = "unmatched"
        else:
            row.item = by_id[next(iter(resolved_ids))]
            row.match_method = next(method for method, matches in identifiers if len(matches) == 1 and matches[0].id == row.item.id)
            validate_protected_identity(row, item_id, product_id, variation_id)
            if row.errors:
                row.action = "conflict"

        if row.item is not None and not row.errors:
            previous_row = rows_by_item_id.get(row.item.id)
            if previous_row is not None:
                message = f"Item is repeated in this file (rows {previous_row.row_number} and {row.row_number})."
                previous_row.errors.append(message)
                previous_row.action = "conflict"
                row.errors.append(message)
                row.action = "conflict"
            else:
                rows_by_item_id[row.item.id] = row

        if row.item is not None and not row.errors:
            build_changes(row)
            if import_opening_stock:
                build_opening_stock(row, db)
            elif raw.get("In Stock"):
                row.warnings.append("In Stock was ignored because Import opening stock is off.")
            if row.errors:
                row.action = "conflict"
            else:
                row.action = "update" if row.changes or row.opening_stock is not None else "unchanged"
        rows.append(row)
    return ParsedEnrichment(rows=rows, skipped_count=skipped)


def validate_protected_identity(row: EnrichmentRow, item_id: int | None, product_id: int | None, variation_id: int | None) -> None:
    item = row.item
    assert item is not None
    expected_type = "variation" if item.woo_variation_id is not None else "simple"
    if item.woo_product_id is None:
        row.errors.append("Matched item has no authoritative WooCommerce mapping.")
    if item_id is not None and item_id != item.id:
        row.errors.append("Protected Pongo Item ID does not match the selected item.")
    if item.woo_variation_id is not None and (product_id is None or variation_id is None):
        row.errors.append("Protected parent Woo Product ID and Woo Variation ID are both required for a variation.")
    elif (product_id is not None and product_id != item.woo_product_id) or (variation_id is not None and variation_id != item.woo_variation_id):
        row.errors.append("Protected WooCommerce identifiers do not match the current mapping.")
    if row.raw_row.get("Woo Mapping Type") and normalized(row.raw_row.get("Woo Mapping Type")) != expected_type:
        row.errors.append("Protected Woo Mapping Type does not match the current mapping.")
    if row.raw_row.get("Woo Mapping Status") and row.raw_row.get("Woo Mapping Status") != (item.woo_sync_status or ""):
        row.errors.append("Protected Woo Mapping Status does not match the current mapping.")


def build_changes(row: EnrichmentRow) -> None:
    item = row.item
    assert item is not None
    for column in REFERENCE_COLUMNS:
        imported = row.raw_row.get(column, "")
        if imported and normalized(imported) != normalized(getattr(item, reference_attribute(column))):
            row.warnings.append(f"{column} is Woo-owned reference data and was not changed.")
    for column, (attribute, kind) in LOCAL_FIELDS.items():
        raw = row.raw_row.get(column, "")
        if raw == "":
            continue
        if raw == "__CLEAR__":
            if attribute not in CLEARABLE_FIELDS:
                row.errors.append(f"{column} cannot be cleared.")
                continue
            value = None
        else:
            value = parse_value(raw, kind, column, row.errors)
        if row.errors:
            continue
        current = getattr(item, attribute)
        if comparable(current) != comparable(value):
            row.changes[attribute] = value
            row.current_values[column] = serializable(current)
            row.imported_values[column] = serializable(value)


def build_opening_stock(row: EnrichmentRow, db: Session) -> None:
    item = row.item
    assert item is not None
    raw_stock = row.raw_row.get("In Stock", "")
    if raw_stock == "":
        return
    quantity = parse_value(raw_stock, "decimal", "In Stock", row.errors)
    if quantity is None or row.errors:
        return
    if quantity < 0:
        row.errors.append("In Stock cannot be negative.")
        return
    warehouse = str(row.changes.get("warehouse", item.warehouse) or "").strip()
    location_name = str(row.changes.get("inventory_location", item.inventory_location or item.default_location) or "").strip()
    locations = list(db.scalars(select(InventoryLocation).where(
        InventoryLocation.active.is_(True),
        func.lower(func.trim(InventoryLocation.warehouse)) == normalized(warehouse),
        or_(func.lower(func.trim(InventoryLocation.location_code)) == normalized(location_name), func.lower(func.trim(InventoryLocation.location_name)) == normalized(location_name)),
    )).all())
    if len(locations) != 1:
        row.errors.append("Opening stock requires one valid active warehouse/location match.")
        return
    history_exists = bool(db.scalar(select(func.count(StockMovement.id)).where(StockMovement.inventory_item_id == item.id)))
    if Decimal(item.in_stock or 0) != 0 or Decimal(item.allocated or 0) != 0 or history_exists:
        row.errors.append("Opening stock is blocked because this item already has operational stock or history.")
        return
    row.opening_stock = quantity
    row.location_id = locations[0].id
    row.current_values["In Stock"] = serializable(item.in_stock)
    row.imported_values["In Stock"] = serializable(quantity)


def preview_enrichment(parsed: ParsedEnrichment) -> dict:
    valid = [row for row in parsed.rows if row.action in {"update", "unchanged"}]
    return {
        "total_rows": len(parsed.rows) + parsed.skipped_count,
        "valid_rows": len(valid),
        "invalid_rows": len(parsed.rows) - len(valid),
        "matched_by_pongo_item_id": count_match(parsed, "pongo_item_id"),
        "matched_by_woo_identity": count_match(parsed, "woo_identity"),
        "matched_by_sku": count_match(parsed, "sku"),
        "matched_by_barcode": count_match(parsed, "barcode"),
        "update_count": count_action(parsed, "update"),
        "create_count": 0,
        "unchanged_count": count_action(parsed, "unchanged"),
        "conflict_count": count_action(parsed, "conflict"),
        "unmatched_count": count_action(parsed, "unmatched"),
        "skipped_count": parsed.skipped_count,
        "preview_rows": [serialize_row(row) for row in parsed.rows],
        "warnings": [warning for row in parsed.rows for warning in row.warnings],
        "errors": [error for row in parsed.rows for error in serialize_errors(row)],
    }


def commit_enrichment(csv_text: str, db: Session, *, file_name: str | None, import_opening_stock: bool = False, created_by: str = "system") -> dict:
    file_hash = hashlib.sha256(csv_text.encode()).hexdigest()
    import_type = "items_enrichment_opening_stock" if import_opening_stock else "items_enrichment"
    parsed = parse_enrichment_csv(csv_text, db, import_opening_stock=import_opening_stock)
    if import_opening_stock:
        lock_inventory_stock(db, {row.item.id for row in parsed.rows if row.item is not None})
        if db.scalars(select(ImportJob).where(ImportJob.import_type == import_type, ImportJob.file_sha256 == file_hash)).first():
            raise HTTPException(status_code=409, detail="This opening-stock file was already committed.")
    job = ImportJob(file_name=file_name, import_type=import_type, file_sha256=file_hash, options_json={"import_opening_stock": import_opening_stock}, total_rows=len(parsed.rows) + parsed.skipped_count, successful_rows=0, failed_rows=0, status="completed", created_by=created_by, completed_at=datetime.now(timezone.utc))
    try:
        db.add(job)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if import_opening_stock:
            raise HTTPException(status_code=409, detail="This opening-stock file was already committed.") from exc
        raise
    updated = unchanged = failed = 0
    for row in parsed.rows:
        if row.action not in {"update", "unchanged"}:
            failed += 1
            for error in row.errors or ["Row was not committed."]:
                db.add(ImportErrorRow(import_job_id=job.id, row_number=row.row_number, sku=row.raw_row.get("SKU") or None, barcode=row.raw_row.get("Barcode") or None, error_message=f"{row.action}: {error}", raw_row=row.raw_row))
            continue
        item = row.item
        assert item is not None
        if row.opening_stock is not None:
            history_exists = bool(db.scalar(select(func.count(StockMovement.id)).where(StockMovement.inventory_item_id == item.id)))
            if Decimal(item.in_stock or 0) != 0 or Decimal(item.allocated or 0) != 0 or history_exists:
                failed += 1
                db.add(ImportErrorRow(import_job_id=job.id, row_number=row.row_number, sku=row.raw_row.get("SKU") or None, barcode=row.raw_row.get("Barcode") or None, error_message="Opening stock is blocked because stock or movement history changed after preview.", raw_row=row.raw_row))
                continue
        if row.action == "unchanged":
            unchanged += 1
            continue
        for attribute, value in row.changes.items():
            setattr(item, attribute, value)
        if row.opening_stock is not None and row.location_id is not None:
            location = db.get(InventoryLocation, row.location_id)
            assert location is not None
            old_item_stock = Decimal(item.in_stock or 0)
            item_location = get_or_create_item_location(db, item, location.warehouse, location.location_code or location.location_name, location_id=location.id, is_default_location=True, create_physical_location=False)
            old_location_stock = Decimal(item_location.in_stock or 0)
            item_location.in_stock = row.opening_stock
            item_location.allocated = Decimal("0")
            recalculate_item_location(item_location, item)
            recalculate_item_totals(db, item.id)
            create_stock_movement(db, item, MovementType.opening_balance_import, row.opening_stock - old_location_stock, item_location, old_location_stock, row.opening_stock, old_item_stock, Decimal(item.in_stock or 0), reason="Opening balance enrichment import", reference_type="import_job", reference_id=job.id, reference_number=str(job.id), created_by=created_by)
        updated += 1
    job.successful_rows = updated + unchanged
    job.failed_rows = failed
    db.commit()
    return {"import_job_id": job.id, "total_rows": job.total_rows, "updated_count": updated, "unchanged_count": unchanged, "created_count": 0, "skipped_count": parsed.skipped_count, "failed_count": failed, "conflict_count": count_action(parsed, "conflict"), "unmatched_count": count_action(parsed, "unmatched"), "errors": [error for row in parsed.rows for error in serialize_errors(row)]}


def grouped(items: list[InventoryItem], key_fn) -> dict[object, list[InventoryItem]]:
    result: dict[object, list[InventoryItem]] = {}
    for item in items:
        key = key_fn(item)
        if key not in {None, ""}:
            result.setdefault(key, []).append(item)
    return result


def parse_int(value: str | None, label: str, errors: list[str], *, allow_blank: bool = False) -> int | None:
    if value in {None, ""}:
        if not allow_blank:
            errors.append(f"{label} is required.")
        return None
    try:
        return int(str(value))
    except ValueError:
        errors.append(f"{label} must be an integer.")
        return None


def parse_value(value: str, kind: str, label: str, errors: list[str]):
    try:
        if kind == "decimal":
            return Decimal(value.replace(",", ""))
        if kind == "integer":
            return int(value)
        if kind == "boolean":
            lowered = normalized(value)
            if lowered in TRUE_VALUES:
                return True
            if lowered in FALSE_VALUES:
                return False
            raise ValueError
        return value.strip()
    except (InvalidOperation, ValueError):
        errors.append(f"{label} has an invalid {kind} value.")
        return None


def reference_attribute(column: str) -> str:
    return {"SKU": "sku", "Description": "description", "Category": "category", "Recommended Retail Price": "recommended_retail_price", "Sales Price": "sales_price", "Weight": "weight"}[column]


def normalized(value) -> str:
    return str(value or "").strip().casefold()


def comparable(value):
    if isinstance(value, Decimal):
        return value.normalize()
    return value


def serializable(value):
    return float(value) if isinstance(value, Decimal) else value


def count_match(parsed: ParsedEnrichment, method: str) -> int:
    return sum(1 for row in parsed.rows if row.match_method == method and row.action in {"update", "unchanged"})


def count_action(parsed: ParsedEnrichment, action: str) -> int:
    return sum(1 for row in parsed.rows if row.action == action)


def serialize_errors(row: EnrichmentRow) -> list[dict]:
    return [{"row_number": row.row_number, "sku": row.raw_row.get("SKU") or None, "barcode": row.raw_row.get("Barcode") or None, "error_message": error, "raw_row": row.raw_row} for error in row.errors]


def serialize_row(row: EnrichmentRow) -> dict:
    item = row.item
    return {
        "row_number": row.row_number,
        "item_name": item.description if item else row.raw_row.get("Description"),
        "sku": row.raw_row.get("SKU") or (item.sku if item else None),
        "barcode": row.raw_row.get("Barcode") or (item.barcode if item else None),
        "pongo_item_id": item.id if item else None,
        "woo_product_id": item.woo_product_id if item else None,
        "woo_variation_id": item.woo_variation_id if item else None,
        "variation_attributes": getattr(item, "woo_variation_attributes", None) if item else None,
        "match_method": row.match_method,
        "action": row.action,
        "fields_changing": list(row.current_values),
        "current_values": row.current_values,
        "imported_values": row.imported_values,
        "warnings": row.warnings,
        "errors": row.errors,
        "raw_row": row.raw_row,
    }
