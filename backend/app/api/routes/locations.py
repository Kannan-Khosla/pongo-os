import csv
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.imports import ImportError as ImportErrorRow
from app.models.imports import ImportJob
from app.models.inventory import InventoryLocation
from app.schemas.locations import (
    InventoryLocationCreate,
    InventoryLocationListResponse,
    InventoryLocationRead,
    InventoryLocationUpdate,
    LocationImportCommitResponse,
    LocationImportPreviewResponse,
)
from app.services.location_import import parse_locations_csv, preview_from_parsed, read_upload_text, values_to_location_payload
from app.services.locations import CANONICAL_LOCATION_COLUMNS, apply_location_payload, location_to_csv_row, location_to_read

router = APIRouter(prefix="/locations", tags=["locations"])


def build_locations_statement(
    search: str | None = None,
    warehouse: str | None = None,
    code: str | None = None,
    name: str | None = None,
    zone: str | None = None,
    aisle: str | None = None,
    active: bool | None = None,
):
    statement = select(InventoryLocation)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                InventoryLocation.warehouse.ilike(pattern),
                InventoryLocation.location_code.ilike(pattern),
                InventoryLocation.location_name.ilike(pattern),
                InventoryLocation.description.ilike(pattern),
                InventoryLocation.zone.ilike(pattern),
                InventoryLocation.aisle.ilike(pattern),
            )
        )
    if warehouse:
        statement = statement.where(InventoryLocation.warehouse == warehouse)
    if code:
        statement = statement.where(InventoryLocation.location_code == code)
    if name:
        statement = statement.where(InventoryLocation.location_name == name)
    if zone:
        statement = statement.where(InventoryLocation.zone == zone)
    if aisle:
        statement = statement.where(InventoryLocation.aisle == aisle)
    if active is not None:
        statement = statement.where(InventoryLocation.active.is_(active))
    return statement.order_by(InventoryLocation.warehouse.asc().nullslast(), InventoryLocation.location_code.asc().nullslast(), InventoryLocation.id.asc())


@router.get("", response_model=InventoryLocationListResponse)
def list_locations(
    search: str | None = None,
    warehouse: str | None = None,
    code: str | None = None,
    name: str | None = None,
    zone: str | None = None,
    aisle: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
) -> InventoryLocationListResponse:
    locations = list(db.scalars(build_locations_statement(search, warehouse, code, name, zone, aisle, active)).all())
    return InventoryLocationListResponse(locations=[location_to_read(location) for location in locations], total=len(locations))


@router.get("/export")
def export_locations(
    search: str | None = None,
    warehouse: str | None = None,
    code: str | None = None,
    name: str | None = None,
    zone: str | None = None,
    aisle: str | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
) -> Response:
    locations = list(db.scalars(build_locations_statement(search, warehouse, code, name, zone, aisle, active)).all())
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CANONICAL_LOCATION_COLUMNS)
    writer.writeheader()
    for location in locations:
        writer.writerow(location_to_csv_row(location))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-locations-export.csv"'},
    )


@router.post("/import/preview", response_model=LocationImportPreviewResponse)
async def preview_locations_import(file: UploadFile = File(...), db: Session = Depends(get_db)) -> LocationImportPreviewResponse:
    csv_text = await read_upload_text(file)
    parsed = parse_locations_csv(csv_text, db)
    return preview_from_parsed(parsed)


@router.post("/import/commit", response_model=LocationImportCommitResponse)
async def commit_locations_import(file: UploadFile = File(...), db: Session = Depends(get_db)) -> LocationImportCommitResponse:
    csv_text = await read_upload_text(file)
    parsed = parse_locations_csv(csv_text, db)
    created_count = 0
    updated_count = 0

    import_job = ImportJob(
        file_name=file.filename,
        import_type="locations",
        total_rows=parsed.total_rows,
        successful_rows=0,
        failed_rows=len(parsed.errors),
        status="completed",
        created_by="system",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(import_job)
    db.flush()

    for error in parsed.errors:
        db.add(
            ImportErrorRow(
                import_job_id=import_job.id,
                row_number=error.row_number,
                sku=None,
                barcode=None,
                error_message=error.error_message,
                raw_row=error.raw_row,
            )
        )

    for row in parsed.valid_rows:
        payload = InventoryLocationCreate.model_validate(values_to_location_payload(row.values))
        if row.existing_location is None:
            location = apply_location_payload(InventoryLocation(), payload)
            db.add(location)
            db.flush()
            created_count += 1
        else:
            location = apply_location_payload(row.existing_location, payload)
            db.add(location)
            db.flush()
            updated_count += 1
        if location.is_default:
            clear_other_defaults(db, location.warehouse, location.id)

    import_job.successful_rows = created_count + updated_count
    import_job.failed_rows = len(parsed.errors)
    db.commit()
    db.refresh(import_job)

    return LocationImportCommitResponse(
        import_job_id=import_job.id,
        total_rows=parsed.total_rows,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=parsed.skipped_count,
        failed_count=len(parsed.errors),
        warnings=parsed.warnings,
        errors=parsed.errors,
    )


@router.get("/{location_id}", response_model=InventoryLocationRead)
def get_location(location_id: int, db: Session = Depends(get_db)) -> InventoryLocationRead:
    return location_to_read(get_location_or_404(location_id, db))


@router.post("", response_model=InventoryLocationRead, status_code=201)
def create_location(payload: InventoryLocationCreate, db: Session = Depends(get_db)) -> InventoryLocationRead:
    ensure_unique_location(db, payload.warehouse, payload.code)
    location = apply_location_payload(InventoryLocation(), payload)
    db.add(location)
    db.flush()
    if location.is_default:
        clear_other_defaults(db, location.warehouse, location.id)
    db.commit()
    db.refresh(location)
    return location_to_read(location)


@router.patch("/{location_id}", response_model=InventoryLocationRead)
def update_location(location_id: int, payload: InventoryLocationUpdate, db: Session = Depends(get_db)) -> InventoryLocationRead:
    location = get_location_or_404(location_id, db)
    next_warehouse = payload.warehouse if payload.warehouse is not None else location.warehouse
    next_code = payload.code if payload.code is not None else location.location_code
    if next_warehouse != location.warehouse or next_code != location.location_code:
        ensure_unique_location(db, next_warehouse, next_code, exclude_id=location.id)
    apply_location_payload(location, payload, partial=True)
    db.add(location)
    db.flush()
    if location.is_default:
        clear_other_defaults(db, location.warehouse, location.id)
    db.commit()
    db.refresh(location)
    return location_to_read(location)


@router.delete("/{location_id}", response_model=InventoryLocationRead)
def deactivate_location(location_id: int, db: Session = Depends(get_db)) -> InventoryLocationRead:
    location = get_location_or_404(location_id, db)
    location.active = False
    db.add(location)
    db.commit()
    db.refresh(location)
    return location_to_read(location)


def get_location_or_404(location_id: int, db: Session) -> InventoryLocation:
    location = db.get(InventoryLocation, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return location


def ensure_unique_location(db: Session, warehouse: str | None, code: str | None, exclude_id: int | None = None) -> None:
    statement = select(InventoryLocation).where(InventoryLocation.warehouse == warehouse, InventoryLocation.location_code == code)
    if exclude_id is not None:
        statement = statement.where(InventoryLocation.id != exclude_id)
    if db.scalars(statement).first() is not None:
        raise HTTPException(status_code=409, detail="Location code already exists for this warehouse.")


def clear_other_defaults(db: Session, warehouse: str | None, location_id: int) -> None:
    if not warehouse:
        return
    existing_defaults = db.scalars(select(InventoryLocation).where(InventoryLocation.warehouse == warehouse, InventoryLocation.id != location_id, InventoryLocation.is_default.is_(True))).all()
    for existing_location in existing_defaults:
        existing_location.is_default = False
        db.add(existing_location)
