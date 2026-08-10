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
from app.models.imports import ImportError, ImportJob, ImportMappingProfile, ImportPreview, ImportPreviewRow, ItemImportChange
from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation, InventoryLocation, StockMovement
from app.schemas.woocommerce import WooStockSyncRequest
from app.services.items import apply_calculated_fields
from app.services.location_inventory import StaleStockQuantityError, create_committed_adjustment_batch, get_or_create_item_location, set_opening_balance
from app.services.order_workflow import auto_allocate_processing_orders_fifo
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_stock_sync_jobs import create_stock_sync_job
from app.services.woocommerce_writeback import stock_writeback_enabled


logger = logging.getLogger("pongo.item_import")
SCHEMA_VERSION = "2026-08-10.1"
OUTCOMES = {"add_items", "update_items", "starting_inventory", "update_stock"}
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
    field("warehouse", "Warehouse", "warehouse", "text", [*METADATA_OUTCOMES, "update_stock"], aliases=["Warehouse name"], required_for=["update_stock"], example="Main Warehouse", max_length=120),
    field("inventory_location", "Inventory location", "inventory_location", "text", [*METADATA_OUTCOMES, "update_stock"], aliases=["Location", "Bin", "Location code"], required_for=["update_stock"], example="A-01", max_length=200),
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
    field("stock_quantity", "In stock", None, "decimal", ["update_stock"], aliases=["On hand", "Stock", "Quantity", "Current stock"], required_for=["update_stock"], example="24", description="The exact physical quantity at this warehouse location after the import.", nullable=False, quantity_related=True),
    field("starting_quantity", "Starting quantity", None, "decimal", ["starting_inventory"], aliases=["Starting inventory", "Initial quantity", "Opening quantity", "Quantity"], required_for=["starting_inventory"], example="24", description="The physical quantity present at the beginning of onboarding.", nullable=False, quantity_related=True),
    field("starting_warehouse", "Warehouse", None, "text", ["starting_inventory"], aliases=["Warehouse name"], required_for=["starting_inventory"], example="Main Warehouse", nullable=False, max_length=120),
    field("starting_location", "Inventory location", None, "text", ["starting_inventory"], aliases=["Location", "Bin", "Location code"], required_for=["starting_inventory"], example="A-01", nullable=False, max_length=200),
    field("note", "Reference note", None, "text", ["starting_inventory", "update_stock"], aliases=["Reference", "Notes", "Reason"], example="Physical count", max_length=500),
]

FIELD_BY_KEY = {spec["key"]: spec for spec in FIELD_SPECS}
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
    "starting_inventory": {
        "label": "Set starting inventory",
        "description": "Record the physical quantity present at the beginning of onboarding.",
        "changes": "Creates audited starting-inventory movements at an eligible location.",
        "does_not_change": "Existing operational inventory is never overwritten.",
    },
    "update_stock": {
        "label": "Override stock levels",
        "description": "Set exact physical stock by SKU and inventory location.",
        "changes": "Creates one audited stock adjustment for the included quantity changes.",
        "does_not_change": "Allocated and sellable quantities remain system-managed; item details are not edited.",
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
    return [{key: value for key, value in spec.items() if key != "attribute"} for spec in FIELD_SPECS if outcome in spec["outcomes"]]


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
                "required_fields": [spec["key"] for spec in FIELD_SPECS if outcome in spec["required_for"]],
            }
            for outcome in ["add_items", "update_items", "update_stock", "starting_inventory"]
        ],
    }


def field_specs_for(outcome: str) -> list[dict[str, Any]]:
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
    elif include_existing and outcome == "update_stock":
        item_locations = db.scalars(select(InventoryItemLocation).join(InventoryItem).where(InventoryItemLocation.active.is_(True)).options(selectinload(InventoryItemLocation.inventory_item)).order_by(InventoryItem.sku.asc().nullslast(), InventoryItemLocation.warehouse, InventoryItemLocation.inventory_location, InventoryItemLocation.id)).all()
        for row in item_locations:
            values = {"sku": row.inventory_item.sku, "warehouse": row.warehouse, "inventory_location": row.inventory_location, "stock_quantity": row.in_stock, "note": ""}
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
    mapping: dict[str, str | None] = {}
    suggestions: list[dict[str, Any]] = []
    used: set[str] = set()
    for header in headers:
        matches = list(dict.fromkeys(aliases.get(normalize_header(header), [])))
        destination = matches[0] if len(matches) == 1 and matches[0] not in used else None
        if destination:
            used.add(destination)
        mapping[header] = destination
        suggestions.append({"source": header, "destination": destination, "confidence": "exact" if destination and normalize_header(header) in {normalize_header(destination), normalize_header(FIELD_BY_KEY[destination]["label"])} else ("alias" if destination else "unmatched"), "ambiguous_matches": matches if len(matches) > 1 else []})
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


async def create_preview(file: UploadFile, outcome: str, db: Session, *, actor: str) -> ImportPreview:
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail={"code": "invalid_outcome", "message": "Choose Add new items, Update item details, Override stock levels, or Set starting inventory."})
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
    mapping, suggestions = suggest_mapping(headers, outcome)
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
        options_json={"allow_blank_clears": False, "file_size": len(content), "encoding": encoding, "delimiter": delimiter, "mapping_profile_id": None},
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
    if preview.status not in {"committed", "cancelled", "expired"} and aware(preview.expires_at) <= utcnow():
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
        (
            normalize_identifier(values.get("sku")),
            normalize_identifier(values.get("warehouse")),
            normalize_identifier(values.get("inventory_location")),
        )
        for values in mapped_rows.values()
        if normalize_identifier(values.get("sku")) and normalize_identifier(values.get("warehouse")) and normalize_identifier(values.get("inventory_location"))
    )
    barcode_counts = Counter(normalize_identifier(values.get("barcode")) for values in mapped_rows.values() if normalize_identifier(values.get("barcode")))

    sku_keys = {normalize_identifier(values.get("sku")) for values in mapped_rows.values() if normalize_identifier(values.get("sku"))}
    barcode_keys = {normalize_identifier(values.get("barcode")) for values in mapped_rows.values() if normalize_identifier(values.get("barcode"))}
    item_matchers = []
    if sku_keys:
        item_matchers.append(func.lower(func.trim(InventoryItem.sku)).in_(sku_keys))
    if barcode_keys:
        item_matchers.append(func.lower(func.trim(InventoryItem.barcode)).in_(barcode_keys))
    items = list(db.scalars(select(InventoryItem).where(or_(*item_matchers))).all()) if item_matchers else []
    items_by_id = {item.id: item for item in items}
    by_sku: dict[str, list[InventoryItem]] = defaultdict(list)
    by_barcode: dict[str, list[InventoryItem]] = defaultdict(list)
    for item in items:
        if item.sku:
            by_sku[normalize_identifier(item.sku)].append(item)
        if item.barcode:
            by_barcode[normalize_identifier(item.barcode)].append(item)
    item_locations: dict[tuple[int, str, str], dict[int, InventoryItemLocation]] = defaultdict(dict)
    if outcome == "update_stock" and items:
        for item_location in db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id.in_([item.id for item in items]), InventoryItemLocation.active.is_(True))).all():
            for location_name in {item_location.inventory_location, item_location.location_code, item_location.location_name}:
                if location_name:
                    item_locations[(item_location.inventory_item_id, normalize_identifier(item_location.warehouse), normalize_identifier(location_name))][item_location.id] = item_location
    movement_item_ids = set(db.scalars(select(StockMovement.inventory_item_id).where(StockMovement.inventory_item_id.in_([item.id for item in items])).distinct()).all()) if outcome == "starting_inventory" and items else set()
    locations = active_location_map(db)
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
        if outcome == "update_stock" and all(stock_scope) and stock_scope_counts[stock_scope] > 1:
            row_issues.append(issue("duplicate_stock_location_in_file", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} and this inventory location appear more than once in this file.", parsed.get("sku"), "Keep one stock value for each SKU and inventory location."))
        elif outcome != "update_stock" and sku_key and sku_counts[sku_key] > 1:
            row_issues.append(issue("duplicate_sku_in_file", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} appears more than once in this file.", parsed.get("sku"), "Keep one row for this SKU or give each item a unique SKU."))
        if barcode_key and barcode_counts[barcode_key] > 1:
            row_issues.append(issue("duplicate_barcode_in_file", "barcode", f"Row {row.row_number}: Barcode {parsed.get('barcode')!r} appears more than once in this file.", parsed.get("barcode"), "Correct or remove the duplicate barcode."))

        matches = by_sku.get(sku_key, []) if sku_key else []
        item = matches[0] if len(matches) == 1 else None
        if len(matches) > 1:
            row_issues.append(issue("ambiguous_sku", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} matches multiple existing items.", parsed.get("sku"), "Resolve the duplicate SKU in Items before importing."))
        if outcome == "add_items" and item is not None:
            row_issues.append(issue("sku_already_exists", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} already exists in Pongo OS.", parsed.get("sku"), "Exclude this row or use Update item details."))
        if outcome in {"update_items", "starting_inventory", "update_stock"} and sku_key and not matches:
            row_issues.append(issue("sku_not_found", "sku", f"Row {row.row_number}: SKU {parsed.get('sku')!r} was not found in Pongo OS.", parsed.get("sku"), "Correct the SKU or exclude this row."))

        if barcode_key:
            barcode_matches = by_barcode.get(barcode_key, [])
            if any(candidate.id != getattr(item, "id", None) for candidate in barcode_matches):
                row_issues.append(issue("barcode_already_exists", "barcode", f"Row {row.row_number}: Barcode {parsed.get('barcode')!r} belongs to another item.", parsed.get("barcode"), "Enter a unique barcode or leave it blank."))

        changes: dict[str, dict[str, Any]] = {}
        relevant_attributes: list[str] = []
        if outcome in METADATA_OUTCOMES:
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
            warehouse = parsed.get("warehouse")
            location_name = parsed.get("inventory_location")
            if quantity is not None and quantity < 0:
                row_issues.append(issue("negative_stock", "stock_quantity", f"Row {row.row_number}: In stock cannot be negative.", quantity, "Enter zero or a positive physical count."))
            if warehouse and location_name and len(locations.get((normalize_identifier(warehouse), normalize_identifier(location_name)), [])) != 1:
                row_issues.append(issue("invalid_location", "inventory_location", f"Row {row.row_number}: {warehouse} / {location_name} does not match one active inventory location.", location_name, "Choose an active warehouse and location from Pongo OS."))
            if item is not None and warehouse and location_name:
                candidates = list(item_locations.get((item.id, normalize_identifier(warehouse), normalize_identifier(location_name)), {}).values())
                if len(candidates) != 1:
                    row_issues.append(issue("item_location_not_found", "inventory_location", f"Row {row.row_number}: SKU {item.sku!r} is not assigned to exactly one active {warehouse} / {location_name} location.", location_name, "Assign the item to this location in Pongo OS, then preview the CSV again."))
                else:
                    item_location = candidates[0]
                    current = Decimal(item_location.in_stock or 0)
                    parsed["_inventory_item_location_id"] = item_location.id
                    parsed["_expected_quantity"] = current
                    if quantity is not None and current != quantity:
                        variance = quantity - current
                        scope_label = f"{warehouse} / {location_name}"
                        changes = {
                            "in_stock": {"field": "stock_quantity", "label": f"In stock · {scope_label}", "before": serializable(current), "after": serializable(quantity)},
                            "variance": {"field": "stock_quantity", "label": f"Variance · {scope_label}", "before": 0, "after": serializable(variance)},
                        }
                    relevant_attributes = ["in_stock", "allocated"]

        if row.excluded:
            state = "excluded"
        elif row_issues:
            codes = {candidate["code"] for candidate in row_issues}
            state = "duplicate" if any("duplicate" in code or "already_exists" in code or "ambiguous" in code for code in codes) else ("unmatched" if "sku_not_found" in codes else ("blocked" if "starting_inventory_ineligible" in codes else "needs_attention"))
        elif outcome == "add_items":
            state = "will_create"
        elif outcome in {"update_items", "update_stock"}:
            state = "will_update" if changes else "no_changes"
        else:
            state = "will_update"

        row.sku = str(parsed.get("sku") or "") or None
        row.barcode = str(parsed.get("barcode") or "") or None
        row.product_name = str(parsed.get("product_name") or (item.description if item is not None else "") or "") or None
        row.normalized_data = {key: serializable(value) for key, value in parsed.items()}
        row.existing_item_id = item.id if item is not None else None
        row.source_item_hash = item_value_hash(item, relevant_attributes) if item is not None else None
        row.proposed_changes = changes
        row.issues_json = row_issues
        row.state = state
        row.match_method = "sku" if item is not None else None

    counts = Counter(row.state for row in rows)
    starting_units = sum((Decimal(str(row.normalized_data.get("starting_quantity") or 0)) for row in rows if row.state == "will_update" and outcome == "starting_inventory"), Decimal("0"))
    valuation = sum((Decimal(str(row.normalized_data.get("starting_quantity") or 0)) * Decimal(str((items_by_id.get(row.existing_item_id).unit_cost if items_by_id.get(row.existing_item_id) else 0) or 0)) for row in rows if row.state == "will_update" and outcome == "starting_inventory"), Decimal("0"))
    stock_units_delta = sum((Decimal(str((row.proposed_changes or {}).get("variance", {}).get("after") or 0)) for row in rows if row.state == "will_update" and outcome == "update_stock"), Decimal("0"))
    preview.summary_json = {
        **(preview.summary_json or {}),
        "total_rows": len(rows),
        "ready_count": counts["will_create"] + counts["will_update"],
        "create_count": counts["will_create"],
        "update_count": counts["will_update"],
        "no_changes_count": counts["no_changes"],
        "needs_attention_count": counts["needs_attention"],
        "duplicate_count": counts["duplicate"],
        "unmatched_count": counts["unmatched"],
        "blocked_count": counts["blocked"],
        "excluded_count": counts["excluded"],
        "missing_required_mappings": missing_mapping,
        "starting_units": serializable(starting_units),
        "estimated_valuation": serializable(valuation),
        "stock_units_delta": serializable(stock_units_delta),
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
        "file": {"name": preview.file_name, "size": (preview.options_json or {}).get("file_size"), "encoding": (preview.options_json or {}).get("encoding"), "delimiter": (preview.options_json or {}).get("delimiter"), "sha256": preview.file_sha256, "row_count": (preview.summary_json or {}).get("total_rows"), "header_count": len(preview.source_headers)},
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
    if preview.status == "committed":
        raise HTTPException(status_code=409, detail={"code": "preview_already_committed", "message": "A completed import cannot be cancelled."})
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
            raw_row=row.source_data,
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


def stale_rows(preview: ImportPreview, rows: list[ImportPreviewRow], db: Session) -> list[int]:
    stale: list[int] = []
    ready_rows = [row for row in rows if row.state in READY_STATES | ({"no_changes"} if preview.outcome != "update_stock" else set())]
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

    for row in ready_rows:
        item = db.get(InventoryItem, row.existing_item_id) if row.existing_item_id else None
        if item is None:
            stale.append(row.row_number)
            continue
        if preview.outcome == "update_stock":
            location_id = (row.normalized_data or {}).get("_inventory_item_location_id")
            item_location = db.get(InventoryItemLocation, location_id) if location_id else None
            expected = Decimal(str((row.normalized_data or {}).get("_expected_quantity") or 0))
            if item_location is None or not item_location.active or item_location.inventory_item_id != item.id or Decimal(item_location.in_stock or 0) != expected:
                stale.append(row.row_number)
            continue
        attributes = [attribute for attribute in row.proposed_changes if attribute in SPEC_BY_ATTRIBUTE]
        if preview.outcome == "starting_inventory":
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


def commit_preview(preview: ImportPreview, db: Session, *, actor: str, idempotency_key: str) -> dict[str, Any]:
    if not idempotency_key or len(idempotency_key) > 120:
        raise HTTPException(status_code=422, detail={"code": "idempotency_key_required", "message": "A valid commit idempotency key is required."})
    if preview.status == "committed":
        return preview.result_json or job_result(db.get(ImportJob, preview.import_job_id))
    if preview.status in {"cancelled", "expired"}:
        raise HTTPException(status_code=409, detail={"code": f"preview_{preview.status}", "message": f"This import preview is {preview.status}. Create a new preview before importing."})
    if preview.status not in {"ready", "running"}:
        raise HTTPException(status_code=409, detail={"code": "preview_not_ready", "message": "Finish matching the required columns before importing."})

    rows = list(db.scalars(select(ImportPreviewRow).where(ImportPreviewRow.preview_id == preview.id).order_by(ImportPreviewRow.row_number)).all())
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

    if preview.outcome in METADATA_OUTCOMES:
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
            stock_rows = [row for row in rows if row.state == "will_update"]
            lines = [
                {
                    "item_id": row.existing_item_id,
                    "inventory_item_location_id": row.normalized_data["_inventory_item_location_id"],
                    "new_quantity": row.normalized_data["stock_quantity"],
                    "expected_quantity": row.normalized_data["_expected_quantity"],
                    "notes": row.normalized_data.get("note") or None,
                }
                for row in stock_rows
            ]
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
                extra_result={"stock_adjustment_id": adjustment.id if adjustment else None, "stock_units_delta": (preview.summary_json or {}).get("stock_units_delta", 0)},
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
