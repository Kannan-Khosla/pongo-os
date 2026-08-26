import csv
from dataclasses import dataclass, field
from decimal import Decimal
from io import StringIO

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem
from app.schemas.imports import ImportPreviewResponse, ImportPreviewRow, ImportRowError
from app.schemas.items import InventoryItemCreate
from app.services.calculations import calculate_sellable, calculate_storage_volume, calculate_under_par
from app.services.items import CANONICAL_ITEM_COLUMNS

NUMERIC_COLUMNS = {
    "In Stock",
    "Allocated",
    "Sellable",
    "On Order",
    "Recommended Retail Price",
    "Sales Price",
    "Unit Cost",
    "Weight",
    "Default Econ Order",
    "Default Lead Time Days",
    "Par Level",
    "Storage Length",
    "Storage Width",
    "Storage Height",
    "Storage Volume",
}

BOOLEAN_COLUMNS = {
    "Under Par",
    "Assembly",
    "Serializable",
    "Track Lot",
    "Perishable",
    "Re-Order",
}

BOOL_TRUE = {"true", "yes", "1", "y"}
BOOL_FALSE = {"false", "no", "0", "n", ""}
HEADER_ALIASES = {
    "Default Lead Time (Days)": "Default Lead Time Days",
    "Product Title": "Description",
}
OPTIONAL_DEFAULT_COLUMNS = {
    "Manufacturer": "",
    "Tags": "",
}


@dataclass
class ParsedImportRow:
    row_number: int
    action: str
    values: dict[str, object]
    existing_item: InventoryItem | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedImport:
    total_rows: int
    valid_rows: list[ParsedImportRow]
    skipped_count: int
    errors: list[ImportRowError]
    warnings: list[str]
    extra_columns: list[str]


async def read_upload_text(file: UploadFile) -> str:
    content = await file.read()
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.") from exc


def parse_items_csv(csv_text: str, db: Session) -> ParsedImport:
    reader = csv_reader(csv_text)
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail="CSV file is empty.") from exc

    header, extra_columns = normalize_header(raw_header)
    missing_columns = [column for column in CANONICAL_ITEM_COLUMNS if column not in header and column not in OPTIONAL_DEFAULT_COLUMNS]
    if missing_columns:
        raise HTTPException(status_code=400, detail={"message": "CSV header is missing required canonical columns.", "missing_columns": missing_columns})

    rows = []
    skipped_count = 0
    errors: list[ImportRowError] = []
    warnings = [f"Extra column ignored: {column}" for column in extra_columns]
    existing_by_sku, existing_by_barcode = load_existing_item_maps(db)
    seen_skus: set[str] = set()
    seen_barcodes: set[str] = set()

    for physical_row_number, raw_values in enumerate(reader, start=2):
        row = {column: "" for column in header}
        for index, column in enumerate(header):
            row[column] = raw_values[index].strip() if index < len(raw_values) else ""
        canonical_row = {column: row.get(column, OPTIONAL_DEFAULT_COLUMNS.get(column, "")) for column in CANONICAL_ITEM_COLUMNS}

        if not any(str(value).strip() for value in canonical_row.values()):
            skipped_count += 1
            continue

        parsed, row_errors, row_warnings = parse_row_values(canonical_row)
        sku = str(parsed.get("SKU") or "").strip()
        barcode = str(parsed.get("Barcode") or "").strip()
        if not sku:
            errors.append(row_error(physical_row_number, sku, barcode, "SKU is required for item import.", canonical_row))
            continue
        if row_errors:
            for message in row_errors:
                errors.append(row_error(physical_row_number, sku, barcode, message, canonical_row))
            continue

        if sku in seen_skus or (barcode and barcode in seen_barcodes):
            errors.append(row_error(physical_row_number, sku, barcode, "SKU or Barcode is repeated in this import file.", canonical_row))
            continue
        seen_skus.add(sku)
        if barcode:
            seen_barcodes.add(barcode)

        sku_matches = existing_by_sku.get(sku, [])
        barcode_matches = existing_by_barcode.get(barcode, []) if barcode else []
        if len(sku_matches) > 1 or len(barcode_matches) > 1:
            errors.append(row_error(physical_row_number, sku, barcode, "SKU or Barcode matches multiple existing items.", canonical_row))
            continue
        sku_match = sku_matches[0] if sku_matches else None
        barcode_match = barcode_matches[0] if barcode_matches else None
        if sku_match is not None and barcode_match is not None and sku_match.id != barcode_match.id:
            errors.append(row_error(physical_row_number, sku, barcode, "SKU and Barcode match different existing items.", canonical_row))
            continue

        existing_item = sku_match or barcode_match
        action = "update" if existing_item else "create"
        rows.append(ParsedImportRow(row_number=physical_row_number, action=action, values=parsed, existing_item=existing_item, warnings=row_warnings))

    return ParsedImport(total_rows=len(rows) + skipped_count + len(errors), valid_rows=rows, skipped_count=skipped_count, errors=errors, warnings=warnings, extra_columns=extra_columns)


def csv_reader(csv_text: str) -> csv.reader:
    try:
        dialect = csv.Sniffer().sniff(csv_text[:4096], delimiters=",\t")
    except csv.Error:
        dialect = csv.excel
    return csv.reader(StringIO(csv_text), dialect)


def normalize_header(raw_header: list[str]) -> tuple[list[str], list[str]]:
    header: list[str] = []
    extra_columns: list[str] = []
    seen: set[str] = set()
    for raw_column in raw_header:
        source_column = raw_column.strip()
        column = HEADER_ALIASES.get(source_column, source_column)
        if column in seen:
            raise HTTPException(status_code=400, detail={"message": "CSV header contains duplicate columns after normalization.", "column": column})
        seen.add(column)
        header.append(column)
        if column not in CANONICAL_ITEM_COLUMNS:
            extra_columns.append(source_column)
    return header, extra_columns


def preview_from_parsed(parsed: ParsedImport) -> ImportPreviewResponse:
    preview_rows = [
        ImportPreviewRow(
            row_number=row.row_number,
            action=row.action,
            sku=str(row.values.get("SKU") or ""),
            barcode=str(row.values.get("Barcode") or ""),
            warnings=row.warnings,
            row=serialize_preview_row(row.values),
        )
        for row in parsed.valid_rows[:20]
    ]
    create_count = sum(1 for row in parsed.valid_rows if row.action == "create")
    update_count = sum(1 for row in parsed.valid_rows if row.action == "update")
    all_warnings = [*parsed.warnings, *[f"Row {row.row_number}: {warning}" for row in parsed.valid_rows for warning in row.warnings]]
    return ImportPreviewResponse(
        total_rows=parsed.total_rows,
        valid_rows=len(parsed.valid_rows),
        invalid_rows=len(parsed.errors),
        create_count=create_count,
        update_count=update_count,
        skipped_count=parsed.skipped_count,
        warnings=all_warnings,
        errors=parsed.errors,
        preview_rows=preview_rows,
    )


def parse_row_values(row: dict[str, str]) -> tuple[dict[str, object], list[str], list[str]]:
    parsed: dict[str, object] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for column in CANONICAL_ITEM_COLUMNS:
        value = row.get(column, "")
        if column in NUMERIC_COLUMNS:
            parsed[column], error = parse_decimal(value)
            if error:
                errors.append(f"{column}: {error}")
        elif column in BOOLEAN_COLUMNS:
            parsed[column], error = parse_bool(value)
            if error:
                errors.append(f"{column}: {error}")
        else:
            parsed[column] = value.strip()

    sellable = calculate_sellable(parsed["In Stock"], parsed["Allocated"])
    under_par = calculate_under_par(parsed["In Stock"], parsed["Par Level"])
    storage_volume = calculate_storage_volume(parsed["Storage Length"], parsed["Storage Width"], parsed["Storage Height"])
    if parsed["Sellable"] != sellable:
        warnings.append("Imported Sellable differed from calculated value and was replaced.")
    if parsed["Under Par"] != under_par:
        warnings.append("Imported Under Par differed from calculated value and was replaced.")
    if parsed["Storage Volume"] != storage_volume:
        warnings.append("Imported Storage Volume differed from calculated value and was replaced.")
    if parsed["In Stock"] or parsed["Allocated"]:
        warnings.append("In Stock and Allocated are not committed by metadata import; use the audited opening-balance workflow.")
    parsed["Sellable"] = sellable
    parsed["Under Par"] = under_par
    parsed["Storage Volume"] = storage_volume
    return parsed, errors, warnings


def parse_decimal(value: str) -> tuple[Decimal, str | None]:
    if value is None or str(value).strip() == "":
        return Decimal("0"), None
    try:
        return Decimal(str(value).strip().replace(",", "")), None
    except Exception:
        return Decimal("0"), f"invalid numeric value {value!r}"


def parse_bool(value: str) -> tuple[bool, str | None]:
    normalized = str(value or "").strip().lower()
    if normalized in BOOL_TRUE:
        return True, None
    if normalized in BOOL_FALSE:
        return False, None
    return False, f"invalid boolean value {value!r}"


def load_existing_item_maps(db: Session) -> tuple[dict[str, list[InventoryItem]], dict[str, list[InventoryItem]]]:
    items = list(db.scalars(select(InventoryItem)).all())
    by_sku: dict[str, list[InventoryItem]] = {}
    by_barcode: dict[str, list[InventoryItem]] = {}
    for item in items:
        if item.sku:
            by_sku.setdefault(item.sku, []).append(item)
        if item.barcode:
            by_barcode.setdefault(item.barcode, []).append(item)
    return by_sku, by_barcode


def row_error(row_number: int, sku: str | None, barcode: str | None, message: str, raw_row: dict) -> ImportRowError:
    return ImportRowError(row_number=row_number, sku=sku or None, barcode=barcode or None, error_message=message, raw_row=raw_row)


def create_payload_from_row(row: ParsedImportRow) -> InventoryItemCreate:
    values = dict(row.values)
    values["In Stock"] = 0
    values["Allocated"] = 0
    values["Sellable"] = 0
    return InventoryItemCreate.model_validate(values)


def serialize_preview_row(row: dict[str, object]) -> dict[str, object]:
    serialized = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            serialized[key] = int(value) if value == value.to_integral_value() else float(value)
        else:
            serialized[key] = value
    return serialized
