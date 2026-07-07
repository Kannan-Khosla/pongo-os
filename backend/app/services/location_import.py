import csv
from dataclasses import dataclass, field
from io import StringIO

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryLocation
from app.schemas.locations import LocationImportPreviewResponse, LocationImportPreviewRow, LocationImportRowError
from app.services.locations import CANONICAL_LOCATION_COLUMNS

BOOLEAN_COLUMNS = {"Default", "Active"}
REQUIRED_COLUMNS = {"Warehouse", "Location Code", "Location Name"}
BOOL_TRUE = {"true", "yes", "1", "y"}
BOOL_FALSE = {"false", "no", "0", "n"}


@dataclass
class ParsedLocationImportRow:
    row_number: int
    action: str
    values: dict[str, object]
    existing_location: InventoryLocation | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedLocationImport:
    total_rows: int
    valid_rows: list[ParsedLocationImportRow]
    skipped_count: int
    errors: list[LocationImportRowError]
    warnings: list[str]
    extra_columns: list[str]


async def read_upload_text(file: UploadFile) -> str:
    content = await file.read()
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV file must be UTF-8 encoded.") from exc


def parse_locations_csv(csv_text: str, db: Session) -> ParsedLocationImport:
    reader = csv.reader(StringIO(csv_text))
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise HTTPException(status_code=400, detail="CSV file is empty.") from exc

    header = [column.strip() for column in raw_header]
    missing_columns = [column for column in CANONICAL_LOCATION_COLUMNS if column not in header]
    extra_columns = [column for column in header if column not in CANONICAL_LOCATION_COLUMNS]
    if missing_columns:
        raise HTTPException(status_code=400, detail={"message": "CSV header is missing required canonical location columns.", "missing_columns": missing_columns})

    existing_by_key = load_existing_location_map(db)
    rows: list[ParsedLocationImportRow] = []
    skipped_count = 0
    errors: list[LocationImportRowError] = []
    warnings = [f"Extra column ignored: {column}" for column in extra_columns]

    for physical_row_number, raw_values in enumerate(reader, start=2):
        row = {column: "" for column in header}
        for index, column in enumerate(header):
            row[column] = raw_values[index].strip() if index < len(raw_values) else ""
        canonical_row = {column: row.get(column, "") for column in CANONICAL_LOCATION_COLUMNS}

        if not any(str(value).strip() for value in canonical_row.values()):
            skipped_count += 1
            continue

        parsed, row_errors = parse_location_row_values(canonical_row)
        warehouse = str(parsed.get("Warehouse") or "").strip()
        code = str(parsed.get("Location Code") or "").strip()
        name = str(parsed.get("Location Name") or "").strip()
        for required_column in REQUIRED_COLUMNS:
            if not str(parsed.get(required_column) or "").strip():
                row_errors.append(f"{required_column} is required for location import.")

        if row_errors:
            for message in row_errors:
                errors.append(row_error(physical_row_number, warehouse, code, message, canonical_row))
            continue

        key = (warehouse, code)
        existing_location = existing_by_key.get(key)
        action = "update" if existing_location else "create"
        rows.append(ParsedLocationImportRow(row_number=physical_row_number, action=action, values=parsed, existing_location=existing_location))

    return ParsedLocationImport(total_rows=len(rows) + skipped_count + len(errors), valid_rows=rows, skipped_count=skipped_count, errors=errors, warnings=warnings, extra_columns=extra_columns)


def preview_from_parsed(parsed: ParsedLocationImport) -> LocationImportPreviewResponse:
    preview_rows = [
        LocationImportPreviewRow(
            row_number=row.row_number,
            action=row.action,
            warehouse=str(row.values.get("Warehouse") or ""),
            code=str(row.values.get("Location Code") or ""),
            name=str(row.values.get("Location Name") or ""),
            warnings=row.warnings,
            row=row.values,
        )
        for row in parsed.valid_rows[:20]
    ]
    create_count = sum(1 for row in parsed.valid_rows if row.action == "create")
    update_count = sum(1 for row in parsed.valid_rows if row.action == "update")
    return LocationImportPreviewResponse(
        total_rows=parsed.total_rows,
        valid_rows=len(parsed.valid_rows),
        invalid_rows=len(parsed.errors),
        create_count=create_count,
        update_count=update_count,
        skipped_count=parsed.skipped_count,
        warnings=parsed.warnings,
        errors=parsed.errors,
        preview_rows=preview_rows,
    )


def parse_location_row_values(row: dict[str, str]) -> tuple[dict[str, object], list[str]]:
    parsed: dict[str, object] = {}
    errors: list[str] = []
    for column in CANONICAL_LOCATION_COLUMNS:
        value = row.get(column, "")
        if column == "Active" and str(value).strip() == "":
            parsed[column] = True
        elif column == "Default" and str(value).strip() == "":
            parsed[column] = False
        elif column in BOOLEAN_COLUMNS:
            parsed[column], error = parse_bool(value)
            if error:
                errors.append(f"{column}: {error}")
        else:
            parsed[column] = value.strip()
    return parsed, errors


def parse_bool(value: str) -> tuple[bool, str | None]:
    normalized = str(value or "").strip().lower()
    if normalized in BOOL_TRUE:
        return True, None
    if normalized in BOOL_FALSE:
        return False, None
    return False, f"invalid boolean value {value!r}"


def load_existing_location_map(db: Session) -> dict[tuple[str, str], InventoryLocation]:
    locations = list(db.scalars(select(InventoryLocation)).all())
    return {(location.warehouse or "", location.location_code or ""): location for location in locations if location.warehouse and location.location_code}


def row_error(row_number: int, warehouse: str | None, code: str | None, message: str, raw_row: dict) -> LocationImportRowError:
    return LocationImportRowError(row_number=row_number, warehouse=warehouse or None, code=code or None, error_message=message, raw_row=raw_row)


def values_to_location_payload(values: dict[str, object]) -> dict[str, object]:
    return {
        "warehouse": values["Warehouse"],
        "code": values["Location Code"],
        "name": values["Location Name"],
        "description": values["Description"],
        "zone": values["Zone"],
        "aisle": values["Aisle"],
        "rack": values["Rack"],
        "shelf": values["Shelf"],
        "bin": values["Bin"],
        "is_default": values["Default"],
        "is_active": values["Active"],
    }
