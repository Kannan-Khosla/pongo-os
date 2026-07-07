import csv
from io import StringIO
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.imports import ImportError as ImportErrorRow
from app.models.imports import ImportJob
from app.models.inventory import InventoryItem
from app.schemas.imports import ImportCommitResponse, ImportPreviewResponse
from app.schemas.items import InventoryItemCreate, InventoryItemListResponse, InventoryItemRead, InventoryItemUpdate
from app.services.item_import import create_payload_from_row, parse_items_csv, preview_from_parsed, read_upload_text
from app.services.items import CANONICAL_ITEM_COLUMNS, apply_calculated_fields, apply_item_payload, item_to_csv_row

router = APIRouter(prefix="/items", tags=["items"])


def build_items_statement(
    search: str | None = None,
    category: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    include_non_inventory: bool = True,
):
    statement = select(InventoryItem)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                InventoryItem.sku.ilike(pattern),
                InventoryItem.barcode.ilike(pattern),
                InventoryItem.description.ilike(pattern),
                InventoryItem.category.ilike(pattern),
                InventoryItem.brand.ilike(pattern),
                InventoryItem.manufacturer.ilike(pattern),
                InventoryItem.warehouse.ilike(pattern),
                InventoryItem.inventory_location.ilike(pattern),
            )
        )
    if category:
        statement = statement.where(InventoryItem.category == category)
    if warehouse:
        statement = statement.where(InventoryItem.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(InventoryItem.inventory_location == inventory_location)
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if active is not None:
        statement = statement.where(InventoryItem.active.is_(active))
    if not include_non_inventory:
        statement = statement.where(InventoryItem.non_inventory.is_(False))
    return statement.order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())


@router.get("", response_model=InventoryItemListResponse)
def list_items(
    search: str | None = None,
    category: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    include_non_inventory: bool = True,
    db: Session = Depends(get_db),
) -> InventoryItemListResponse:
    statement = build_items_statement(search, category, warehouse, inventory_location, brand, active, include_non_inventory)
    items = list(db.scalars(statement).all())
    for item in items:
        apply_calculated_fields(item)
    return InventoryItemListResponse(items=items, total=len(items))


@router.get("/export")
def export_items(
    search: str | None = None,
    category: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    include_non_inventory: bool = True,
    db: Session = Depends(get_db),
) -> Response:
    statement = build_items_statement(search, category, warehouse, inventory_location, brand, active, include_non_inventory)
    items = list(db.scalars(statement).all())
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CANONICAL_ITEM_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(item_to_csv_row(item))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-inventory-items-export.csv"'},
    )


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def preview_items_import(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ImportPreviewResponse:
    csv_text = await read_upload_text(file)
    parsed = parse_items_csv(csv_text, db)
    return preview_from_parsed(parsed)


@router.post("/import/commit", response_model=ImportCommitResponse)
async def commit_items_import(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ImportCommitResponse:
    csv_text = await read_upload_text(file)
    parsed = parse_items_csv(csv_text, db)
    created_count = 0
    updated_count = 0

    import_job = ImportJob(
        file_name=file.filename,
        import_type="items",
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
                sku=error.sku,
                barcode=error.barcode,
                error_message=error.error_message,
                raw_row=error.raw_row,
            )
        )

    for row in parsed.valid_rows:
        payload = create_payload_from_row(row)
        if row.existing_item is None:
            item = apply_item_payload(InventoryItem(), payload)
            db.add(item)
            created_count += 1
        else:
            apply_item_payload(row.existing_item, payload)
            db.add(row.existing_item)
            updated_count += 1

    import_job.successful_rows = created_count + updated_count
    import_job.failed_rows = len(parsed.errors)
    db.commit()
    db.refresh(import_job)

    return ImportCommitResponse(
        import_job_id=import_job.id,
        total_rows=parsed.total_rows,
        created_count=created_count,
        updated_count=updated_count,
        skipped_count=parsed.skipped_count,
        failed_count=len(parsed.errors),
        errors=parsed.errors,
    )


@router.get("/{item_id}", response_model=InventoryItemRead)
def get_item(item_id: int, db: Session = Depends(get_db)) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    apply_calculated_fields(item)
    return item


@router.post("", response_model=InventoryItemRead, status_code=201)
def create_item(payload: InventoryItemCreate, db: Session = Depends(get_db)) -> InventoryItem:
    item = apply_item_payload(InventoryItem(), payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=InventoryItemRead)
def update_item(item_id: int, payload: InventoryItemUpdate, db: Session = Depends(get_db)) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    apply_item_payload(item, payload, partial=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
