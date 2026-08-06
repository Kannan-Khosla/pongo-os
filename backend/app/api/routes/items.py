import csv
from io import StringIO
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.imports import ImportError as ImportErrorRow
from app.models.imports import ImportJob
from app.models.item_notes import ItemNote
from app.models.inventory import InventoryItem, InventoryItemLocation
from app.models.orders import Order, OrderItem
from app.schemas.imports import ImportCommitResponse, ImportPreviewResponse
from app.schemas.inventory import InventoryItemLocationCreate, InventoryItemLocationListResponse, InventoryItemLocationRead, InventoryItemLocationUpdate
from app.schemas.items import InventoryItemCreate, InventoryItemListResponse, InventoryItemRead, InventoryItemUpdate, InventoryOpeningBalanceRequest
from app.services.item_import import create_payload_from_row, parse_items_csv, preview_from_parsed, read_upload_text
from app.services.auth import authenticated_actor
from app.services.item_enrichment import commit_enrichment, enrichment_csv, parse_enrichment_csv, preview_enrichment
from app.services.item_control import build_item_activity, build_item_detail, commit_bulk_item_update, item_keyword_predicates, preview_bulk_item_update, search_items
from app.services.items import CANONICAL_ITEM_COLUMNS, apply_calculated_fields, apply_item_payload, item_to_csv_row
from app.services.location_inventory import ensure_default_item_location_from_item, get_or_create_item_location, lock_inventory_stock, recalculate_item_location, recalculate_item_totals, set_default_item_location, set_opening_balance, to_decimal
from app.services.stock_mutation_guard import IdempotencyConflict

router = APIRouter(prefix="/items", tags=["items"])


ITEM_SORT_COLUMNS = {
    "sku": InventoryItem.sku,
    "barcode": InventoryItem.barcode,
    "description": func.coalesce(InventoryItem.woo_name, InventoryItem.description),
    "brand": InventoryItem.brand,
    "category": InventoryItem.category,
    "in_stock": InventoryItem.in_stock,
    "allocated": InventoryItem.allocated,
    "sellable": InventoryItem.sellable,
    "unit_cost": InventoryItem.unit_cost,
    "sales_price": InventoryItem.sales_price,
    "updated_at": InventoryItem.updated_at,
}

DATA_QUALITY_FILTERS = {
    "missing_barcode",
    "missing_brand",
    "missing_cost",
    "unmapped",
    "receiving",
    "missing_location",
}
ItemStockStatus = Literal["in_stock", "out_of_stock", "under_par", "negative_sellable"]


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
    data_quality: str | None = None,
    stock_status: ItemStockStatus | None = None,
):
    statement = select(InventoryItem)
    if search:
        statement = statement.where(*item_keyword_predicates(search))
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
    if stock_status == "in_stock":
        statement = statement.where(InventoryItem.in_stock > 0)
    elif stock_status == "out_of_stock":
        statement = statement.where(InventoryItem.in_stock <= 0)
    elif stock_status == "under_par":
        statement = statement.where(InventoryItem.under_par.is_(True))
    elif stock_status == "negative_sellable":
        statement = statement.where(InventoryItem.sellable < 0)
    quality_filters = parse_data_quality_filters(data_quality)
    if quality_filters:
        predicates = []
        if "missing_barcode" in quality_filters:
            predicates.append(func.trim(func.coalesce(InventoryItem.barcode, "")) == "")
        if "missing_brand" in quality_filters:
            predicates.append(func.trim(func.coalesce(InventoryItem.brand, "")) == "")
        if "missing_cost" in quality_filters:
            predicates.append(InventoryItem.unit_cost.is_(None))
        if "unmapped" in quality_filters:
            predicates.append(InventoryItem.woo_product_id.is_(None))
        if "receiving" in quality_filters:
            receiving_location = and_(
                InventoryItemLocation.active.is_(True),
                func.lower(func.trim(func.coalesce(InventoryItemLocation.inventory_location, ""))) == "receiving",
            )
            predicates.append(
                or_(
                    func.lower(func.trim(func.coalesce(InventoryItem.inventory_location, ""))) == "receiving",
                    InventoryItem.locations.any(receiving_location),
                )
            )
        if "missing_location" in quality_filters:
            usable_location = and_(
                InventoryItemLocation.active.is_(True),
                func.trim(func.coalesce(InventoryItemLocation.warehouse, "")) != "",
                func.trim(func.coalesce(InventoryItemLocation.inventory_location, "")) != "",
            )
            predicates.append(~InventoryItem.locations.any(usable_location))
        statement = statement.where(or_(*predicates))
    return statement.order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())


def parse_data_quality_filters(value: str | None) -> set[str]:
    if not value or not value.strip():
        return set()
    filters = {part.strip().lower() for part in value.split(",") if part.strip()}
    invalid = filters - DATA_QUALITY_FILTERS
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported data_quality filter: {', '.join(sorted(invalid))}")
    return filters


def get_open_order_totals(db: Session, item_ids: list[int]) -> dict[int, dict[str, float | int]]:
    if not item_ids:
        return {}
    closed_statuses = {"cancelled", "canceled", "completed", "fulfilled", "refunded", "skipped"}
    remaining_quantity = func.coalesce(OrderItem.quantity_ordered, 0) - func.coalesce(OrderItem.quantity_fulfilled, 0)
    statement = (
        select(
            OrderItem.inventory_item_id,
            func.count(func.distinct(OrderItem.order_id)),
            func.coalesce(func.sum(remaining_quantity), 0),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(OrderItem.inventory_item_id.in_(item_ids))
        .where(~func.lower(func.coalesce(Order.local_status, "")).in_(closed_statuses))
        .where(remaining_quantity > 0)
        .group_by(OrderItem.inventory_item_id)
    )
    return {
        item_id: {"count": int(order_count or 0), "quantity": float(quantity or 0)}
        for item_id, order_count, quantity in db.execute(statement).all()
        if item_id is not None
    }


def get_item_facets(db: Session) -> dict[str, list[str]]:
    def values_for(column) -> list[str]:
        statement = (
            select(column)
            .where(column.is_not(None), func.trim(column) != "")
            .distinct()
            .order_by(column.asc())
        )
        return [str(value) for value in db.scalars(statement).all()]

    return {
        "categories": values_for(InventoryItem.category),
        "brands": values_for(InventoryItem.brand),
    }


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
def commit_items_bulk_update(payload: dict, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    return commit_bulk_item_update(db, payload.get("item_ids") or [], payload.get("updates") or {}, created_by=actor)


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
    data_quality: str | None = None,
    stock_status: ItemStockStatus | None = None,
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    sort_by: Literal["sku", "barcode", "description", "brand", "category", "in_stock", "allocated", "sellable", "unit_cost", "sales_price", "updated_at"] = "sku",
    sort_direction: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
) -> InventoryItemListResponse:
    statement = build_items_statement(
        search=search,
        sku=sku,
        barcode=barcode,
        category=category,
        warehouse=warehouse,
        inventory_location=inventory_location,
        brand=brand,
        active=active,
        include_non_inventory=include_non_inventory,
        woo_sync_status=woo_sync_status,
        woo_product_id=woo_product_id,
        woo_variation_id=woo_variation_id,
        data_quality=data_quality,
        stock_status=stock_status,
    )
    total = int(db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
    sort_column = ITEM_SORT_COLUMNS[sort_by]
    sort_expression = sort_column.desc().nullslast() if sort_direction == "desc" else sort_column.asc().nullslast()
    statement = statement.order_by(None).order_by(sort_expression, InventoryItem.id.asc())
    pagination_requested = page is not None or page_size is not None
    effective_page_size = page_size or 20
    total_pages = (total + effective_page_size - 1) // effective_page_size if effective_page_size else 0
    effective_page = min(page or 1, max(total_pages, 1)) if pagination_requested else 1
    if pagination_requested:
        statement = statement.offset((effective_page - 1) * effective_page_size).limit(effective_page_size)
    items = list(db.scalars(statement).all())
    open_order_totals = get_open_order_totals(db, [item.id for item in items])
    for item in items:
        apply_calculated_fields(item)
        totals = open_order_totals.get(item.id, {"count": 0, "quantity": 0})
        item.open_orders_count = totals["count"]
        item.open_order_quantity = totals["quantity"]
    if not pagination_requested:
        effective_page_size = len(items)
        total_pages = (total + effective_page_size - 1) // effective_page_size if effective_page_size else 0
    return InventoryItemListResponse(
        items=items,
        total=total,
        page=effective_page,
        page_size=effective_page_size,
        total_pages=total_pages,
        returned_count=len(items),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
        facets=get_item_facets(db),
    )


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
    data_quality: str | None = None,
    stock_status: ItemStockStatus | None = None,
    db: Session = Depends(get_db),
) -> Response:
    statement = build_items_statement(
        search=search,
        sku=sku,
        barcode=barcode,
        category=category,
        warehouse=warehouse,
        inventory_location=inventory_location,
        brand=brand,
        active=active,
        include_non_inventory=include_non_inventory,
        woo_sync_status=woo_sync_status,
        woo_product_id=woo_product_id,
        woo_variation_id=woo_variation_id,
        data_quality=data_quality,
        stock_status=stock_status,
    )
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


@router.get("/enrichment/export")
def export_items_enrichment(db: Session = Depends(get_db)) -> Response:
    items = list(db.scalars(
        select(InventoryItem)
        .where(InventoryItem.woo_product_id.is_not(None))
        .order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())
    ).all())
    return Response(
        content=enrichment_csv(items),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-woo-enrichment-template.csv"'},
    )


@router.post("/enrichment/preview")
async def preview_items_enrichment(
    file: UploadFile = File(...),
    import_opening_stock: bool = Form(False),
    db: Session = Depends(get_db),
) -> dict:
    csv_text = await read_upload_text(file)
    return preview_enrichment(parse_enrichment_csv(csv_text, db, import_opening_stock=import_opening_stock))


@router.post("/enrichment/commit")
async def commit_items_enrichment(
    file: UploadFile = File(...),
    import_opening_stock: bool = Form(False),
    db: Session = Depends(get_db),
    actor: str = Depends(authenticated_actor),
) -> dict:
    csv_text = await read_upload_text(file)
    return commit_enrichment(csv_text, db, file_name=file.filename, import_opening_stock=import_opening_stock, created_by=actor)


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def preview_items_import(file: UploadFile = File(...), db: Session = Depends(get_db)) -> ImportPreviewResponse:
    csv_text = await read_upload_text(file)
    parsed = parse_items_csv(csv_text, db)
    return preview_from_parsed(parsed)


@router.post("/import/commit", response_model=ImportCommitResponse)
async def commit_items_import(file: UploadFile = File(...), db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> ImportCommitResponse:
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
        created_by=actor,
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
def create_item_note(item_id: int, payload: dict, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    note = ItemNote(inventory_item_id=item_id, note=payload.get("note") or "", note_type=payload.get("note_type") or "general", created_by=actor)
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
    lock_inventory_stock(db, {item_id})
    item = db.get(InventoryItem, item_id, populate_existing=True)
    row = db.get(InventoryItemLocation, item_location_id, populate_existing=True)
    if item is None or row is None or row.inventory_item_id != item_id:
        raise HTTPException(status_code=404, detail="Item location not found")
    if payload.location_code is not None:
        row.location_code = payload.location_code
    if payload.location_name is not None:
        row.location_name = payload.location_name
    if payload.par_level is not None:
        row.par_level = to_decimal(payload.par_level)
    if payload.active is not None:
        if payload.active is False and (
            to_decimal(row.in_stock) != 0
            or to_decimal(row.allocated) != 0
            or to_decimal(row.on_order) != 0
        ):
            raise HTTPException(status_code=409, detail="Transfer or adjust this location to zero before deactivating it.")
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
    if {"in_stock", "allocated"} & payload.model_fields_set and (to_decimal(payload.in_stock) != 0 or to_decimal(payload.allocated) != 0):
        raise HTTPException(status_code=422, detail="Create the item first, then use its explicit opening-balance endpoint for In Stock or Allocated quantities.")
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
    if {"in_stock", "allocated"} & payload.model_fields_set:
        raise HTTPException(status_code=422, detail="In Stock and Allocated can only change through audited stock workflows.")
    apply_item_payload(item, payload, partial=True)
    db.add(item)
    db.flush()
    ensure_default_item_location_from_item(db, item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/opening-balance")
def create_item_opening_balance(item_id: int, payload: InventoryOpeningBalanceRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    try:
        return set_opening_balance(
            db,
            item_id,
            in_stock=to_decimal(payload.in_stock),
            allocated=to_decimal(payload.allocated),
            warehouse=payload.warehouse,
            inventory_location=payload.inventory_location,
            idempotency_key=payload.idempotency_key,
            created_by=actor,
        )
    except IdempotencyConflict as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error


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
