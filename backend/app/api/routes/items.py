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
from app.models.item_notes import ItemNote
from app.models.inventory import InventoryItem, InventoryItemLocation
from app.schemas.imports import ImportCommitResponse, ImportPreviewResponse
from app.schemas.inventory import InventoryItemLocationCreate, InventoryItemLocationListResponse, InventoryItemLocationRead, InventoryItemLocationUpdate
from app.schemas.items import InventoryItemCreate, InventoryItemListResponse, InventoryItemRead, InventoryItemUpdate
from app.services.item_import import create_payload_from_row, parse_items_csv, preview_from_parsed, read_upload_text
from app.services.item_control import build_item_activity, build_item_detail, commit_bulk_item_update, preview_bulk_item_update, search_items
from app.services.items import CANONICAL_ITEM_COLUMNS, apply_calculated_fields, apply_item_payload, item_to_csv_row
from app.services.location_inventory import ensure_default_item_location_from_item, get_or_create_item_location, recalculate_item_location, recalculate_item_totals, set_default_item_location, to_decimal

router = APIRouter(prefix="/items", tags=["items"])


def build_items_statement(
    search: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    include_non_inventory: bool = True,
    woo_sync_status: str | None = None,
    woo_product_id: int | None = None,
    woo_variation_id: int | None = None,
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
    if sku:
        statement = statement.where(InventoryItem.sku == sku)
    if barcode:
        statement = statement.where(InventoryItem.barcode == barcode)
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
    if woo_sync_status:
        statement = statement.where(InventoryItem.woo_sync_status == woo_sync_status)
    if woo_product_id is not None:
        statement = statement.where(InventoryItem.woo_product_id == woo_product_id)
    if woo_variation_id is not None:
        statement = statement.where(InventoryItem.woo_variation_id == woo_variation_id)
    return statement.order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())


@router.get("/search")
def search_items_endpoint(
    q: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    limit: int = 25,
    db: Session = Depends(get_db),
) -> dict:
    return search_items(db, q=q, sku=sku, barcode=barcode, brand=brand, category=category, limit=limit)


@router.post("/bulk/preview")
def preview_items_bulk_update(payload: dict, db: Session = Depends(get_db)) -> dict:
    return preview_bulk_item_update(db, payload.get("item_ids") or [], payload.get("updates") or {})


@router.post("/bulk/commit")
def commit_items_bulk_update(payload: dict, db: Session = Depends(get_db)) -> dict:
    return commit_bulk_item_update(db, payload.get("item_ids") or [], payload.get("updates") or {})


@router.get("", response_model=InventoryItemListResponse)
def list_items(
    search: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    include_non_inventory: bool = True,
    woo_sync_status: str | None = None,
    woo_product_id: int | None = None,
    woo_variation_id: int | None = None,
    db: Session = Depends(get_db),
) -> InventoryItemListResponse:
    statement = build_items_statement(search, sku, barcode, category, warehouse, inventory_location, brand, active, include_non_inventory, woo_sync_status, woo_product_id, woo_variation_id)
    items = list(db.scalars(statement).all())
    for item in items:
        apply_calculated_fields(item)
    return InventoryItemListResponse(items=items, total=len(items))


@router.get("/export")
def export_items(
    search: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    active: bool | None = None,
    include_non_inventory: bool = True,
    woo_sync_status: str | None = None,
    woo_product_id: int | None = None,
    woo_variation_id: int | None = None,
    db: Session = Depends(get_db),
) -> Response:
    statement = build_items_statement(search, sku, barcode, category, warehouse, inventory_location, brand, active, include_non_inventory, woo_sync_status, woo_product_id, woo_variation_id)
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
            db.flush()
            ensure_default_item_location_from_item(db, item, create_physical_location=True)
            created_count += 1
        else:
            apply_item_payload(row.existing_item, payload)
            db.add(row.existing_item)
            db.flush()
            ensure_default_item_location_from_item(db, row.existing_item, create_physical_location=True)
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


@router.get("/{item_id}/detail")
def get_item_detail(item_id: int, db: Session = Depends(get_db)) -> dict:
    return build_item_detail(db, item_id)


@router.get("/{item_id}/activity")
def get_item_activity(
    item_id: int,
    type: str | None = "all",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> dict:
    return build_item_activity(db, item_id, type_filter=type, start_date=start_date.date() if start_date else None, end_date=end_date.date() if end_date else None, limit=limit, offset=offset)


@router.get("/{item_id}/history")
def get_item_history(item_id: int, section: str = "stock-movements", limit: int = 50, db: Session = Depends(get_db)) -> dict:
    activity_type = {
        "receipts": "receipt",
        "cycle-counts": "cycle_count",
        "adjustments": "adjustment",
        "transfers": "transfer",
        "allocations": "allocation",
        "picks": "pick",
        "fulfillments": "fulfillment",
        "orders": "order",
        "stock-movements": "stock_movement",
    }.get(section, section)
    activity = build_item_activity(db, item_id, type_filter=activity_type, limit=limit, offset=0)
    return {"section": section, "rows": activity["activity"], "total": activity["total"]}


@router.get("/{item_id}/receipts")
def get_item_receipts(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "receipts", db=db)


@router.get("/{item_id}/cycle-counts")
def get_item_cycle_counts(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "cycle-counts", db=db)


@router.get("/{item_id}/adjustments")
def get_item_adjustments(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "adjustments", db=db)


@router.get("/{item_id}/transfers")
def get_item_transfers(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "transfers", db=db)


@router.get("/{item_id}/allocations")
def get_item_allocations(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "allocations", db=db)


@router.get("/{item_id}/picks")
def get_item_picks(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "picks", db=db)


@router.get("/{item_id}/fulfillments")
def get_item_fulfillments(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "fulfillments", db=db)


@router.get("/{item_id}/orders")
def get_item_orders(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "orders", db=db)


@router.get("/{item_id}/stock-movements")
def get_item_stock_movements(item_id: int, db: Session = Depends(get_db)) -> dict:
    return get_item_history(item_id, "stock-movements", db=db)


def item_note_to_dict(note: ItemNote) -> dict:
    return {
        "id": note.id,
        "inventory_item_id": note.inventory_item_id,
        "note": note.note,
        "note_type": note.note_type,
        "created_by": note.created_by,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }


@router.get("/{item_id}/notes")
def list_item_notes(item_id: int, db: Session = Depends(get_db)) -> dict:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    notes = list(db.scalars(select(ItemNote).where(ItemNote.inventory_item_id == item_id).order_by(ItemNote.created_at.desc(), ItemNote.id.desc())).all())
    return {"notes": [item_note_to_dict(note) for note in notes], "total": len(notes)}


@router.post("/{item_id}/notes", status_code=201)
def create_item_note(item_id: int, payload: dict, db: Session = Depends(get_db)) -> dict:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    note = ItemNote(inventory_item_id=item_id, note=payload.get("note") or "", note_type=payload.get("note_type") or "general", created_by=payload.get("created_by") or "system")
    if not note.note.strip():
        raise HTTPException(status_code=400, detail="Note is required")
    db.add(note)
    db.commit()
    db.refresh(note)
    return item_note_to_dict(note)


@router.patch("/{item_id}/notes/{note_id}")
def update_item_note(item_id: int, note_id: int, payload: dict, db: Session = Depends(get_db)) -> dict:
    note = db.get(ItemNote, note_id)
    if note is None or note.inventory_item_id != item_id:
        raise HTTPException(status_code=404, detail="Item note not found")
    if "note" in payload:
        note.note = payload["note"]
    if "note_type" in payload:
        note.note_type = payload["note_type"]
    db.commit()
    db.refresh(note)
    return item_note_to_dict(note)


@router.delete("/{item_id}/notes/{note_id}")
def delete_item_note(item_id: int, note_id: int, db: Session = Depends(get_db)) -> dict:
    note = db.get(ItemNote, note_id)
    if note is None or note.inventory_item_id != item_id:
        raise HTTPException(status_code=404, detail="Item note not found")
    db.delete(note)
    db.commit()
    return {"deleted": True, "id": note_id}


@router.get("/{item_id}/locations", response_model=InventoryItemLocationListResponse)
def list_item_locations(item_id: int, active: bool | None = None, db: Session = Depends(get_db)) -> InventoryItemLocationListResponse:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    statement = select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item_id)
    if active is not None:
        statement = statement.where(InventoryItemLocation.active.is_(active))
    rows = list(db.scalars(statement.order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.warehouse.asc(), InventoryItemLocation.inventory_location.asc())).all())
    return InventoryItemLocationListResponse(locations=[item_location_to_read(row, item) for row in rows], total=len(rows))


@router.post("/{item_id}/locations", response_model=InventoryItemLocationRead, status_code=201)
def create_item_location(item_id: int, payload: InventoryItemLocationCreate, db: Session = Depends(get_db)) -> InventoryItemLocationRead:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    row = get_or_create_item_location(
        db,
        item,
        payload.warehouse,
        payload.inventory_location,
        location_id=payload.location_id,
        is_default_location=payload.is_default_location,
        par_level=payload.par_level,
        active=payload.active,
    )
    db.commit()
    db.refresh(row)
    return item_location_to_read(row, item)


@router.patch("/{item_id}/locations/{item_location_id}", response_model=InventoryItemLocationRead)
def update_item_location(item_id: int, item_location_id: int, payload: InventoryItemLocationUpdate, db: Session = Depends(get_db)) -> InventoryItemLocationRead:
    item = db.get(InventoryItem, item_id)
    row = db.get(InventoryItemLocation, item_location_id)
    if item is None or row is None or row.inventory_item_id != item_id:
        raise HTTPException(status_code=404, detail="Item location not found")
    if payload.location_code is not None:
        row.location_code = payload.location_code
    if payload.location_name is not None:
        row.location_name = payload.location_name
    if payload.par_level is not None:
        row.par_level = to_decimal(payload.par_level)
    if payload.active is not None:
        row.active = payload.active
    if payload.is_default_location is not None:
        if payload.is_default_location:
            set_default_item_location(db, item_id, row)
        else:
            row.is_default_location = False
    recalculate_item_location(row, item)
    recalculate_item_totals(db, item_id)
    db.commit()
    db.refresh(row)
    return item_location_to_read(row, item)


@router.post("", response_model=InventoryItemRead, status_code=201)
def create_item(payload: InventoryItemCreate, db: Session = Depends(get_db)) -> InventoryItem:
    item = apply_item_payload(InventoryItem(), payload)
    db.add(item)
    db.flush()
    ensure_default_item_location_from_item(db, item)
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
    db.flush()
    ensure_default_item_location_from_item(db, item)
    db.commit()
    db.refresh(item)
    return item


def item_location_to_read(row: InventoryItemLocation, item: InventoryItem | None = None) -> InventoryItemLocationRead:
    item = item or row.inventory_item
    return InventoryItemLocationRead(
        id=row.id,
        item_id=row.inventory_item_id,
        sku=item.sku if item else None,
        barcode=item.barcode if item else None,
        description=item.description if item else None,
        warehouse=row.warehouse,
        inventory_location=row.inventory_location,
        location_code=row.location_code,
        location_name=row.location_name,
        is_default_location=row.is_default_location,
        in_stock=float(row.in_stock or 0),
        allocated=float(row.allocated or 0),
        sellable=float(row.sellable or 0),
        on_order=float(row.on_order or 0),
        par_level=float(row.par_level) if row.par_level is not None else None,
        under_par=row.under_par,
        active=row.active,
        updated_at=row.updated_at,
    )
