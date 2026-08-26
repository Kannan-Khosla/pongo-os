from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.imports import ImportError, ImportJob, ImportMappingProfile, ImportPreview, ImportPreviewRow, ItemImportChange
from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation, InventoryLocation, StockMovement
from app.schemas.woocommerce import WooStockSyncRequest
from app.services.items import apply_calculated_fields
from app.services.location_inventory import (
    StaleStockQuantityError,
    assert_item_invariants,
    assert_location_invariants,
    create_committed_adjustment_batch,
    get_or_create_item_location,
    lock_inventory_stock,
    recalculate_item_location,
    recalculate_item_totals,
    set_opening_balance,
    transfer_between_locations,
)
from app.services.order_workflow import auto_allocate_processing_orders_fifo
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_stock_sync_jobs import create_stock_sync_job
from app.services.woocommerce_writeback import stock_writeback_enabled


logger = logging.getLogger("pongo.item_import")
SCHEMA_VERSION = "2026-08-26.1"
OUTCOMES = {"add_items", "update_items", "repair_items", "starting_inventory", "update_stock"}
READY_STATES = {"will_create", "will_update"}
ISSUE_STATES = {"needs_attention", "duplicate", "unmatched", "blocked"}
ALLOWED_MIME_TYPES = {"", "text/csv", "text/plain", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}
TRUE_VALUES = {"true", "yes", "1", "y", "on"}
FALSE_VALUES = {"false", "no", "0", "n", "off"}


def field(
    key: str,
    label: str,
    attribute: str | None,
    value_type: str,
    outcomes: list[str],
    *,
    aliases: list[str] | None = None,
    required_for: list[str] | None = None,
    example: str = "",
    description: str = "",
    nullable: bool = True,
    editable: bool = True,
    quantity_related: bool = False,
    max_length: int | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "attribute": attribute,
        "type": value_type,
        "outcomes": outcomes,
        "aliases": aliases or [],
        "required_for": required_for or [],
        "example": example,
        "description": description,
        "nullable": nullable,
        "editable": editable,
        "quantity_related": quantity_related,
        "derived": False,
        "max_length": max_length,
    }


METADATA_OUTCOMES = ["add_items", "update_items"]
FIELD_SPECS = [
    field("sku", "SKU", "sku", "text", [*METADATA_OUTCOMES, "starting_inventory", "update_stock"], aliases=["Item SKU", "Product SKU", "Code"], required_for=["add_items", "update_items", "starting_inventory", "update_stock"], example="DOG-FOOD-001", description="The unique item code used to match products.", nullable=False, max_length=120),
    field("product_name", "Product name", "description", "text", METADATA_OUTCOMES, aliases=["Description", "Product title", "Name", "Item name"], example="ACANA Adult Dog Recipe", description="The customer-facing product or item name."),
    field("barcode", "Barcode", "barcode", "text", METADATA_OUTCOMES, aliases=["UPC", "EAN", "GTIN", "UPC code"], example="064992123456", description="A unique scannable barcode.", max_length=120),
    field("category", "Category", "category", "text", METADATA_OUTCOMES, aliases=["Product category", "Item category"], example="Dry Dog Food", max_length=200),
    field("brand", "Brand", "brand", "text", METADATA_OUTCOMES, aliases=["Vendor brand"], example="ACANA", max_length=200),
    field("tags", "Tags", "tags", "text", METADATA_OUTCOMES, aliases=["Labels", "Keywords"], example="dog, adult, dry food", max_length=2000),
    field("client", "Client", "client", "text", METADATA_OUTCOMES, aliases=["Account", "Organization"], example="Pongo", max_length=120),
    field("unit_of_measurement", "Unit of measurement", "unit_of_measurement", "text", METADATA_OUTCOMES, aliases=["UOM", "Unit", "Unit of Measure"], example="Each", max_length=50),
    field("manufacturer", "Manufacturer", "manufacturer", "text", METADATA_OUTCOMES, aliases=["Maker"], example="Champion Petfoods", max_length=200),
    field("manufacturer_website", "Manufacturer website", "manufacturer_website", "url", METADATA_OUTCOMES, aliases=["Manufacturer URL", "Website"], example="https://example.com", max_length=500),
    field("recommended_retail_price", "Recommended retail price", "recommended_retail_price", "decimal", METADATA_OUTCOMES, aliases=["RRP", "MSRP", "Retail price"], example="79.99"),
    field("sales_price", "Sales price", "sales_price", "decimal", METADATA_OUTCOMES, aliases=["Price", "Selling price"], example="74.99"),
    field("unit_cost", "Unit cost", "unit_cost", "decimal", METADATA_OUTCOMES, aliases=["Cost", "Wholesale", "Wholesale cost"], example="42.50"),
    field("weight", "Weight", "weight", "decimal", METADATA_OUTCOMES, aliases=["Item weight"], example="11.4"),
    field("par_level", "Par level", "par_level", "decimal", METADATA_OUTCOMES, aliases=["Minimum stock", "Reorder point"], example="4"),
    field("default_econ_order", "Default economic order", "default_econ_order", "decimal", METADATA_OUTCOMES, aliases=["Economic order quantity", "EOQ"], example="6"),
    field("default_lead_time_days", "Default lead time days", "default_lead_time_days", "integer", METADATA_OUTCOMES, aliases=["Lead time", "Lead time days", "Default Lead Time (Days)"], example="5"),
    field("warehouse", "Warehouse", "warehouse", "text", METADATA_OUTCOMES, aliases=["Warehouse name"], example="Main Warehouse", max_length=120),
    field("inventory_location", "Inventory location", "inventory_location", "text", METADATA_OUTCOMES, aliases=["Location", "Bin", "Location code"], example="A-01", max_length=200),
    field("default_location", "Default location", "default_location", "text", METADATA_OUTCOMES, aliases=["Primary location"], example="A-01", max_length=200),
    field("assembly", "Assembly", "assembly", "boolean", METADATA_OUTCOMES, aliases=["Is assembly"], example="No", nullable=False),
    field("serializable", "Serializable", "serializable", "boolean", METADATA_OUTCOMES, aliases=["Serialized"], example="No", nullable=False),
    field("track_lot", "Track lot", "track_lot", "boolean", METADATA_OUTCOMES, aliases=["Lot tracked", "Track lots"], example="No", nullable=False),
    field("perishable", "Perishable", "perishable", "boolean", METADATA_OUTCOMES, aliases=["Is perishable"], example="No", nullable=False),
    field("reorder", "Reorder", "reorder", "boolean", METADATA_OUTCOMES, aliases=["Re-order", "Allow reorder"], example="Yes", nullable=False),
    field("active", "Active", "active", "boolean", METADATA_OUTCOMES, aliases=["Enabled", "Is active"], example="Yes", nullable=False),
    field("non_inventory", "Non-inventory item", "non_inventory", "boolean", METADATA_OUTCOMES, aliases=["Non inventory", "Service item"], example="No", nullable=False),
    field("storage_length", "Storage length", "storage_length", "decimal", METADATA_OUTCOMES, aliases=["Length"], example="12"),
    field("storage_width", "Storage width", "storage_width", "decimal", METADATA_OUTCOMES, aliases=["Width"], example="8"),
    field("storage_height", "Storage height", "storage_height", "decimal", METADATA_OUTCOMES, aliases=["Height"], example="4"),
    field("stock_quantity", "In stock", None, "decimal", ["update_stock"], aliases=["On hand", "Stock", "Quantity", "Current stock"], required_for=["update_stock"], example="24", description="The exact total physical quantity for this SKU after the import. Multiple CSV rows for one SKU are added together.", nullable=False, quantity_related=True),
    field("starting_quantity", "Starting quantity", None, "decimal", ["starting_inventory"], aliases=["Starting inventory", "Initial quantity", "Opening quantity", "Quantity"], required_for=["starting_inventory"], example="24", description="The physical quantity present at the beginning of onboarding.", nullable=False, quantity_related=True),
    field("starting_warehouse", "Warehouse", None, "text", ["starting_inventory"], aliases=["Warehouse name"], required_for=["starting_inventory"], example="Main Warehouse", nullable=False, max_length=120),
    field("starting_location", "Inventory location", None, "text", ["starting_inventory"], aliases=["Location", "Bin", "Location code"], required_for=["starting_inventory"], example="A-01", nullable=False, max_length=200),
    field("note", "Reference note", None, "text", ["starting_inventory", "update_stock"], aliases=["Reference", "Notes", "Reason"], example="Physical count", max_length=500),
]

REPAIR_FIELD_SPECS = [
    field("item_id", "Pongo Item ID", None, "integer", ["repair_items"], aliases=["Item ID", "Pongo ID"], example="123", description="The immutable Pongo OS item identifier. Use this or SKU to match an item.", editable=False),
    field("sku", "SKU", None, "text", ["repair_items"], aliases=["Item SKU", "Product SKU", "Code"], example="DOG-FOOD-001", description="An immutable fallback identifier when Pongo Item ID is unavailable.", editable=False, max_length=120),
    field("product_name", "Product name", None, "text", ["repair_items"], aliases=["Description", "Product title", "Name", "Item name"], example="ACANA Adult Dog Recipe", description="Read-only context for reviewing the matched item.", editable=False),
    field("woo_product_id", "Woo product ID", None, "integer", ["repair_items"], aliases=["WooCommerce product ID", "Woo Product ID"], example="456", description="Read-only WooCommerce identity used to validate the match.", editable=False),
    field("woo_variation_id", "Woo variation ID", None, "integer", ["repair_items"], aliases=["WooCommerce variation ID", "Woo Variation ID"], example="0", description="Read-only WooCommerce variation identity used to validate the match.", editable=False),
    field("brand", "Brand", "brand", "text", ["repair_items"], aliases=["Vendor brand"], example="ACANA", max_length=200),
    field("unit_cost", "Unit cost", "unit_cost", "decimal", ["repair_items"], aliases=["Cost", "Wholesale", "Wholesale cost"], example="42.50"),
    field("warehouse", "Target warehouse", None, "text", ["repair_items"], aliases=["Warehouse", "Warehouse name"], required_for=["repair_items"], example="Main Warehouse", description="The active warehouse that should hold this item after repair.", nullable=False, max_length=120),
    field("inventory_location", "Target inventory location", None, "text", ["repair_items"], aliases=["Inventory location", "Location", "Bin", "Location code"], required_for=["repair_items"], example="001", description="The one active physical location to keep for this item.", nullable=False, max_length=200),
]
REPAIR_HASH_ATTRIBUTES = (
    "active",
    "brand",
    "default_location",
    "inventory_location",
    "non_inventory",
    "sku",
    "unit_cost",
    "warehouse",
    "woo_product_id",
    "woo_variation_id",
)

SPEC_BY_ATTRIBUTE = {spec["attribute"]: spec for spec in FIELD_SPECS if spec["attribute"]}
OUTCOME_CONTENT = {
    "add_items": {
        "label": "Add new items",
        "description": "Create products that do not yet exist in Pongo OS.",
        "changes": "Creates item records and optional product metadata.",
        "does_not_change": "Inventory quantities and stock history will not change.",
    },
    "update_items": {
        "label": "Update item details",
        "description": "Update existing products by SKU.",
        "changes": "Updates approved metadata and shows every before-and-after value.",
        "does_not_change": "On hand, allocated, available, and stock history will not change.",
    },
    "repair_items": {
        "label": "Repair item data and locations",
        "description": "Update brand and unit cost while consolidating unallocated inventory into one active location.",
        "changes": "Moves unallocated stock and on-order quantities into the selected location with an audit trail. Allocated units stay reserved at their source until the order releases them.",
        "does_not_change": "Barcodes, SKUs, WooCommerce identity, item totals, allocations, and WooCommerce stock are not edited.",
    },
    "starting_inventory": {
        "label": "Set starting inventory",
        "description": "Record the physical quantity present at the beginning of onboarding.",
        "changes": "Creates audited starting-inventory movements at an eligible location.",
        "does_not_change": "Existing operational inventory is never overwritten.",
    },
    "update_stock": {
        "label": "Override stock levels",
        "description": "Set exact physical stock from a full CSV export, matched by SKU.",
        "changes": "Adds location rows into one total per SKU, skips matching totals, and applies every safe difference in one audited transaction.",
        "does_not_change": "Allocated and sellable quantities remain system-managed; CSV locations and item details are not edited.",
    },
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def serializable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def normalize_identifier(value: Any) -> str:
    return str(value or "").strip().casefold()


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().casefold()).strip()


def safe_filename(value: str | None) -> str:
    base = Path(value or "items.csv").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .")
    return (cleaned or "items.csv")[:300]


def schema_fields(outcome: str) -> list[dict[str, Any]]:
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=404, detail="Unknown item import outcome.")
    return [{key: value for key, value in spec.items() if key != "attribute"} for spec in field_specs_for(outcome)]


def schema_document() -> dict[str, Any]:
    settings = get_settings()
    return {
        "schema_version": SCHEMA_VERSION,
        "accepted_file_types": [".csv"],
        "max_file_bytes": settings.item_import_max_bytes,
        "preview_ttl_hours": settings.item_import_preview_ttl_hours,
        "protected_inventory_fields": ["Allocated", "Available", "Stock movement history"],
        "outcomes": [
            {
                "key": outcome,
                **OUTCOME_CONTENT[outcome],
                "fields": schema_fields(outcome),
                "required_fields": [spec["key"] for spec in field_specs_for(outcome) if outcome in spec["required_for"]],
            }
            for outcome in ["add_items", "update_items", "repair_items", "update_stock", "starting_inventory"]
        ],
    }


def field_specs_for(outcome: str) -> list[dict[str, Any]]:
    if outcome == "repair_items":
        return REPAIR_FIELD_SPECS
    return [spec for spec in FIELD_SPECS if outcome in spec["outcomes"]]


def template_headers(outcome: str) -> list[str]:
    return [spec["label"] for spec in field_specs_for(outcome)]


def safe_csv_value(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return f"'{value}"
    return serializable(value)


def template_csv(outcome: str, db: Session, *, include_existing: bool = False) -> str:
    specs = field_specs_for(outcome)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[spec["label"] for spec in specs])
    writer.writeheader()
    if include_existing and outcome == "update_items":
        for item in db.scalars(select(InventoryItem).order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())).all():
            writer.writerow({spec["label"]: safe_csv_value(getattr(item, spec["attribute"], "")) for spec in specs})
    elif include_existing and outcome == "repair_items":
        for item in db.scalars(
            select(InventoryItem)
            .where(InventoryItem.active.is_(True), InventoryItem.non_inventory.is_(False))
            .order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())
        ).all():
            values = {
                "item_id": item.id,
                "sku": item.sku,
                "product_name": item.woo_name or item.description,
                "woo_product_id": item.woo_product_id,
                "woo_variation_id": item.woo_variation_id,
                "brand": item.brand,
                "unit_cost": item.unit_cost,
                "warehouse": item.warehouse,
                "inventory_location": item.inventory_location or item.default_location,
            }
            writer.writerow({spec["label"]: safe_csv_value(values.get(spec["key"], "")) for spec in specs})
    elif include_existing and outcome == "update_stock":
        for item in db.scalars(select(InventoryItem).order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())).all():
            values = {"sku": item.sku, "stock_quantity": item.in_stock, "note": ""}
            writer.writerow({spec["label"]: safe_csv_value(values.get(spec["key"], "")) for spec in specs})
    else:
        writer.writerow({spec["label"]: safe_csv_value(spec["example"]) for spec in specs})
    return buffer.getvalue()


def source_signature(headers: list[str]) -> str:
    normalized = "\n".join(normalize_header(header) for header in headers)
    return hashlib.sha256(normalized.encode()).hexdigest()


def issue(code: str, field_key: str | None, message: str, invalid_value: Any = None, suggested_action: str | None = None, *, blocking: bool = True) -> dict[str, Any]:
    return {
        "code": code,
        "field": field_key,
        "message": message,
        "invalid_value": None if invalid_value is None else str(invalid_value)[:300],
        "suggested_action": suggested_action,
        "blocking": blocking,
    }


def header_aliases(outcome: str) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = defaultdict(list)
    for spec in field_specs_for(outcome):
        for candidate in [spec["key"], spec["label"], *spec["aliases"]]:
            aliases[normalize_header(candidate)].append(spec["key"])
    return aliases


def suggest_mapping(headers: list[str], outcome: str) -> tuple[dict[str, str | None], list[dict[str, Any]]]:
    aliases = header_aliases(outcome)
    fields_by_key = {spec["key"]: spec for spec in field_specs_for(outcome)}
    mapping: dict[str, str | None] = {}
    suggestions: list[dict[str, Any]] = []
    used: set[str] = set()
    for header in headers:
        matches = list(dict.fromkeys(aliases.get(normalize_header(header), [])))
        destination = matches[0] if len(matches) == 1 and matches[0] not in used else None
        if destination:
            used.add(destination)
        mapping[header] = destination
        suggestions.append({"source": header, "destination": destination, "confidence": "exact" if destination and normalize_header(header) in {normalize_header(destination), normalize_header(fields_by_key[destination]["label"])} else ("alias" if destination else "unmatched"), "ambiguous_matches": matches if len(matches) > 1 else []})
    return mapping, suggestions


def parse_csv_bytes(content: bytes) -> tuple[str, list[str], list[dict[str, str]], str, str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_encoding", "message": "CSV files must use UTF-8 encoding. Save the file as UTF-8 and try again."}) from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail={"code": "empty_file", "message": "The selected CSV file is empty."})
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    try:
        reader = csv.reader(StringIO(text), csv.excel, delimiter=dialect.delimiter, strict=True)
        raw_headers = next(reader)
        headers = [header.strip() for header in raw_headers]
        if not any(headers):
            raise HTTPException(status_code=400, detail={"code": "missing_headers", "message": "The CSV header row is empty."})
        normalized_headers = [normalize_header(header) for header in headers]
        duplicates = sorted({header for header, count in Counter(normalized_headers).items() if count > 1})
        if duplicates:
            raise HTTPException(status_code=400, detail={"code": "duplicate_headers", "message": "The CSV contains duplicate column headers.", "headers": duplicates})
        rows: list[dict[str, str]] = []
        for values in reader:
            if not any(str(value).strip() for value in values):
                continue
            if len(values) > len(headers):
                raise HTTPException(status_code=400, detail={"code": "malformed_row", "message": f"CSV row {len(rows) + 2} contains more values than the header row.", "row_number": len(rows) + 2})
            rows.append({header: values[index].strip() if index < len(values) else "" for index, header in enumerate(headers)})
    except csv.Error as exc:
        raise HTTPException(status_code=400, detail={"code": "malformed_csv", "message": f"The CSV could not be read: {exc}."}) from exc
    if not rows:
        raise HTTPException(status_code=400, detail={"code": "no_data_rows", "message": "The CSV contains headers but no item rows."})
    delimiter_name = {",": "Comma", ";": "Semicolon", "\t": "Tab", "|": "Pipe"}.get(dialect.delimiter, dialect.delimiter)
    return text, headers, rows, "UTF-8", delimiter_name


def aggregate_stock_rows(rows: list[dict[str, str]], mapping: dict[str, str | None]) -> list[dict[str, str]]:
    source_by_field = {destination: source for source, destination in mapping.items() if destination}
    sku_source = source_by_field.get("sku")
    quantity_source = source_by_field.get("stock_quantity")
    if not sku_source or not quantity_source:
        return rows
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[normalize_identifier(row.get(sku_source)) or f"__blank_{index}"].append(row)
    aggregated: list[dict[str, str]] = []
    for group in grouped.values():
        header_by_name = {normalize_header(header): header for header in group[0]}
        warehouse_source = next((header_by_name[name] for name in ("warehouse", "warehouse name") if name in header_by_name), None)
        location_source = next((header_by_name[name] for name in ("inventory location", "location", "bin", "location code") if name in header_by_name), None)
        if warehouse_source and location_source:
            scopes = [
                (normalize_identifier(row.get(warehouse_source)), normalize_identifier(row.get(location_source)))
                for row in group
            ]
            populated_scopes = [scope for scope in scopes if any(scope)]
            if len(populated_scopes) != len(set(populated_scopes)):
                aggregated.extend(group)
                continue
        try:
            quantities = [Decimal(str(row.get(quantity_source) or "").replace(",", "")) for row in group]
            if any(not quantity.is_finite() or quantity < 0 for quantity in quantities):
                raise InvalidOperation
        except InvalidOperation:
            aggregated.extend(group)
            continue
        row = dict(group[0])
        row[quantity_source] = format(sum(quantities, Decimal("0")), "f")
        aggregated.append(row)
    return aggregated


def replace_stock_preview_rows(preview: ImportPreview, db: Session, mapping: dict[str, str | None]) -> None:
    existing = list(db.scalars(select(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id)).all())
    if any(row.corrected_data or row.excluded for row in existing):
        raise HTTPException(status_code=409, detail={"code": "mapping_after_corrections", "message": "Start a new preview to change stock column mappings after correcting rows."})
    _, _, source_rows, _, _ = parse_csv_bytes(preview.source_file_text.encode("utf-8"))
    rows = aggregate_stock_rows(source_rows, mapping)
    db.execute(delete(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id))
    db.flush()
    for index, raw_row in enumerate(rows, start=2):
        db.add(ImportPreviewRow(preview_id=preview.id, row_number=index, source_data=raw_row, normalized_data={}, corrected_data={}, proposed_changes={}, issues_json=[], state="pending_mapping", excluded=False))
    db.flush()


async def create_preview(file: UploadFile, outcome: str, db: Session, *, actor: str) -> ImportPreview:
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail={"code": "invalid_outcome", "message": "Choose Add new items, Update item details, Repair item data and locations, Override stock levels, or Set starting inventory."})
    filename = safe_filename(file.filename)
    if Path(filename).suffix.casefold() != ".csv":
        raise HTTPException(status_code=400, detail={"code": "invalid_file_type", "message": "Choose a CSV file ending in .csv."})
    if (file.content_type or "").casefold() not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail={"code": "invalid_mime_type", "message": "The selected file is not recognized as CSV text."})
    content = await file.read()
    settings = get_settings()
    if len(content) > settings.item_import_max_bytes:
        raise HTTPException(status_code=413, detail={"code": "file_too_large", "message": f"The CSV exceeds the {settings.item_import_max_bytes // 1_048_576} MB file limit."})
    started = perf_counter()
    source_text, headers, raw_rows, encoding, delimiter = parse_csv_bytes(content)
    source_row_count = len(raw_rows)
    mapping, suggestions = suggest_mapping(headers, outcome)
    if outcome == "update_stock":
        raw_rows = aggregate_stock_rows(raw_rows, mapping)
    columns = [
        {
            **suggestion,
            "samples": list(dict.fromkeys(row.get(suggestion["source"], "") for row in raw_rows if row.get(suggestion["source"], "")))[:3],
        }
        for suggestion in suggestions
    ]
    preview = ImportPreview(
        id=str(uuid4()),
        outcome=outcome,
        file_name=filename,
        file_sha256=hashlib.sha256(content).hexdigest(),
        source_file_text=source_text,
        schema_version=SCHEMA_VERSION,
        source_headers=headers,
        source_columns_json=columns,
        mapping_json=mapping,
        options_json={"allow_blank_clears": False, "file_size": len(content), "encoding": encoding, "delimiter": delimiter, "mapping_profile_id": None, "source_row_count": source_row_count},
        summary_json={},
        status="draft",
        created_by=actor,
        expires_at=utcnow() + timedelta(hours=settings.item_import_preview_ttl_hours),
    )
    db.add(preview)
    db.flush()
    for index, raw_row in enumerate(raw_rows, start=2):
        db.add(ImportPreviewRow(preview_id=preview.id, row_number=index, source_data=raw_row, normalized_data={}, corrected_data={}, proposed_changes={}, issues_json=[], state="pending_mapping", excluded=False))
    db.flush()
    revalidate_preview(preview, db)
    preview.summary_json = {**preview.summary_json, "preview_duration_ms": round((perf_counter() - started) * 1000)}
    db.commit()
    db.refresh(preview)
    logger.info(json.dumps({"event": "item_import_preview_created", "preview_id": preview.id, "outcome": outcome, "rows": len(raw_rows), "duration_ms": preview.summary_json.get("preview_duration_ms")}))
    return preview


def get_preview(db: Session, preview_id: str, actor: str, *, with_rows: bool = False) -> ImportPreview:
    statement = select(ImportPreview).where(ImportPreview.id == preview_id)
    if with_rows:
        statement = statement.options(selectinload(ImportPreview.rows))
    preview = db.scalars(statement).one_or_none()
    if preview is None:
        raise HTTPException(status_code=404, detail={"code": "preview_not_found", "message": "This import preview could not be found."})
    if preview.created_by != actor:
        raise HTTPException(status_code=403, detail={"code": "preview_access_denied", "message": "This import preview belongs to another user."})
    if preview.status in {"draft", "ready"} and aware(preview.expires_at) <= utcnow():
        preview.status = "expired"
        db.commit()
    return preview


def destination_values(row: ImportPreviewRow, preview: ImportPreview) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for source, destination in (preview.mapping_json or {}).items():
        if destination:
            values[destination] = row.source_data.get(source, "")
    values.update(row.corrected_data or {})
    return values


def parse_typed(spec: dict[str, Any], raw: Any, row_number: int, issues: list[dict[str, Any]]) -> Any:
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    if spec["max_length"] and len(text) > spec["max_length"]:
        issues.append(issue("value_too_long", spec["key"], f"Row {row_number}: {spec['label']} cannot exceed {spec['max_length']} characters.", text, f"Shorten {spec['label']} to {spec['max_length']} characters or fewer."))
        return None
    if spec["type"] == "text":
        return text
    if spec["type"] == "url":
        if not re.match(r"^https?://[^\s]+$", text, re.IGNORECASE):
            issues.append(issue("invalid_url", spec["key"], f"Row {row_number}: {spec['label']} must be a complete http:// or https:// URL. Received {text!r}.", text, "Enter a complete web address or leave this field blank."))
            return None
        return text
    if spec["type"] in {"decimal", "integer"}:
        try:
            number = Decimal(text.replace(",", ""))
        except InvalidOperation:
            issues.append(issue("invalid_number", spec["key"], f"Row {row_number}: {spec['label']} must be a number greater than or equal to zero. Received {text!r}.", text, "Enter a number such as 42 or 42.50."))
            return None
        if not number.is_finite():
            issues.append(issue("invalid_number", spec["key"], f"Row {row_number}: {spec['label']} must be a finite number. Received {text!r}.", text, "Enter a number such as 42 or 42.50."))
            return None
        if number < 0:
            issues.append(issue("negative_number", spec["key"], f"Row {row_number}: {spec['label']} cannot be negative. Received {text!r}.", text, "Enter zero or a positive number."))
            return None
        if spec["type"] == "integer":
            if number != number.to_integral_value():
                issues.append(issue("invalid_integer", spec["key"], f"Row {row_number}: {spec['label']} must be a whole number. Received {text!r}.", text, "Enter a whole number such as 5."))
                return None
            return int(number)
        return number
    if spec["type"] == "boolean":
        normalized = text.casefold()
        if normalized in TRUE_VALUES:
            return True
        if normalized in FALSE_VALUES:
            return False
        issues.append(issue("invalid_boolean", spec["key"], f"Row {row_number}: {spec['label']} must be Yes or No. Received {text!r}.", text, "Use Yes/No, True/False, or 1/0."))
        return None
    return text


def item_value_hash(item: InventoryItem, attributes: list[str]) -> str:
    payload = {"id": item.id, **{attribute: serializable(getattr(item, attribute, None)) for attribute in sorted(attributes)}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def values_equal(current: Any, incoming: Any) -> bool:
    if isinstance(current, Decimal) or isinstance(incoming, Decimal):
        try:
            return Decimal(str(current or 0)) == Decimal(str(incoming or 0))
        except InvalidOperation:
            return False
    return current == incoming


def active_location_map(db: Session) -> dict[tuple[str, str], list[InventoryLocation]]:
    locations: dict[tuple[str, str], list[InventoryLocation]] = defaultdict(list)
    for location in db.scalars(select(InventoryLocation).where(InventoryLocation.active.is_(True))).all():
        for name in {location.location_code, location.location_name}:
            if name:
                locations[(normalize_identifier(location.warehouse), normalize_identifier(name))].append(location)
    return locations


def location_snapshot(
    item: InventoryItem,
    item_locations: list[InventoryItemLocation],
    physical_locations: dict[int, InventoryLocation],
) -> dict[str, Any]:
    return {
        "item_totals": {
            "in_stock": serializable(item.in_stock or 0),
            "allocated": serializable(item.allocated or 0),
            "sellable": serializable(item.sellable or 0),
            "on_order": serializable(item.on_order or 0),
        },
        "locations": [
            {
                "id": row.id,
                "location_id": row.location_id,
                "warehouse": row.warehouse,
                "inventory_location": row.inventory_location,
                "location_code": row.location_code,
                "location_name": row.location_name,
                "active": bool(row.active),
                "is_default_location": bool(row.is_default_location),
                "physical_active": bool(physical_locations.get(row.location_id).active) if row.location_id in physical_locations else False,
                "physical_warehouse": physical_locations.get(row.location_id).warehouse if row.location_id in physical_locations else None,
                "physical_location_code": physical_locations.get(row.location_id).location_code if row.location_id in physical_locations else None,
                "physical_location_name": physical_locations.get(row.location_id).location_name if row.location_id in physical_locations else None,
                "in_stock": serializable(row.in_stock or 0),
                "allocated": serializable(row.allocated or 0),
                "sellable": serializable(row.sellable or 0),
                "on_order": serializable(row.on_order or 0),
            }
            for row in sorted(item_locations, key=lambda candidate: candidate.id)
        ],
    }


def physical_location_snapshot(location: InventoryLocation | None) -> dict[str, Any] | None:
    if location is None:
        return None
    return {
        "id": location.id,
        "warehouse": location.warehouse,
        "location_code": location.location_code,
        "location_name": location.location_name,
        "active": bool(location.active),
    }


def has_location_balances(row: InventoryItemLocation) -> bool:
    return any(Decimal(value or 0) != 0 for value in (row.in_stock, row.allocated, row.sellable, row.on_order))


def stock_total_targets(candidates: list[InventoryItemLocation], quantity: Decimal) -> list[dict[str, Any]]:
    current = {candidate.id: Decimal(candidate.in_stock or 0) for candidate in candidates}
    delta = quantity - sum(current.values(), Decimal("0"))
    if delta > 0:
        target = min(candidates, key=lambda candidate: (normalize_identifier(candidate.inventory_location) != "unassigned", not candidate.is_default_location, candidate.id))
        current[target.id] += delta
    elif delta < 0:
        remaining = -delta
        for candidate in sorted(candidates, key=lambda row: (normalize_identifier(row.inventory_location) != "unassigned", not row.is_default_location, row.id)):
            reduction = min(remaining, max(current[candidate.id] - Decimal(candidate.allocated or 0), Decimal("0")))
            current[candidate.id] -= reduction
            remaining -= reduction
            if remaining == 0:
                break
    return [
        {
            "inventory_item_location_id": candidate.id,
            "expected_location_id": candidate.location_id,
            "expected_quantity": serializable(candidate.in_stock or 0),
            "expected_allocated": serializable(candidate.allocated or 0),
            "new_quantity": serializable(current[candidate.id]),
        }
        for candidate in candidates
    ]


def revalidate_preview(preview: ImportPreview, db: Session) -> ImportPreview:
    rows = list(db.scalars(select(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id).order_by(ImportPreviewRow.row_number)).all())
    outcome = preview.outcome
    fields = field_specs_for(outcome)
    field_keys = {spec["key"] for spec in fields}
    required = {spec["key"] for spec in fields if outcome in spec["required_for"]}
    mapped_destinations = {destination for destination in (preview.mapping_json or {}).values() if destination in field_keys}
    missing_mapping = sorted(required - mapped_destinations)
    mapped_rows = {row.id: destination_values(row, preview) for row in rows}
    sku_counts = Counter(normalize_identifier(values.get("sku")) for values in mapped_rows.values() if normalize_identifier(values.get("sku")))
    stock_scope_counts = Counter(
        (normalize_identifier(values.get("sku")), normalize_identifier(values.get("warehouse")), normalize_identifier(values.get("inventory_location")))
        for values in mapped_rows.values()
        if normalize_identifier(values.get("sku"))
    )
    barcode_counts = Counter(normalize_identifier(values.get("barcode")) for values in mapped_rows.values() if normalize_identifier(values.get("barcode")))

    sku_keys = {normalize_identifier(values.get("sku")) for values in mapped_rows.values() if normalize_identifier(values.get("sku"))}
    barcode_keys = {normalize_identifier(values.get("barcode")) for values in mapped_rows.values() if normalize_identifier(values.get("barcode"))}
    item_ids: set[int] = set()
    if outcome == "repair_items":
        for values in mapped_rows.values():
            try:
                raw_item_id = Decimal(str(values.get("item_id") or "").strip())
                item_id = int(raw_item_id)
            except (InvalidOperation, ValueError):
                continue
            if raw_item_id == raw_item_id.to_integral_value() and item_id > 0:
                item_ids.add(item_id)
    item_matchers = []
    if sku_keys:
        item_matchers.append(func.lower(func.trim(InventoryItem.sku)).in_(sku_keys))
    if barcode_keys:
        item_matchers.append(func.lower(func.trim(InventoryItem.barcode)).in_(barcode_keys))
    if item_ids:
        item_matchers.append(InventoryItem.id.in_(item_ids))
    items = list(db.scalars(select(InventoryItem).where(or_(*item_matchers))).all()) if item_matchers else []
    items_by_id = {item.id: item for item in items}
    by_sku: dict[str, list[InventoryItem]] = defaultdict(list)
    by_barcode: dict[str, list[InventoryItem]] = defaultdict(list)
    for item in items:
        if item.sku:
            by_sku[normalize_identifier(item.sku)].append(item)
        if item.barcode:
            by_barcode[normalize_identifier(item.barcode)].append(item)

    item_locations_by_item: dict[int, list[InventoryItemLocation]] = defaultdict(list)
    if outcome in {"update_stock", "repair_items"} and items:
        statement = select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id.in_([item.id for item in items]))
        if outcome == "update_stock":
            statement = statement.where(InventoryItemLocation.active.is_(True))
        for item_location in db.scalars(statement).all():
            item_locations_by_item[item_location.inventory_item_id].append(item_location)
    physical_locations = {location.id: location for location in db.scalars(select(InventoryLocation)).all()}
    active_physical_location_ids = {location.id for location in physical_locations.values() if location.active}
    locations: dict[tuple[str, str], list[InventoryLocation]] = defaultdict(list)
    for location in physical_locations.values():
        if not location.active:
            continue
        for name in {location.location_code, location.location_name}:
            if name:
                locations[(normalize_identifier(location.warehouse), normalize_identifier(name))].append(location)
    movement_item_ids = set(db.scalars(select(StockMovement.inventory_item_id).where(StockMovement.inventory_item_id.in_([item.id for item in items])).distinct()).all()) if outcome == "starting_inventory" and items else set()
    allow_blank_clears = bool((preview.options_json or {}).get("allow_blank_clears"))

    for row in rows:
        raw_values = mapped_rows[row.id]
        row_issues: list[dict[str, Any]] = []
        parsed: dict[str, Any] = {}
        for spec in fields:
            raw = raw_values.get(spec["key"], "")
            if spec["key"] in required and str(raw or "").strip() == "":
                row_issues.append(issue("required_value", spec["key"], f"Row {row.row_number}: {spec['label']} is required.", raw, f"Enter a value for {spec['label']}."))
                continue
            parsed[spec["key"]] = parse_typed(spec, raw, row.row_number, row_issues)

        sku_key = normalize_identifier(parsed.get("sku"))
        barcode_key = normalize_identifier(parsed.get("barcode"))
        stock_scope = (sku_key, normalize_identifier(parsed.get("warehouse")), normalize_identifier(parsed.get("inventory_location")))
        if outcome == "update_stock" and sku_key and stock_scope_counts[stock_scope] > 1:
            row_issues.append(issue("duplicate_stock_location_in_file", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} and this inventory location appear more than once in this file.", parsed.get("sku"), "Keep one stock value for each SKU and inventory location."))
        elif outcome != "update_stock" and sku_key and sku_counts[sku_key] > 1 and not (outcome == "repair_items" and parsed.get("item_id") is not None):
            row_issues.append(issue("duplicate_sku_in_file", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} appears more than once in this file.", parsed.get("sku"), "Keep one row for this item."))
        if barcode_key and barcode_counts[barcode_key] > 1:
            row_issues.append(issue("duplicate_barcode_in_file", "barcode", f"Row {row.row_number}: Barcode {parsed.get('barcode')!r} appears more than once in this file.", parsed.get("barcode"), "Correct or remove the duplicate barcode."))

        matches = by_sku.get(sku_key, []) if sku_key else []
        item = matches[0] if len(matches) == 1 else None
        match_method = "sku" if item is not None else None
        if outcome == "repair_items":
            item_id = parsed.get("item_id")
            if item_id is not None and item_id <= 0:
                row_issues.append(issue("invalid_item_id", "item_id", f"Row {row.row_number}: Pongo Item ID must be greater than zero.", item_id, "Use a valid Pongo Item ID or leave it blank and provide SKU."))
                item = None
            elif item_id is not None:
                item = items_by_id.get(item_id)
                match_method = "pongo_item_id" if item is not None else None
                if item is None:
                    row_issues.append(issue("item_id_not_found", "item_id", f"Pongo Item ID {item_id!r} was not found.", item_id, "Export a fresh repair template and use its Pongo Item ID."))
                elif sku_key and normalize_identifier(item.sku) != sku_key:
                    row_issues.append(issue("identity_mismatch", "sku", f"Row {row.row_number}: Pongo Item ID {item_id} belongs to SKU {item.sku!r}, not {parsed.get('sku')!r}.", parsed.get("sku"), "Use the SKU exported for this Pongo Item ID."))
            elif not sku_key:
                item = None
                row_issues.append(issue("item_identity_required", "item_id", f"Row {row.row_number}: Pongo Item ID or SKU is required.", None, "Provide Pongo Item ID or SKU."))
            elif len(matches) > 1:
                item = None
                row_issues.append(issue("ambiguous_sku", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} matches multiple existing items.", parsed.get("sku"), "Use Pongo Item ID to identify this item."))
            elif not matches:
                item = None
                row_issues.append(issue("sku_not_found", "sku", f"SKU {parsed.get('sku')!r} was not found in Pongo OS.", parsed.get("sku"), "Export a fresh repair template and use Pongo Item ID."))
            if item is not None:
                for key, attribute, label in (
                    ("woo_product_id", "woo_product_id", "Woo product ID"),
                    ("woo_variation_id", "woo_variation_id", "Woo variation ID"),
                ):
                    if parsed.get(key) is not None and parsed.get(key) != getattr(item, attribute):
                        row_issues.append(issue("woo_identity_mismatch", key, f"Row {row.row_number}: {label} does not match Pongo Item ID {item.id}.", parsed.get(key), "Export a fresh repair template and keep its identity columns unchanged."))
        else:
            if len(matches) > 1:
                row_issues.append(issue("ambiguous_sku", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} matches multiple existing items.", parsed.get("sku"), "Resolve the duplicate SKU in Items before importing."))
            if outcome == "add_items" and item is not None:
                row_issues.append(issue("sku_already_exists", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} already exists in Pongo OS.", parsed.get("sku"), "Exclude this row or use Update item details."))
            if outcome in {"update_items", "starting_inventory", "update_stock"} and sku_key and not matches:
                row_issues.append(issue("sku_not_found", "sku", f"SKU {parsed.get('sku')!r} was not found in Pongo OS.", parsed.get("sku"), "This SKU will be skipped; add it to Items first if Pongo should manage it.", blocking=outcome != "update_stock"))

        if barcode_key:
            barcode_matches = by_barcode.get(barcode_key, [])
            if any(candidate.id != getattr(item, "id", None) for candidate in barcode_matches):
                row_issues.append(issue("barcode_already_exists", "barcode", f"Row {row.row_number}: Barcode {parsed.get('barcode')!r} belongs to another item.", parsed.get("barcode"), "Enter a unique barcode or leave it blank."))

        changes: dict[str, dict[str, Any]] = {}
        relevant_attributes: list[str] = []
        if outcome == "repair_items":
            relevant_attributes = list(REPAIR_HASH_ATTRIBUTES)
            if item is not None:
                if not item.active or item.non_inventory:
                    row_issues.append(issue("repair_item_ineligible", "item_id", f"Row {row.row_number}: only active inventory items can be repaired.", item.id, "Remove inactive or non-inventory items from the repair file."))
                for key, attribute, label in (("brand", "brand", "Brand"), ("unit_cost", "unit_cost", "Unit cost")):
                    if str(raw_values.get(key, "") or "").strip() and not values_equal(getattr(item, attribute), parsed.get(key)):
                        changes[attribute] = {"field": key, "label": label, "before": serializable(getattr(item, attribute)), "after": serializable(parsed.get(key))}

                warehouse = parsed.get("warehouse")
                location_name = parsed.get("inventory_location")
                target_matches = locations.get((normalize_identifier(warehouse), normalize_identifier(location_name)), []) if warehouse and location_name else []
                if warehouse and location_name and len(target_matches) != 1:
                    row_issues.append(issue("invalid_location", "inventory_location", f"Row {row.row_number}: {warehouse} / {location_name} does not match one active inventory location.", location_name, "Choose one active physical location from Pongo OS."))
                if len(target_matches) == 1:
                    target = target_matches[0]
                    assignments = item_locations_by_item.get(item.id, [])
                    active_assignments = [candidate for candidate in assignments if candidate.active]
                    inactive_with_balances = [candidate for candidate in assignments if not candidate.active and has_location_balances(candidate)]
                    if inactive_with_balances:
                        row_issues.append(issue("inactive_location_has_inventory", "inventory_location", f"Row {row.row_number}: this item has inventory on an inactive assignment.", None, "Reconcile the inactive assignment before running repair."))
                    invalid_assignment = next(
                        (
                            candidate
                            for candidate in active_assignments
                            if candidate.location_id not in active_physical_location_ids
                            or Decimal(candidate.in_stock or 0) < 0
                            or Decimal(candidate.allocated or 0) < 0
                            or Decimal(candidate.allocated or 0) > Decimal(candidate.in_stock or 0)
                            or Decimal(candidate.sellable or 0) != Decimal(candidate.in_stock or 0) - Decimal(candidate.allocated or 0)
                            or Decimal(candidate.on_order or 0) < 0
                        ),
                        None,
                    )
                    if invalid_assignment is not None:
                        row_issues.append(issue("invalid_location_inventory", "inventory_location", f"Row {row.row_number}: an active assignment is missing an active physical location or has inconsistent balances.", invalid_assignment.inventory_location, "Reconcile this item before running repair."))
                    if active_assignments:
                        active_totals = {
                            key: sum((Decimal(getattr(candidate, key) or 0) for candidate in active_assignments), Decimal("0"))
                            for key in ("in_stock", "allocated", "sellable", "on_order")
                        }
                        if any(active_totals[key] != Decimal(getattr(item, key) or 0) for key in active_totals):
                            row_issues.append(issue("location_total_mismatch", "inventory_location", f"Row {row.row_number}: item totals do not equal its active location totals.", None, "Reconcile this item before running repair."))
                    elif Decimal(item.allocated or 0) > Decimal(item.in_stock or 0) or Decimal(item.sellable or 0) != Decimal(item.in_stock or 0) - Decimal(item.allocated or 0) or Decimal(item.on_order or 0) < 0:
                        row_issues.append(issue("item_total_mismatch", "inventory_location", f"Row {row.row_number}: item totals are internally inconsistent.", None, "Reconcile this item before running repair."))

                    target_assignment = next((candidate for candidate in assignments if candidate.location_id == target.id), None)
                    sources = [candidate for candidate in active_assignments if candidate.id != getattr(target_assignment, "id", None)]
                    deferred_units = sum((Decimal(candidate.allocated or 0) for candidate in sources), Decimal("0"))
                    movable_units = sum((Decimal(candidate.in_stock or 0) - Decimal(candidate.allocated or 0) for candidate in sources), Decimal("0"))
                    on_order_units = sum((Decimal(candidate.on_order or 0) for candidate in sources), Decimal("0"))
                    deferred_count = sum(1 for candidate in sources if Decimal(candidate.allocated or 0) > 0)
                    target_name = target.location_code or target.location_name
                    if not values_equal(item.warehouse, target.warehouse):
                        changes["warehouse"] = {"field": "warehouse", "label": "Target warehouse", "before": item.warehouse, "after": target.warehouse}
                    if not values_equal(item.inventory_location, target_name):
                        changes["inventory_location"] = {"field": "inventory_location", "label": "Target inventory location", "before": item.inventory_location, "after": target_name}
                    needs_consolidation = bool(
                        target_assignment is None
                        or not target_assignment.active
                        or not target_assignment.is_default_location
                        or sources
                    )
                    if needs_consolidation:
                        changes["location_repair"] = {
                            "field": "inventory_location",
                            "label": "Location consolidation",
                            "before": f"{len(active_assignments)} active assignment(s)",
                            "after": f"{target.warehouse} / {target_name}",
                        }
                    if deferred_units:
                        row_issues.append(issue("allocated_stock_deferred", "inventory_location", f"Row {row.row_number}: {serializable(deferred_units)} allocated unit(s) will remain reserved at {deferred_count} source location(s).", deferred_units, "Run repair again after those orders release or consume their allocations.", blocking=False))
                    parsed["_repair_plan"] = {
                        "target_location_id": target.id,
                        "target_warehouse": target.warehouse,
                        "target_inventory_location": target_name,
                        "target_assignment_id": target_assignment.id if target_assignment else None,
                        "source_assignment_ids": [candidate.id for candidate in sources],
                        "location_snapshot": location_snapshot(item, assignments, physical_locations),
                        "target_location_snapshot": physical_location_snapshot(target),
                        "needs_consolidation": needs_consolidation,
                        "units_relocated": serializable(movable_units),
                        "on_order_units_relocated": serializable(on_order_units),
                        "deferred_location_count": deferred_count,
                        "deferred_units": serializable(deferred_units),
                    }
        elif outcome in METADATA_OUTCOMES:
            for spec in fields:
                attribute = spec["attribute"]
                if not attribute or spec["key"] == "sku" and outcome == "update_items":
                    continue
                raw = raw_values.get(spec["key"], "")
                blank = str(raw or "").strip() == ""
                if blank and outcome == "update_items" and not allow_blank_clears:
                    continue
                if blank and outcome == "add_items":
                    continue
                incoming = parsed.get(spec["key"])
                if blank and allow_blank_clears and spec["nullable"]:
                    incoming = None
                current = getattr(item, attribute, None) if item is not None else None
                if item is None or not values_equal(current, incoming):
                    changes[attribute] = {"field": spec["key"], "label": spec["label"], "before": serializable(current), "after": serializable(incoming)}
                    relevant_attributes.append(attribute)

            warehouse = parsed.get("warehouse") or (item.warehouse if item is not None else None)
            location_name = parsed.get("inventory_location") or parsed.get("default_location") or (item.inventory_location if item is not None else None)
            location_requested = any(str(raw_values.get(key, "") or "").strip() for key in ["warehouse", "inventory_location", "default_location"])
            if location_requested:
                if not warehouse or not location_name:
                    row_issues.append(issue("incomplete_location", "inventory_location", f"Row {row.row_number}: Warehouse and inventory location are both required when assigning a location.", location_name, "Choose an active warehouse and location."))
                elif len(locations.get((normalize_identifier(warehouse), normalize_identifier(location_name)), [])) != 1:
                    row_issues.append(issue("invalid_location", "inventory_location", f"Row {row.row_number}: {warehouse} / {location_name} does not match one active inventory location.", location_name, "Choose an active warehouse and location from Pongo OS."))
        elif outcome == "starting_inventory":
            quantity = parsed.get("starting_quantity")
            warehouse = parsed.get("starting_warehouse")
            location_name = parsed.get("starting_location")
            if warehouse and location_name and len(locations.get((normalize_identifier(warehouse), normalize_identifier(location_name)), [])) != 1:
                row_issues.append(issue("invalid_location", "starting_location", f"Row {row.row_number}: {warehouse} / {location_name} does not match one active inventory location.", location_name, "Choose an active warehouse and location from Pongo OS."))
            if item is not None:
                if Decimal(item.in_stock or 0) != 0 or Decimal(item.allocated or 0) != 0 or item.id in movement_item_ids:
                    row_issues.append(issue("starting_inventory_ineligible", "starting_quantity", f"Row {row.row_number}: Starting inventory is blocked because this item already has operational stock or stock history.", quantity, "Use receiving, cycle count, or an audited adjustment instead."))
                changes = {
                    "in_stock": {"field": "starting_quantity", "label": "On hand", "before": serializable(item.in_stock), "after": serializable(quantity)},
                    "location": {"field": "starting_location", "label": "Destination", "before": None, "after": f"{warehouse} / {location_name}" if warehouse and location_name else None},
                }
                relevant_attributes = ["in_stock", "allocated"]
        else:
            quantity = parsed.get("stock_quantity")
            if quantity is not None and quantity < 0:
                row_issues.append(issue("negative_stock", "stock_quantity", f"Row {row.row_number}: In stock cannot be negative.", quantity, "Enter zero or a positive physical count."))
            if item is not None and quantity is not None:
                candidates = item_locations_by_item.get(item.id, [])
                current = sum((Decimal(candidate.in_stock or 0) for candidate in candidates), Decimal("0")) if candidates else Decimal(item.in_stock or 0)
                allocated = sum((Decimal(candidate.allocated or 0) for candidate in candidates), Decimal("0")) if candidates else Decimal(item.allocated or 0)
                targets: list[dict[str, Any]] = []
                if Decimal(item.in_stock or 0) != current:
                    row_issues.append(issue("stock_total_mismatch", "stock_quantity", f"SKU {item.sku!r} has inconsistent item and location totals.", quantity, "Reconcile this item before importing stock."))
                elif Decimal(item.allocated or 0) != allocated:
                    row_issues.append(issue("stock_allocation_mismatch", "stock_quantity", f"SKU {item.sku!r} has inconsistent item and location allocations.", quantity, "Reconcile this item before importing stock."))
                elif any(candidate.location_id and candidate.location_id not in active_physical_location_ids for candidate in candidates):
                    row_issues.append(issue("inactive_stock_location", "stock_quantity", f"SKU {item.sku!r} is assigned to an inactive or missing physical location.", quantity, "Reactivate or replace the inventory location, then preview again."))
                elif quantity < allocated:
                    row_issues.append(issue("stock_below_allocated", "stock_quantity", f"SKU {item.sku!r} cannot be set to {serializable(quantity)} because {serializable(allocated)} unit(s) are allocated to open orders.", quantity, "Complete or unallocate those orders, then preview this CSV again."))
                elif not candidates and current != quantity:
                    row_issues.append(issue("item_location_not_found", "stock_quantity", f"SKU {item.sku!r} has no active inventory assignment where stock can be changed.", quantity, "Assign the item to an active location, then preview again."))
                elif candidates:
                    targets = stock_total_targets(candidates, quantity)
                parsed["_stock_targets"] = targets
                parsed["_expected_item_quantity"] = serializable(item.in_stock or 0)
                parsed["_expected_item_allocated"] = serializable(item.allocated or 0)
                if not row_issues and current != quantity:
                    variance = quantity - current
                    changes = {
                        "in_stock": {"field": "stock_quantity", "label": "Total in stock", "before": serializable(current), "after": serializable(quantity)},
                        "variance": {"field": "stock_quantity", "label": "Total variance", "before": 0, "after": serializable(variance)},
                    }
                relevant_attributes = ["in_stock", "allocated"]

        blocking_issues = [candidate for candidate in row_issues if candidate.get("blocking", True)]
        if row.excluded:
            state = "excluded"
        elif blocking_issues:
            codes = {candidate["code"] for candidate in blocking_issues}
            state = "duplicate" if any("duplicate" in code or "already_exists" in code or "ambiguous" in code for code in codes) else ("unmatched" if codes & {"sku_not_found", "item_id_not_found", "item_identity_required"} else ("blocked" if "starting_inventory_ineligible" in codes else "needs_attention"))
        elif outcome == "repair_items":
            state = "will_update" if changes else "no_changes"
        elif row_issues:
            state = "skipped"
        elif outcome == "add_items":
            state = "will_create"
        elif outcome in {"update_items", "update_stock"}:
            state = "will_update" if changes else "no_changes"
        else:
            state = "will_update"

        row.sku = str(parsed.get("sku") or getattr(item, "sku", "") or "") or None
        row.barcode = None if outcome == "repair_items" else (str(parsed.get("barcode") or "") or None)
        row.product_name = (str(parsed.get("product_name") or (item.woo_name if item is not None else "") or (item.description if item is not None else "") or "")[:500] or None)
        row.normalized_data = {key: serializable(value) for key, value in parsed.items()}
        row.existing_item_id = item.id if item is not None else None
        row.source_item_hash = item_value_hash(item, relevant_attributes) if item is not None else None
        row.proposed_changes = changes
        row.issues_json = row_issues
        row.state = state
        row.match_method = match_method if item is not None else None

    if outcome == "update_stock":
        rows_by_target: dict[int, list[ImportPreviewRow]] = defaultdict(list)
        for row in rows:
            for target_id in {int(target["inventory_item_location_id"]) for target in stock_targets(row) if target.get("inventory_item_location_id")}:
                rows_by_target[target_id].append(row)
        for target_rows in rows_by_target.values():
            if len(target_rows) < 2:
                continue
            for row in target_rows:
                row.issues_json = [*(row.issues_json or []), issue("duplicate_stock_target_in_file", "inventory_location", f"Row {row.row_number}: Another CSV row resolves to the same inventory location for SKU {row.sku!r}.", None, "Keep one row for each SKU and inventory location.")]
                row.proposed_changes = {}
                if not row.excluded:
                    row.state = "duplicate"
    elif outcome == "repair_items":
        rows_by_item: dict[int, list[ImportPreviewRow]] = defaultdict(list)
        for row in rows:
            if row.existing_item_id:
                rows_by_item[row.existing_item_id].append(row)
        for matched_rows in rows_by_item.values():
            if len(matched_rows) < 2:
                continue
            for row in matched_rows:
                row.issues_json = [*(row.issues_json or []), issue("duplicate_item_in_file", "item_id", f"Row {row.row_number}: another CSV row resolves to the same Pongo item.", row.existing_item_id, "Keep one repair row per Pongo item.")]
                row.proposed_changes = {}
                if not row.excluded:
                    row.state = "duplicate"

    counts = Counter(row.state for row in rows)
    starting_units = sum((Decimal(str(row.normalized_data.get("starting_quantity") or 0)) for row in rows if row.state == "will_update" and outcome == "starting_inventory"), Decimal("0"))
    valuation = sum((Decimal(str(row.normalized_data.get("starting_quantity") or 0)) * Decimal(str((items_by_id.get(row.existing_item_id).unit_cost if items_by_id.get(row.existing_item_id) else 0) or 0)) for row in rows if row.state == "will_update" and outcome == "starting_inventory"), Decimal("0"))
    stock_units_delta = sum((Decimal(str((row.proposed_changes or {}).get("variance", {}).get("after") or 0)) for row in rows if row.state == "will_update" and outcome == "update_stock"), Decimal("0"))
    repair_plans = [(row.normalized_data or {}).get("_repair_plan") or {} for row in rows if row.state in {"will_update", "no_changes"} and outcome == "repair_items"]
    preview.summary_json = {
        **(preview.summary_json or {}),
        "total_rows": len(rows),
        "source_row_count": (preview.options_json or {}).get("source_row_count", len(rows)),
        "sku_count": len(rows) if outcome == "update_stock" else None,
        "ready_count": counts["will_create"] + counts["will_update"],
        "create_count": counts["will_create"],
        "update_count": counts["will_update"],
        "no_changes_count": counts["no_changes"],
        "needs_attention_count": counts["needs_attention"],
        "duplicate_count": counts["duplicate"],
        "unmatched_count": counts["unmatched"],
        "skipped_count": counts["skipped"],
        "blocked_count": counts["blocked"],
        "blocking_count": sum(counts[state] for state in ISSUE_STATES) + (counts["excluded"] if outcome in {"update_stock", "repair_items"} else 0),
        "excluded_count": counts["excluded"],
        "missing_required_mappings": missing_mapping,
        "starting_units": serializable(starting_units),
        "estimated_valuation": serializable(valuation),
        "stock_units_delta": serializable(stock_units_delta),
        "consolidate_count": sum(1 for plan in repair_plans if plan.get("needs_consolidation")),
        "deferred_location_count": sum(int(plan.get("deferred_location_count") or 0) for plan in repair_plans),
        "deferred_units": serializable(sum((Decimal(str(plan.get("deferred_units") or 0)) for plan in repair_plans), Decimal("0"))),
        "units_relocated": serializable(sum((Decimal(str(plan.get("units_relocated") or 0)) for plan in repair_plans), Decimal("0"))),
    }
    preview.status = "draft" if missing_mapping else "ready"
    db.flush()
    return preview


def preview_detail(preview: ImportPreview, db: Session) -> dict[str, Any]:
    profile = db.scalars(select(ImportMappingProfile).where(ImportMappingProfile.created_by == preview.created_by, ImportMappingProfile.outcome == preview.outcome, ImportMappingProfile.source_signature == source_signature(preview.source_headers)).order_by(ImportMappingProfile.updated_at.desc())).first()
    return {
        "preview_id": preview.id,
        "outcome": preview.outcome,
        "outcome_content": OUTCOME_CONTENT[preview.outcome],
        "file": {"name": preview.file_name, "size": (preview.options_json or {}).get("file_size"), "encoding": (preview.options_json or {}).get("encoding"), "delimiter": (preview.options_json or {}).get("delimiter"), "sha256": preview.file_sha256, "row_count": (preview.options_json or {}).get("source_row_count", (preview.summary_json or {}).get("total_rows")), "header_count": len(preview.source_headers)},
        "schema_version": preview.schema_version,
        "source_columns": preview.source_columns_json,
        "mapping": preview.mapping_json,
        "options": preview.options_json,
        "summary": preview.summary_json,
        "status": preview.status,
        "created_by": preview.created_by,
        "created_at": preview.created_at,
        "expires_at": preview.expires_at,
        "import_job_id": preview.import_job_id,
        "result": preview.result_json,
        "suggested_profile": mapping_profile_dict(profile) if profile else None,
    }


def preview_rows_page(preview: ImportPreview, db: Session, *, page: int = 1, page_size: int = 50, state: str | None = None, search: str | None = None) -> dict[str, Any]:
    statement = select(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id)
    if state:
        statement = statement.where(ImportPreviewRow.state == state)
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(or_(ImportPreviewRow.sku.ilike(term), ImportPreviewRow.barcode.ilike(term), ImportPreviewRow.product_name.ilike(term)))
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    safe_page_size = max(1, min(page_size, 100))
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    safe_page = min(max(1, page), max(total_pages, 1))
    rows = list(db.scalars(statement.order_by(ImportPreviewRow.row_number).offset((safe_page - 1) * safe_page_size).limit(safe_page_size)).all())
    return {
        "rows": [preview_row_dict(row) for row in rows],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": total_pages,
    }


def preview_row_dict(row: ImportPreviewRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "row_number": row.row_number,
        "sku": row.sku,
        "barcode": row.barcode,
        "product_name": row.product_name,
        "source_data": row.source_data,
        "normalized_data": row.normalized_data,
        "corrected_data": row.corrected_data,
        "existing_item_id": row.existing_item_id,
        "proposed_changes": row.proposed_changes,
        "issues": row.issues_json,
        "state": row.state,
        "match_method": row.match_method,
        "excluded": row.excluded,
    }


def update_mapping(preview: ImportPreview, db: Session, mapping: dict[str, str | None], *, allow_blank_clears: bool = False, mapping_profile_id: int | None = None) -> ImportPreview:
    expected_sources = set(preview.source_headers)
    if set(mapping) != expected_sources:
        raise HTTPException(status_code=422, detail={"code": "invalid_mapping", "message": "The mapping must include every uploaded CSV column."})
    allowed_destinations = {spec["key"] for spec in field_specs_for(preview.outcome)}
    invalid = sorted({destination for destination in mapping.values() if destination and destination not in allowed_destinations})
    destinations = [destination for destination in mapping.values() if destination]
    duplicates = sorted({destination for destination, count in Counter(destinations).items() if count > 1})
    if invalid or duplicates:
        raise HTTPException(status_code=422, detail={"code": "invalid_mapping", "message": "Each supported Pongo OS field can be mapped once.", "invalid_fields": invalid, "duplicate_fields": duplicates})
    if preview.outcome == "update_stock" and mapping != (preview.mapping_json or {}):
        replace_stock_preview_rows(preview, db, mapping)
    preview.mapping_json = mapping
    preview.options_json = {**(preview.options_json or {}), "allow_blank_clears": bool(allow_blank_clears), "mapping_profile_id": mapping_profile_id}
    revalidate_preview(preview, db)
    db.commit()
    db.refresh(preview)
    return preview


def update_preview_row(preview: ImportPreview, row_number: int, db: Session, *, values: dict[str, Any] | None = None, excluded: bool | None = None) -> ImportPreviewRow:
    row = db.scalars(select(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id, ImportPreviewRow.row_number == row_number)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "preview_row_not_found", "message": f"CSV row {row_number} was not found in this preview."})
    allowed = {spec["key"] for spec in field_specs_for(preview.outcome)}
    if values is not None:
        invalid = sorted(set(values) - allowed)
        if invalid:
            raise HTTPException(status_code=422, detail={"code": "invalid_correction", "message": "One or more corrected fields are not supported.", "fields": invalid})
        row.corrected_data = {**(row.corrected_data or {}), **values}
    if excluded is not None:
        row.excluded = excluded
    db.flush()
    revalidate_preview(preview, db)
    db.commit()
    db.refresh(row)
    return row


def cancel_preview(preview: ImportPreview, db: Session) -> ImportPreview:
    preview = db.scalar(
        select(ImportPreview)
        .where(ImportPreview.id == preview.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if preview.status == "committed":
        raise HTTPException(status_code=409, detail={"code": "preview_already_committed", "message": "A completed import cannot be cancelled."})
    if preview.status == "running":
        raise HTTPException(status_code=409, detail={"code": "preview_commit_running", "message": "This repair is already queued and cannot be cancelled while the worker is applying it."})
    preview.status = "cancelled"
    db.commit()
    return preview


def mapping_profile_dict(profile: ImportMappingProfile) -> dict[str, Any]:
    return {"id": profile.id, "name": profile.name, "outcome": profile.outcome, "source_signature": profile.source_signature, "source_headers": profile.source_headers, "mapping": profile.mapping_json, "created_by": profile.created_by, "created_at": profile.created_at, "updated_at": profile.updated_at}


def list_mapping_profiles(db: Session, actor: str, *, outcome: str | None = None) -> list[dict[str, Any]]:
    statement = select(ImportMappingProfile).where(ImportMappingProfile.created_by == actor)
    if outcome:
        statement = statement.where(ImportMappingProfile.outcome == outcome)
    return [mapping_profile_dict(profile) for profile in db.scalars(statement.order_by(ImportMappingProfile.name)).all()]


def create_mapping_profile(db: Session, actor: str, *, name: str, outcome: str, source_headers: list[str], mapping: dict[str, str | None]) -> ImportMappingProfile:
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail={"code": "profile_name_required", "message": "Enter a name for this mapping profile."})
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail={"code": "invalid_outcome", "message": "This mapping profile has an unsupported import outcome."})
    existing = db.scalars(select(ImportMappingProfile).where(ImportMappingProfile.created_by == actor, ImportMappingProfile.outcome == outcome, func.lower(ImportMappingProfile.name) == clean_name.casefold())).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail={"code": "profile_name_exists", "message": "A mapping profile with this name already exists."})
    profile = ImportMappingProfile(name=clean_name[:160], outcome=outcome, source_signature=source_signature(source_headers), source_headers=source_headers, mapping_json=mapping, created_by=actor)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_mapping_profile(db: Session, actor: str, profile_id: int, payload: dict[str, Any]) -> ImportMappingProfile:
    profile = db.get(ImportMappingProfile, profile_id)
    if profile is None or profile.created_by != actor:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found", "message": "Mapping profile not found."})
    if "name" in payload:
        profile.name = str(payload["name"]).strip()[:160]
    if "mapping" in payload:
        profile.mapping_json = payload["mapping"]
    db.commit()
    db.refresh(profile)
    return profile


def delete_mapping_profile(db: Session, actor: str, profile_id: int) -> None:
    profile = db.get(ImportMappingProfile, profile_id)
    if profile is None or profile.created_by != actor:
        raise HTTPException(status_code=404, detail={"code": "profile_not_found", "message": "Mapping profile not found."})
    db.delete(profile)
    db.commit()


def coerce_attribute(attribute: str, value: Any) -> Any:
    if value is None:
        return None
    spec = SPEC_BY_ATTRIBUTE[attribute]
    if spec["type"] == "decimal":
        return Decimal(str(value))
    if spec["type"] == "integer":
        return int(value)
    if spec["type"] == "boolean":
        return bool(value)
    return value


def resolve_location(db: Session, warehouse: str | None, location_name: str | None) -> InventoryLocation | None:
    if not warehouse or not location_name:
        return None
    return db.scalars(
        select(InventoryLocation).where(
            InventoryLocation.active.is_(True),
            func.lower(func.trim(InventoryLocation.warehouse)) == normalize_identifier(warehouse),
            or_(
                func.lower(func.trim(InventoryLocation.location_code)) == normalize_identifier(location_name),
                func.lower(func.trim(InventoryLocation.location_name)) == normalize_identifier(location_name),
            ),
        )
    ).one_or_none()


def record_job_error(job: ImportJob, row: ImportPreviewRow, db: Session, issue_data: dict[str, Any]) -> None:
    raw_row = dict(row.source_data or {})
    for spec in field_specs_for(job.outcome):
        value = (row.normalized_data or {}).get(spec["key"])
        if value is not None:
            raw_row[spec["label"]] = value
    db.add(
        ImportError(
            import_job_id=job.id,
            row_number=row.row_number,
            sku=row.sku,
            barcode=row.barcode,
            error_message=issue_data.get("message") or "This row was not imported.",
            error_code=issue_data.get("code"),
            field_name=issue_data.get("field"),
            invalid_value=issue_data.get("invalid_value"),
            blocking=bool(issue_data.get("blocking", True)),
            suggested_action=issue_data.get("suggested_action"),
            raw_row=raw_row,
        )
    )


def job_result(job: ImportJob) -> dict[str, Any]:
    if job.result_json:
        return job.result_json
    return {
        "import_job_id": job.id,
        "preview_id": job.preview_id,
        "outcome": job.outcome,
        "status": job.status,
        "total_rows": job.total_rows,
        "created_count": job.created_rows,
        "updated_count": job.updated_rows,
        "unchanged_count": job.unchanged_rows,
        "excluded_count": job.excluded_rows,
        "failed_count": job.failed_rows,
        "successful_count": job.successful_rows,
        "starting_units": serializable(job.starting_units),
        "duration_ms": job.duration_ms,
    }


def enqueue_repair_commit(
    preview: ImportPreview,
    db: Session,
    *,
    actor: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key or len(idempotency_key) > 120:
        raise HTTPException(status_code=422, detail={"code": "idempotency_key_required", "message": "A valid commit idempotency key is required."})
    if preview.outcome != "repair_items":
        raise ValueError("Only item repairs are queued by this workflow.")

    preview = db.scalar(
        select(ImportPreview)
        .where(ImportPreview.id == preview.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if preview is None:
        raise HTTPException(status_code=404, detail={"code": "preview_not_found", "message": "This import preview could not be found."})
    if preview.status == "committed":
        return preview.result_json or job_result(db.get(ImportJob, preview.import_job_id))
    if preview.status in {"cancelled", "expired"}:
        raise HTTPException(status_code=409, detail={"code": f"preview_{preview.status}", "message": f"This import preview is {preview.status}. Create a new preview before importing."})
    if preview.import_job_id:
        existing_job = db.get(ImportJob, preview.import_job_id)
        if existing_job is not None:
            return job_result(existing_job)
    if preview.status != "ready":
        raise HTTPException(status_code=409, detail={"code": "preview_not_ready", "message": "Finish matching the required columns before importing."})

    blocking_count = int((preview.summary_json or {}).get("blocking_count") or 0)
    if blocking_count:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "repair_import_not_ready",
                "message": "No item was changed. Fix every blocked repair row, then preview the whole file again.",
                "blocking_count": blocking_count,
            },
        )
    existing_key = db.scalar(select(ImportJob).where(ImportJob.idempotency_key == idempotency_key))
    if existing_key is not None:
        if existing_key.preview_id == preview.id:
            return job_result(existing_key)
        raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict", "message": "This commit key was already used for another import."})

    job = ImportJob(
        file_name=preview.file_name,
        import_type="items_repair_items",
        file_sha256=preview.file_sha256,
        preview_id=preview.id,
        outcome=preview.outcome,
        idempotency_key=idempotency_key,
        options_json=preview.options_json,
        total_rows=int((preview.summary_json or {}).get("total_rows") or 0),
        successful_rows=0,
        failed_rows=0,
        status="queued",
        created_by=actor,
    )
    db.add(job)
    db.flush()
    preview.import_job_id = job.id
    preview.commit_idempotency_key = idempotency_key
    preview.status = "running"
    db.commit()
    logger.info(json.dumps({"event": "item_repair_commit_queued", "preview_id": preview.id, "import_job_id": job.id, "rows": job.total_rows}))
    return job_result(job)


def failed_repair_job_result(job: ImportJob, *, code: str, message: str, duration_ms: int) -> dict[str, Any]:
    return {
        "import_job_id": job.id,
        "preview_id": job.preview_id,
        "outcome": "repair_items",
        "status": "failed",
        "total_rows": job.total_rows,
        "successful_count": 0,
        "created_count": 0,
        "updated_count": 0,
        "unchanged_count": 0,
        "excluded_count": 0,
        "failed_count": job.total_rows,
        "starting_units": 0,
        "duration_ms": duration_ms,
        "code": code,
        "message": message,
    }


def process_next_item_import_job(*, db_factory=SessionLocal) -> dict[str, Any] | None:
    with db_factory() as db:
        job = db.scalar(
            select(ImportJob)
            .where(ImportJob.outcome == "repair_items", ImportJob.status == "queued")
            .order_by(ImportJob.created_at, ImportJob.id)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return None
        started = perf_counter()
        preview = db.scalar(select(ImportPreview).where(ImportPreview.id == job.preview_id).with_for_update())
        if preview is not None and preview.import_job_id == job.id:
            try:
                with db.begin_nested():
                    result = commit_preview(
                        preview,
                        db,
                        actor=job.created_by or "system",
                        idempotency_key=job.idempotency_key or f"repair-job:{job.id}",
                        commit_transaction=False,
                    )
                db.commit()
                return result
            except Exception as exc:
                detail = exc.detail if isinstance(exc, HTTPException) else None
                code = str(detail.get("code") or "repair_worker_failed") if isinstance(detail, dict) else "repair_worker_failed"
                message = str(detail.get("message") or "The repair could not be completed. No item or location changes were saved.") if isinstance(detail, dict) else "The repair could not be completed. No item or location changes were saved."
                logger.exception(json.dumps({"event": "item_repair_worker_failed", "preview_id": preview.id, "import_job_id": job.id, "code": code}))
        else:
            code = "repair_preview_unavailable"
            message = "The queued repair preview is no longer available. No item or location changes were saved."

        duration_ms = round((perf_counter() - started) * 1000)
        job.status = "failed"
        job.successful_rows = 0
        job.failed_rows = job.total_rows
        job.duration_ms = duration_ms
        job.completed_at = utcnow()
        result = failed_repair_job_result(job, code=code, message=message, duration_ms=duration_ms)
        job.result_json = result
        if preview is not None and preview.import_job_id == job.id:
            if preview.status not in {"cancelled", "expired"}:
                preview.status = "ready"
            preview.import_job_id = None
            preview.commit_idempotency_key = None
            preview.result_json = None
        db.commit()
        return result


def stock_targets(row: ImportPreviewRow) -> list[dict[str, Any]]:
    data = row.normalized_data or {}
    targets = data.get("_stock_targets")
    if isinstance(targets, list):
        return targets
    location_id = data.get("_inventory_item_location_id")
    if not location_id:
        return []
    return [{
        "inventory_item_location_id": location_id,
        "expected_quantity": data.get("_expected_quantity", 0),
        "new_quantity": data.get("stock_quantity", 0),
    }]


def stale_rows(preview: ImportPreview, rows: list[ImportPreviewRow], db: Session) -> list[int]:
    stale: list[int] = []
    ready_rows = [row for row in rows if row.state in READY_STATES | {"no_changes"}]
    if preview.outcome == "add_items":
        normalized_skus = {normalize_identifier(row.sku) for row in ready_rows if row.sku}
        normalized_barcodes = {normalize_identifier(row.barcode) for row in ready_rows if row.barcode}
        sku_expression = func.lower(func.trim(InventoryItem.sku))
        barcode_expression = func.lower(func.trim(InventoryItem.barcode))
        existing_skus = (
            set(db.scalars(select(sku_expression).where(sku_expression.in_(normalized_skus))).all())
            if normalized_skus
            else set()
        )
        existing_barcodes = (
            set(db.scalars(select(barcode_expression).where(barcode_expression.in_(normalized_barcodes))).all())
            if normalized_barcodes
            else set()
        )
        return [
            row.row_number
            for row in ready_rows
            if normalize_identifier(row.sku) in existing_skus
            or (row.barcode and normalize_identifier(row.barcode) in existing_barcodes)
        ]

    items_by_id: dict[int, InventoryItem] = {}
    locations_by_id: dict[int, InventoryItemLocation] = {}
    locations_by_item: dict[int, list[InventoryItemLocation]] = defaultdict(list)
    physical_locations: dict[int, InventoryLocation] = {}
    active_location_ids_by_item: dict[int, set[int]] = defaultdict(set)
    active_physical_location_ids: set[int] = set()
    if ready_rows:
        item_ids = {row.existing_item_id for row in ready_rows if row.existing_item_id}
        items_by_id = {item.id: item for item in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids))).all()} if item_ids else {}
        if preview.outcome == "update_stock":
            active_locations = list(db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id.in_(item_ids), InventoryItemLocation.active.is_(True))).all()) if item_ids else []
            locations_by_id = {location.id: location for location in active_locations}
            physical_location_ids = {location.location_id for location in active_locations if location.location_id}
            active_physical_location_ids = set(db.scalars(select(InventoryLocation.id).where(InventoryLocation.id.in_(physical_location_ids), InventoryLocation.active.is_(True))).all()) if physical_location_ids else set()
            for location in active_locations:
                active_location_ids_by_item[location.inventory_item_id].add(location.id)
        elif preview.outcome == "repair_items":
            item_locations = list(db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id.in_(item_ids))).all()) if item_ids else []
            for location in item_locations:
                locations_by_item[location.inventory_item_id].append(location)
            physical_ids = {location.location_id for location in item_locations if location.location_id}
            physical_ids.update(
                int(plan["target_location_id"])
                for row in ready_rows
                if (plan := (row.normalized_data or {}).get("_repair_plan") or {}).get("target_location_id")
            )
            physical_locations = {location.id: location for location in db.scalars(select(InventoryLocation).where(InventoryLocation.id.in_(physical_ids))).all()} if physical_ids else {}

    for row in ready_rows:
        item = items_by_id.get(row.existing_item_id)
        if item is None:
            stale.append(row.row_number)
            continue
        if preview.outcome == "update_stock":
            expected_item = (row.normalized_data or {}).get("_expected_item_quantity")
            expected_item_allocated = (row.normalized_data or {}).get("_expected_item_allocated")
            targets = stock_targets(row)
            if expected_item is not None and Decimal(item.in_stock or 0) != Decimal(str(expected_item)):
                stale.append(row.row_number)
                continue
            if expected_item_allocated is not None and Decimal(item.allocated or 0) != Decimal(str(expected_item_allocated)):
                stale.append(row.row_number)
                continue
            if {int(target["inventory_item_location_id"]) for target in targets if target.get("inventory_item_location_id")} != active_location_ids_by_item[item.id]:
                stale.append(row.row_number)
                continue
            for target in targets:
                item_location = locations_by_id.get(int(target["inventory_item_location_id"]))
                expected = Decimal(str(target.get("expected_quantity") or 0))
                expected_allocated = target.get("expected_allocated")
                if (
                    item_location is None
                    or not item_location.active
                    or item_location.inventory_item_id != item.id
                    or item_location.location_id != target.get("expected_location_id")
                    or item_location.location_id and item_location.location_id not in active_physical_location_ids
                    or Decimal(item_location.in_stock or 0) != expected
                    or expected_allocated is not None and Decimal(item_location.allocated or 0) != Decimal(str(expected_allocated))
                ):
                    stale.append(row.row_number)
                    break
            continue
        if preview.outcome == "repair_items":
            plan = (row.normalized_data or {}).get("_repair_plan") or {}
            if (
                plan.get("location_snapshot") != location_snapshot(item, locations_by_item.get(item.id, []), physical_locations)
                or plan.get("target_location_snapshot") != physical_location_snapshot(physical_locations.get(plan.get("target_location_id")))
            ):
                stale.append(row.row_number)
                continue
        attributes = [attribute for attribute in row.proposed_changes if attribute in SPEC_BY_ATTRIBUTE]
        if preview.outcome == "repair_items":
            attributes = list(REPAIR_HASH_ATTRIBUTES)
        elif preview.outcome == "starting_inventory":
            attributes = ["in_stock", "allocated"]
        if row.source_item_hash != item_value_hash(item, attributes):
            stale.append(row.row_number)
    return stale


def audit_metadata_item(item: InventoryItem, job: ImportJob, preview: ImportPreview, row: ImportPreviewRow, db: Session, *, actor: str, before_quantities: tuple[Decimal, Decimal, Decimal]) -> None:
    for attribute, change in row.proposed_changes.items():
        if attribute not in SPEC_BY_ATTRIBUTE:
            continue
        db.add(
            ItemImportChange(
                import_job_id=job.id,
                preview_id=preview.id,
                item_id=item.id,
                sku=item.sku,
                field_name=attribute,
                previous_value=change.get("before"),
                new_value=change.get("after"),
                source_filename=preview.file_name,
                outcome=preview.outcome,
                mapping_profile_id=(preview.options_json or {}).get("mapping_profile_id"),
                created_by=actor,
            )
        )
    old_stock, old_allocated, old_available = before_quantities
    db.add(
        InventoryAuditEvent(
            item_id=item.id,
            sku=item.sku,
            barcode=item.barcode,
            event_type="item_metadata_import",
            quantity_delta=Decimal("0"),
            previous_in_stock=old_stock,
            new_in_stock=Decimal(item.in_stock or 0),
            previous_allocated=old_allocated,
            new_allocated=Decimal(item.allocated or 0),
            previous_sellable=old_available,
            new_sellable=Decimal(item.sellable or 0),
            warehouse=item.warehouse,
            inventory_location=item.inventory_location,
            reference_type="import_job",
            reference_id=job.id,
            reference_number=str(job.id),
            notes=f"Metadata imported from {preview.file_name}: {', '.join(sorted(row.proposed_changes))}",
            created_by=actor,
        )
    )


def apply_metadata_row(preview: ImportPreview, row: ImportPreviewRow, job: ImportJob, db: Session, *, actor: str) -> InventoryItem:
    item = db.get(InventoryItem, row.existing_item_id) if row.existing_item_id else InventoryItem()
    if item is None:
        raise ValueError("The matched item no longer exists.")
    before_quantities = (Decimal(item.in_stock or 0), Decimal(item.allocated or 0), Decimal(item.sellable or 0))
    for attribute, change in row.proposed_changes.items():
        if attribute in SPEC_BY_ATTRIBUTE:
            setattr(item, attribute, coerce_attribute(attribute, change.get("after")))
    item.source = item.source or "csv_import"
    db.add(item)
    db.flush()
    apply_calculated_fields(item)
    location_name = item.inventory_location or item.default_location
    location = resolve_location(db, item.warehouse, location_name)
    if location is not None:
        get_or_create_item_location(
            db,
            item,
            location.warehouse,
            location.location_code or location.location_name,
            location_id=location.id,
            is_default_location=True,
            create_physical_location=False,
        )
    audit_metadata_item(item, job, preview, row, db, actor=actor, before_quantities=before_quantities)
    return item


def apply_repair_row(
    preview: ImportPreview,
    row: ImportPreviewRow,
    job: ImportJob,
    db: Session,
    *,
    actor: str,
    repair_context: dict[str, dict[int, Any]] | None = None,
) -> dict[str, Any]:
    item = repair_context["items"].get(row.existing_item_id) if repair_context is not None else db.get(InventoryItem, row.existing_item_id)
    if item is None:
        raise ValueError("The matched item no longer exists.")
    plan = (row.normalized_data or {}).get("_repair_plan") or {}
    target_location_id = plan.get("target_location_id")
    target_physical = repair_context["physical_locations"].get(target_location_id) if repair_context is not None else None
    target_physical = target_physical or db.get(InventoryLocation, target_location_id)
    if target_physical is None or not target_physical.active:
        raise ValueError("The repair target physical location is missing or inactive.")

    before_totals = (
        Decimal(item.in_stock or 0),
        Decimal(item.allocated or 0),
        Decimal(item.sellable or 0),
        Decimal(item.on_order or 0),
    )
    before_quantities = before_totals[:3]
    assignments = (
        list(repair_context["assignments"].get(item.id, []))
        if repair_context is not None
        else list(db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item.id).order_by(InventoryItemLocation.id)).all())
    )
    had_active_assignment = any(candidate.active for candidate in assignments)

    for attribute in ("brand", "unit_cost"):
        change = (row.proposed_changes or {}).get(attribute)
        if change is not None:
            setattr(item, attribute, coerce_attribute(attribute, change.get("after")))

    target = next((candidate for candidate in assignments if candidate.location_id == target_physical.id and candidate.active), None)
    if target is None:
        target = get_or_create_item_location(
            db,
            item,
            target_physical.warehouse,
            target_physical.location_code or target_physical.location_name,
            location_id=target_physical.id,
            is_default_location=True,
            create_physical_location=False,
        )
        if target not in assignments:
            assignments.append(target)
        if not had_active_assignment:
            target.in_stock, target.allocated, target.sellable, target.on_order = before_totals
            recalculate_item_location(target, item)
            recalculate_item_totals(db, item.id)
    target.client = item.client
    target.warehouse = target_physical.warehouse
    target.inventory_location = target_physical.location_code or target_physical.location_name
    target.location_code = target_physical.location_code
    target.location_name = target_physical.location_name
    target.active = True

    assignment_ids = {int(value) for value in plan.get("source_assignment_ids") or []}
    sources = [candidate for candidate in assignments if candidate.id in assignment_ids]
    if {candidate.id for candidate in sources} != assignment_ids:
        raise ValueError("A planned source assignment no longer exists.")

    units_relocated = Decimal("0")
    on_order_units_relocated = Decimal("0")
    for source in sources:
        if not source.active:
            raise ValueError("A planned source assignment is no longer active.")
        movable = Decimal(source.in_stock or 0) - Decimal(source.allocated or 0)
        if movable < 0:
            raise ValueError("A source location has more allocated units than stock.")
        if movable:
            transfer_between_locations(
                db,
                item,
                source,
                target_physical.warehouse or "",
                target_physical.location_code or target_physical.location_name or "",
                movable,
                reference_number=str(job.id),
                reference_id=job.id,
                notes=f"Location repair imported from {preview.file_name}",
                created_by=actor,
                destination_row=target,
                locations_already_validated=True,
                recalculate_totals=False,
            )
            units_relocated += movable
        source_on_order = Decimal(source.on_order or 0)
        if source_on_order:
            source.on_order = Decimal("0")
            target.on_order = Decimal(target.on_order or 0) + source_on_order
            on_order_units_relocated += source_on_order
        recalculate_item_location(source, item)
        recalculate_item_location(target, item)
        assert_location_invariants(source)
        assert_location_invariants(target)
        if Decimal(source.in_stock or 0) == 0 and Decimal(source.allocated or 0) == 0 and Decimal(source.on_order or 0) == 0:
            source.active = False
            source.is_default_location = False

    for assignment in assignments:
        assignment.is_default_location = assignment.id == target.id
    active_assignments = [assignment for assignment in assignments if assignment.active]
    for assignment in active_assignments:
        recalculate_item_location(assignment, item)
        assert_location_invariants(assignment)
    item.in_stock = sum((Decimal(assignment.in_stock or 0) for assignment in active_assignments), Decimal("0"))
    item.allocated = sum((Decimal(assignment.allocated or 0) for assignment in active_assignments), Decimal("0"))
    item.sellable = sum((Decimal(assignment.sellable or 0) for assignment in active_assignments), Decimal("0"))
    item.on_order = sum((Decimal(assignment.on_order or 0) for assignment in active_assignments), Decimal("0"))
    item.under_par = bool(item.par_level is not None and item.in_stock <= item.par_level)
    item.warehouse = target_physical.warehouse
    item.inventory_location = target_physical.location_code or target_physical.location_name
    item.default_location = item.inventory_location
    assert_location_invariants(target)
    assert_item_invariants(item)
    after_totals = (
        Decimal(item.in_stock or 0),
        Decimal(item.allocated or 0),
        Decimal(item.sellable or 0),
        Decimal(item.on_order or 0),
    )
    if after_totals != before_totals:
        raise ValueError("Location repair was stopped because item inventory totals would change.")

    audit_metadata_item(item, job, preview, row, db, actor=actor, before_quantities=before_quantities)
    deferred_sources = [candidate for candidate in sources if candidate.active and Decimal(candidate.allocated or 0) > 0]
    deferred_units = sum((Decimal(candidate.allocated or 0) for candidate in deferred_sources), Decimal("0"))
    db.add(
        InventoryAuditEvent(
            item_id=item.id,
            sku=item.sku,
            barcode=item.barcode,
            event_type="item_location_repair",
            quantity_delta=Decimal("0"),
            previous_in_stock=before_totals[0],
            new_in_stock=after_totals[0],
            previous_allocated=before_totals[1],
            new_allocated=after_totals[1],
            previous_sellable=before_totals[2],
            new_sellable=after_totals[2],
            warehouse=item.warehouse,
            inventory_location=item.inventory_location,
            reference_type="import_job",
            reference_id=job.id,
            reference_number=str(job.id),
            notes=(
                f"Consolidated {serializable(units_relocated)} unallocated and "
                f"{serializable(on_order_units_relocated)} on-order unit(s) from {preview.file_name}; "
                f"{serializable(deferred_units)} allocated unit(s) deferred."
            ),
            created_by=actor,
        )
    )
    return {
        "consolidated": bool(plan.get("needs_consolidation")),
        "units_relocated": units_relocated,
        "on_order_units_relocated": on_order_units_relocated,
        "deferred_location_count": len(deferred_sources),
        "deferred_units": deferred_units,
    }


def finalize_job(job: ImportJob, preview: ImportPreview, *, created: int, updated: int, unchanged: int, excluded: int, failed: int, starting_units: Decimal, started: float, extra_result: dict[str, Any] | None = None) -> dict[str, Any]:
    successful = created + updated + unchanged
    status = "failed" if successful == 0 and failed else ("completed_with_errors" if failed else "completed")
    job.status = status
    job.successful_rows = successful
    job.failed_rows = failed
    job.created_rows = created
    job.updated_rows = updated
    job.unchanged_rows = unchanged
    job.excluded_rows = excluded
    job.starting_units = starting_units
    job.duration_ms = round((perf_counter() - started) * 1000)
    job.completed_at = utcnow()
    result = {
        "import_job_id": job.id,
        "preview_id": preview.id,
        "outcome": preview.outcome,
        "status": status,
        "total_rows": job.total_rows,
        "successful_count": successful,
        "created_count": created,
        "updated_count": updated,
        "unchanged_count": unchanged,
        "excluded_count": excluded,
        "failed_count": failed,
        "starting_units": serializable(starting_units),
        "estimated_valuation": (preview.summary_json or {}).get("estimated_valuation", 0),
        "duration_ms": job.duration_ms,
        **(extra_result or {}),
    }
    job.result_json = result
    preview.status = "committed"
    preview.committed_at = utcnow()
    preview.import_job_id = job.id
    preview.result_json = result
    return result


def commit_preview(
    preview: ImportPreview,
    db: Session,
    *,
    actor: str,
    idempotency_key: str,
    commit_transaction: bool = True,
) -> dict[str, Any]:
    if not idempotency_key or len(idempotency_key) > 120:
        raise HTTPException(status_code=422, detail={"code": "idempotency_key_required", "message": "A valid commit idempotency key is required."})
    if preview.status == "committed":
        return preview.result_json or job_result(db.get(ImportJob, preview.import_job_id))
    if preview.status in {"cancelled", "expired"}:
        raise HTTPException(status_code=409, detail={"code": f"preview_{preview.status}", "message": f"This import preview is {preview.status}. Create a new preview before importing."})
    if preview.status not in {"ready", "running"}:
        raise HTTPException(status_code=409, detail={"code": "preview_not_ready", "message": "Finish matching the required columns before importing."})

    rows = list(db.scalars(select(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id).order_by(ImportPreviewRow.row_number)).all())
    if preview.outcome in {"update_stock", "repair_items"}:
        allowed_states = {"will_update", "no_changes", "skipped"} if preview.outcome == "update_stock" else {"will_update", "no_changes"}
        blockers = [row for row in rows if row.state not in allowed_states]
        if blockers:
            is_repair = preview.outcome == "repair_items"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "repair_import_not_ready" if is_repair else "stock_import_not_ready",
                    "message": (
                        "No item was changed. Fix or remove every blocked repair row, then preview the whole file again."
                        if is_repair
                        else "No stock was changed. Fix the blocking SKU issues before all matched stock totals can be applied together."
                    ),
                    "blocking_count": len(blockers),
                    "row_numbers": [row.row_number for row in blockers[:100]],
                },
            )
        lock_inventory_stock(db, {row.existing_item_id for row in rows if row.existing_item_id})
        if preview.outcome == "repair_items":
            physical_location_ids: set[int] = set()
            for row in rows:
                plan = (row.normalized_data or {}).get("_repair_plan") or {}
                if plan.get("target_location_id"):
                    physical_location_ids.add(int(plan["target_location_id"]))
                for snapshot_row in (plan.get("location_snapshot") or {}).get("locations", []):
                    if snapshot_row.get("location_id"):
                        physical_location_ids.add(int(snapshot_row["location_id"]))
            if physical_location_ids:
                db.scalars(
                    select(InventoryLocation)
                    .where(InventoryLocation.id.in_(physical_location_ids))
                    .order_by(InventoryLocation.id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                ).all()
    stale = stale_rows(preview, rows, db)
    if stale:
        logger.info(json.dumps({"event": "item_import_stale_preview", "preview_id": preview.id, "rows": stale[:20]}))
        raise HTTPException(status_code=409, detail={"code": "stale_preview", "message": "Some items changed after this preview was created. Review a refreshed preview before importing.", "row_numbers": stale[:100]})

    started = perf_counter()
    existing_job = db.get(ImportJob, preview.import_job_id) if preview.import_job_id else None
    if existing_job is not None and existing_job.status in {"completed", "completed_with_errors", "failed"}:
        return job_result(existing_job)
    job = existing_job or ImportJob(
        file_name=preview.file_name,
        import_type=f"items_{preview.outcome}",
        file_sha256=preview.file_sha256,
        preview_id=preview.id,
        outcome=preview.outcome,
        idempotency_key=idempotency_key,
        options_json=preview.options_json,
        total_rows=len(rows),
        successful_rows=0,
        failed_rows=0,
        status="running",
        created_by=actor,
    )
    if existing_job is None:
        db.add(job)
        db.flush()
        preview.import_job_id = job.id
    elif job.idempotency_key and job.idempotency_key != idempotency_key:
        return job_result(job)
    preview.commit_idempotency_key = preview.commit_idempotency_key or idempotency_key
    preview.status = "running"
    db.execute(delete(ImportError).where(ImportError.import_job_id == job.id))
    db.flush()
    logger.info(json.dumps({"event": "item_import_commit_started", "preview_id": preview.id, "import_job_id": job.id, "outcome": preview.outcome, "rows": len(rows)}))

    created = updated = unchanged = failed = 0
    excluded = sum(1 for row in rows if row.state == "excluded")
    starting_units = Decimal("0")
    unresolved = [row for row in rows if row.state in ISSUE_STATES]
    for row in unresolved:
        for issue_data in row.issues_json or [issue("row_not_ready", None, f"Row {row.row_number} still needs attention.")]:
            record_job_error(job, row, db, issue_data)
        failed += 1
    skipped_rows = [row for row in rows if row.state == "skipped"]
    for row in skipped_rows:
        for issue_data in row.issues_json or [issue("sku_not_found", "sku", f"SKU {row.sku!r} was not found in Pongo OS.", row.sku, "Add it to Items first if Pongo should manage it.", blocking=False)]:
            record_job_error(job, row, db, issue_data)

    if preview.outcome == "repair_items":
        try:
            unchanged = sum(1 for row in rows if row.state == "no_changes")
            repair_item_ids = {row.existing_item_id for row in rows if row.existing_item_id}
            repair_items = {item.id: item for item in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(repair_item_ids))).all()}
            repair_assignments: dict[int, list[InventoryItemLocation]] = defaultdict(list)
            all_repair_assignments = list(db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id.in_(repair_item_ids)).order_by(InventoryItemLocation.inventory_item_id, InventoryItemLocation.id)).all())
            for assignment in all_repair_assignments:
                repair_assignments[assignment.inventory_item_id].append(assignment)
            repair_physical_ids = {assignment.location_id for assignment in all_repair_assignments if assignment.location_id}
            repair_physical_locations = {location.id: location for location in db.scalars(select(InventoryLocation).where(InventoryLocation.id.in_(repair_physical_ids))).all()}
            repair_context = {"items": repair_items, "assignments": repair_assignments, "physical_locations": repair_physical_locations}
            metrics = {
                "consolidate_count": 0,
                "deferred_location_count": 0,
                "deferred_units": Decimal("0"),
                "units_relocated": Decimal("0"),
                "on_order_units_relocated": Decimal("0"),
            }
            for row in rows:
                if row.state != "will_update":
                    continue
                row_metrics = apply_repair_row(preview, row, job, db, actor=actor, repair_context=repair_context)
                updated += 1
                metrics["consolidate_count"] += int(row_metrics["consolidated"])
                metrics["deferred_location_count"] += int(row_metrics["deferred_location_count"])
                for key in ("deferred_units", "units_relocated", "on_order_units_relocated"):
                    metrics[key] += Decimal(row_metrics[key] or 0)
            result = finalize_job(
                job,
                preview,
                created=0,
                updated=updated,
                unchanged=unchanged,
                excluded=0,
                failed=0,
                starting_units=starting_units,
                started=started,
                extra_result={key: serializable(value) for key, value in metrics.items()},
            )
            if commit_transaction:
                db.commit()
            else:
                db.flush()
        except Exception as exc:
            if commit_transaction:
                db.rollback()
            logger.exception(json.dumps({"event": "item_import_commit_failed", "preview_id": preview.id, "outcome": preview.outcome}))
            raise HTTPException(status_code=500, detail={"code": "import_transaction_failed", "message": "The repair could not be completed. No item or location changes were saved."}) from exc
    elif preview.outcome in METADATA_OUTCOMES:
        try:
            for row in rows:
                if row.state == "no_changes":
                    unchanged += 1
                elif row.state in READY_STATES:
                    apply_metadata_row(preview, row, job, db, actor=actor)
                    if row.state == "will_create":
                        created += 1
                    else:
                        updated += 1
            result = finalize_job(job, preview, created=created, updated=updated, unchanged=unchanged, excluded=excluded, failed=failed, starting_units=starting_units, started=started)
            db.commit()
        except Exception as exc:
            db.rollback()
            failed_job = ImportJob(file_name=preview.file_name, import_type=f"items_{preview.outcome}", file_sha256=preview.file_sha256, preview_id=preview.id, outcome=preview.outcome, idempotency_key=idempotency_key, total_rows=len(rows), successful_rows=0, failed_rows=len(rows) - excluded, status="failed", created_by=actor, completed_at=utcnow(), duration_ms=round((perf_counter() - started) * 1000), result_json={"status": "failed", "message": "The import transaction was rolled back safely."})
            db.add(failed_job)
            db.commit()
            logger.exception(json.dumps({"event": "item_import_commit_failed", "preview_id": preview.id, "outcome": preview.outcome}))
            raise HTTPException(status_code=500, detail={"code": "import_transaction_failed", "message": "The import could not be completed. No item metadata changes were saved.", "import_job_id": failed_job.id}) from exc
    elif preview.outcome == "update_stock":
        try:
            unchanged = sum(1 for row in rows if row.state == "no_changes")
            skipped = len(skipped_rows)
            stock_rows = [row for row in rows if row.state == "will_update"]
            lines = []
            for row in stock_rows:
                for target in stock_targets(row):
                    if Decimal(str(target["new_quantity"])) == Decimal(str(target["expected_quantity"])):
                        continue
                    lines.append({"item_id": row.existing_item_id, **target, "notes": row.normalized_data.get("note") or None})
            adjustment = None
            if lines:
                adjustment = create_committed_adjustment_batch(
                    db,
                    lines,
                    adjustment_type="correction",
                    reason=f"CSV stock override from {preview.file_name}",
                    notes=f"Item import job #{job.id}",
                    created_by=actor,
                    idempotency_key=f"item-import:{preview.id}:{idempotency_key}",
                )
                if not getattr(adjustment, "_idempotent_replay", False):
                    auto_allocate_processing_orders_fifo(db, source=f"item-import:{job.id}")
            updated = len(stock_rows)
            result = finalize_job(
                job,
                preview,
                created=0,
                updated=updated,
                unchanged=unchanged,
                excluded=excluded,
                failed=failed,
                starting_units=starting_units,
                started=started,
                extra_result={
                    "stock_adjustment_id": adjustment.id if adjustment else None,
                    "stock_units_delta": (preview.summary_json or {}).get("stock_units_delta", 0),
                    "skipped_count": skipped,
                    "source_row_count": (preview.summary_json or {}).get("source_row_count", len(rows)),
                    "sku_count": (preview.summary_json or {}).get("sku_count", len(rows)),
                },
            )
            item_ids = {row.existing_item_id for row in stock_rows if row.existing_item_id}
            db.commit()
        except StaleStockQuantityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail={"code": "stale_preview", "message": str(exc) + " Review a refreshed preview before importing."}) from exc
        except Exception as exc:
            db.rollback()
            failed_job = ImportJob(file_name=preview.file_name, import_type=f"items_{preview.outcome}", file_sha256=preview.file_sha256, preview_id=preview.id, outcome=preview.outcome, idempotency_key=idempotency_key, total_rows=len(rows), successful_rows=0, failed_rows=len(rows) - excluded, status="failed", created_by=actor, completed_at=utcnow(), duration_ms=round((perf_counter() - started) * 1000), result_json={"status": "failed", "message": "The stock import transaction was rolled back safely."})
            db.add(failed_job)
            db.commit()
            logger.exception(json.dumps({"event": "item_import_commit_failed", "preview_id": preview.id, "outcome": preview.outcome}))
            raise HTTPException(status_code=500, detail={"code": "import_transaction_failed", "message": "The stock import could not be completed. No stock changes were saved.", "import_job_id": failed_job.id}) from exc

        try:
            settings = effective_woocommerce_settings(db, get_settings())
            if item_ids and stock_writeback_enabled(settings):
                sync_job = create_stock_sync_job(db, WooStockSyncRequest(idempotency_key=f"item-import:{preview.id}", requested_by=actor))
                result = {**result, "woo_stock_sync_job_id": sync_job.id}
                job = db.get(ImportJob, result["import_job_id"])
                preview = db.get(ImportPreview, result["preview_id"])
                job.result_json = result
                preview.result_json = result
                db.commit()
        except Exception:
            db.rollback()
            logger.exception(json.dumps({"event": "item_import_stock_writeback_queue_failed", "preview_id": preview.id, "item_count": len(item_ids)}))
    else:
        db.commit()
        for row in rows:
            if row.state != "will_update":
                continue
            try:
                quantity = Decimal(str(row.normalized_data.get("starting_quantity") or 0))
                set_opening_balance(
                    db,
                    row.existing_item_id,
                    in_stock=quantity,
                    allocated=Decimal("0"),
                    warehouse=str(row.normalized_data.get("starting_warehouse") or ""),
                    inventory_location=str(row.normalized_data.get("starting_location") or ""),
                    idempotency_key=f"item-import:{preview.id}:{row.row_number}",
                    created_by=actor,
                    reference_type="import_job",
                    reference_id=job.id,
                    reason=f"Starting inventory imported from {preview.file_name}",
                )
                updated += 1
                starting_units += quantity
            except Exception as exc:
                db.rollback()
                runtime_issue = issue("starting_inventory_failed", "starting_quantity", f"Row {row.row_number}: {exc}", row.normalized_data.get("starting_quantity"), "Review current stock history and try this row again.")
                record_job_error(job, row, db, runtime_issue)
                db.commit()
                failed += 1
        job = db.get(ImportJob, job.id)
        preview = db.get(ImportPreview, preview.id)
        result = finalize_job(job, preview, created=0, updated=updated, unchanged=0, excluded=excluded, failed=failed, starting_units=starting_units, started=started)
        db.commit()

    logger.info(json.dumps({"event": "item_import_commit_completed", "preview_id": preview.id, "import_job_id": result["import_job_id"], "status": result["status"], "duration_ms": result["duration_ms"], "created": result["created_count"], "updated": result["updated_count"], "failed": result["failed_count"]}))
    return result


def rollback_metadata_import(job: ImportJob, db: Session, *, actor: str) -> dict[str, Any]:
    result = dict(job.result_json or {})
    if (result.get("rollback") or {}).get("status") == "completed":
        return result["rollback"]
    if job.outcome != "update_items" or job.status not in {"completed", "completed_with_errors"}:
        raise HTTPException(status_code=409, detail={"code": "rollback_not_available", "message": "Safe rollback is available only for completed item-detail updates. Added items and inventory movements are not deleted."})
    changes = list(db.scalars(select(ItemImportChange).where(ItemImportChange.import_job_id == job.id).order_by(ItemImportChange.id.desc())).all())
    if not changes:
        raise HTTPException(status_code=409, detail={"code": "rollback_not_available", "message": "This import has no reversible metadata changes."})
    item_ids = {change.item_id for change in changes}
    items = {item.id: item for item in db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids))).all()}
    stale = []
    for change in changes:
        item = items.get(change.item_id)
        if item is None or not values_equal(getattr(item, change.field_name, None), change.new_value):
            stale.append({"item_id": change.item_id, "sku": change.sku, "field": change.field_name})
    if stale:
        raise HTTPException(status_code=409, detail={"code": "rollback_stale", "message": "Some imported fields changed after this import. Nothing was rolled back.", "conflicts": stale[:100]})

    quantities = {item.id: (Decimal(item.in_stock or 0), Decimal(item.allocated or 0), Decimal(item.sellable or 0)) for item in items.values()}
    fields_by_item: dict[int, list[str]] = defaultdict(list)
    for change in changes:
        item = items[change.item_id]
        setattr(item, change.field_name, coerce_attribute(change.field_name, change.previous_value))
        fields_by_item[item.id].append(change.field_name)
    for item in items.values():
        apply_calculated_fields(item)
        old_stock, old_allocated, old_sellable = quantities[item.id]
        if (Decimal(item.in_stock or 0), Decimal(item.allocated or 0), Decimal(item.sellable or 0)) != quantities[item.id]:
            db.rollback()
            raise HTTPException(status_code=500, detail={"code": "rollback_inventory_guard", "message": "Rollback was stopped because an inventory quantity would have changed."})
        db.add(
            InventoryAuditEvent(
                item_id=item.id,
                sku=item.sku,
                barcode=item.barcode,
                event_type="item_metadata_import_rollback",
                quantity_delta=Decimal("0"),
                previous_in_stock=old_stock,
                new_in_stock=old_stock,
                previous_allocated=old_allocated,
                new_allocated=old_allocated,
                previous_sellable=old_sellable,
                new_sellable=old_sellable,
                warehouse=item.warehouse,
                inventory_location=item.inventory_location,
                reference_type="import_job",
                reference_id=job.id,
                reference_number=str(job.id),
                notes=f"Rolled back imported item details: {', '.join(sorted(fields_by_item[item.id]))}",
                created_by=actor,
            )
        )
    rollback = {"status": "completed", "import_job_id": job.id, "items_restored": len(items), "fields_restored": len(changes), "completed_at": utcnow().isoformat(), "completed_by": actor}
    job.result_json = {**result, "rollback": rollback}
    db.commit()
    logger.info(json.dumps({"event": "item_import_rollback_completed", **rollback}))
    return rollback
