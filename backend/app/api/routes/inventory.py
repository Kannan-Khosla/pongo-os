import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.inventory import InventoryItem, InventoryItemLocation, InventoryTransfer, InventoryTransferLine, StockAdjustment, StockAdjustmentLine
from app.schemas.inventory import (
    InventoryItemLocationRead,
    InventoryLocationInventoryListResponse,
    InventoryLocationSummaryResponse,
    InventoryTransferDetail,
    InventoryTransferLineRead,
    InventoryTransferListResponse,
    InventoryTransferRead,
    InventoryTransferRequest,
    StockAdjustmentDetail,
    StockAdjustmentLineRead,
    StockAdjustmentListResponse,
    StockAdjustmentRead,
    StockAdjustmentRequest,
)
from app.services.inventory_reports import INVENTORY_BY_LOCATION_COLUMNS, get_inventory_items, item_to_inventory_by_location_row, query_inventory_summary
from app.services.auth import authenticated_actor
from app.services.item_identifiers import barcode_scan_candidates
from app.services.location_inventory import create_committed_adjustment_batch, create_committed_transfer_batch, recalculate_item_location
from app.services.order_workflow import auto_allocate_processing_orders_fifo
from app.services.stock_mutation_guard import IdempotencyConflict
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_writeback import sync_inventory_stock

router = APIRouter(prefix="/inventory", tags=["inventory"])


LOCATION_EXPORT_COLUMNS = [
    "Client",
    "SKU",
    "Barcode",
    "Description",
    "Category",
    "Brand",
    "Warehouse",
    "Inventory Location",
    "Default Location",
    "Location Code",
    "Location Name",
    "In Stock",
    "Allocated",
    "Sellable",
    "Under Par",
    "On Order",
    "Unit Cost",
    "Inventory Value",
    "Updated At",
]


@router.get("/locations", response_model=InventoryLocationInventoryListResponse)
def list_inventory_locations(
    search: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    item_id: int | None = None,
    item_ids: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    under_par: bool | None = None,
    active: bool | None = True,
    has_stock: bool | None = None,
    negative_sellable: bool | None = None,
    allocated_gt_stock: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> InventoryLocationInventoryListResponse:
    parsed_item_ids = parse_item_ids(item_ids)
    statement = build_inventory_location_statement(search, sku, barcode, item_id, parsed_item_ids, warehouse, inventory_location, brand, category, under_par, active, has_stock, negative_sellable, allocated_gt_stock)
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    total_pages = (total + page_size - 1) // page_size
    effective_page = min(page, max(total_pages, 1))
    rows = list(
        db.scalars(
            statement
            .options(selectinload(InventoryItemLocation.inventory_item))
            .order_by(
                InventoryItemLocation.warehouse.asc().nullslast(),
                InventoryItemLocation.inventory_location.asc().nullslast(),
                InventoryItem.sku.asc().nullslast(),
                InventoryItemLocation.id.asc(),
            )
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return InventoryLocationInventoryListResponse(
        rows=[item_location_to_read(row) for row in rows],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(rows),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/locations/export")
def export_inventory_locations(
    search: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    item_id: int | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    under_par: bool | None = None,
    active: bool | None = True,
    has_stock: bool | None = None,
    negative_sellable: bool | None = None,
    allocated_gt_stock: bool | None = None,
    db: Session = Depends(get_db),
) -> Response:
    rows = query_inventory_location_rows(db, search, sku, barcode, item_id, None, warehouse, inventory_location, brand, category, under_par, active, has_stock, negative_sellable, allocated_gt_stock, None, 0)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=LOCATION_EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        item = row.inventory_item
        in_stock = row.in_stock or 0
        unit_cost = item.unit_cost
        writer.writerow(
            {
                "Client": item.client or row.client or "",
                "SKU": item.sku or "",
                "Barcode": item.barcode or "",
                "Description": item.description or "",
                "Category": item.category or "",
                "Brand": item.brand or "",
                "Warehouse": row.warehouse or "",
                "Inventory Location": row.inventory_location or "",
                "Default Location": "Yes" if row.is_default_location else "No",
                "Location Code": row.location_code or "",
                "Location Name": row.location_name or "",
                "In Stock": in_stock,
                "Allocated": row.allocated or 0,
                "Sellable": row.sellable or 0,
                "Under Par": row.under_par,
                "On Order": row.on_order or 0,
                "Unit Cost": unit_cost if unit_cost is not None else "",
                "Inventory Value": in_stock * unit_cost if unit_cost is not None else "",
                "Updated At": row.updated_at.isoformat() if row.updated_at else "",
            }
        )
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="pongo-location-inventory-export.csv"'})


@router.post("/transfers", response_model=InventoryTransferDetail, status_code=201)
def commit_inventory_transfer(payload: InventoryTransferRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> InventoryTransferDetail:
    try:
        transfer = create_committed_transfer_batch(
            db,
            [line.model_dump() for line in payload.lines],
            notes=payload.notes,
            created_by=actor,
            idempotency_key=payload.idempotency_key,
        )
        db.commit()
        transfer = db.scalars(select(InventoryTransfer).where(InventoryTransfer.id == transfer.id).options(selectinload(InventoryTransfer.lines))).one()
        return transfer_to_detail(transfer)
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/transfers", response_model=InventoryTransferListResponse)
def list_inventory_transfers(
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> InventoryTransferListResponse:
    predicates = []
    if status:
        predicates.append(InventoryTransfer.status == status)
    total = int(db.scalar(select(func.count(InventoryTransfer.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    transfers = list(
        db.scalars(
            select(InventoryTransfer)
            .where(*predicates)
            .options(selectinload(InventoryTransfer.lines))
            .order_by(InventoryTransfer.created_at.desc(), InventoryTransfer.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return InventoryTransferListResponse(
        transfers=[transfer_to_read(transfer) for transfer in transfers],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(transfers),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/transfers/{transfer_id}", response_model=InventoryTransferDetail)
def get_inventory_transfer(transfer_id: int, db: Session = Depends(get_db)) -> InventoryTransferDetail:
    transfer = db.scalars(select(InventoryTransfer).where(InventoryTransfer.id == transfer_id).options(selectinload(InventoryTransfer.lines))).one_or_none()
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer_to_detail(transfer)


@router.post("/adjustments", response_model=StockAdjustmentDetail, status_code=201)
def commit_stock_adjustment(payload: StockAdjustmentRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> StockAdjustmentDetail:
    try:
        adjustment = create_committed_adjustment_batch(
            db,
            [line.model_dump() for line in payload.lines],
            adjustment_type=payload.adjustment_type,
            reason=payload.reason,
            notes=payload.notes,
            created_by=actor,
            idempotency_key=payload.idempotency_key,
        )
        replayed = bool(getattr(adjustment, "_idempotent_replay", False))
        if not replayed:
            auto_allocate_processing_orders_fifo(db, source=f"stock-adjustment:{adjustment.adjustment_number}")
        db.commit()
        adjustment = db.scalars(select(StockAdjustment).where(StockAdjustment.id == adjustment.id).options(selectinload(StockAdjustment.lines))).one()
        if not replayed:
            settings = effective_woocommerce_settings(db, get_settings())
            sync_inventory_stock(
                db,
                settings,
                WooCommerceClient(settings),
                item_ids={line.item_id for line in payload.lines},
                requested_by=actor,
            )
        return adjustment_to_detail(adjustment)
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/adjustments", response_model=StockAdjustmentListResponse)
def list_stock_adjustments(
    status: str | None = None,
    adjustment_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> StockAdjustmentListResponse:
    predicates = []
    if status:
        predicates.append(StockAdjustment.status == status)
    if adjustment_type:
        predicates.append(StockAdjustment.adjustment_type == adjustment_type)
    total = int(db.scalar(select(func.count(StockAdjustment.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    adjustments = list(
        db.scalars(
            select(StockAdjustment)
            .where(*predicates)
            .options(selectinload(StockAdjustment.lines))
            .order_by(StockAdjustment.created_at.desc(), StockAdjustment.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return StockAdjustmentListResponse(
        adjustments=[adjustment_to_read(adjustment) for adjustment in adjustments],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(adjustments),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/adjustments/{adjustment_id}", response_model=StockAdjustmentDetail)
def get_stock_adjustment(adjustment_id: int, db: Session = Depends(get_db)) -> StockAdjustmentDetail:
    adjustment = db.scalars(select(StockAdjustment).where(StockAdjustment.id == adjustment_id).options(selectinload(StockAdjustment.lines))).one_or_none()
    if adjustment is None:
        raise HTTPException(status_code=404, detail="Adjustment not found")
    return adjustment_to_detail(adjustment)


@router.get("/export/by-location")
def export_inventory_by_location(
    warehouse: str | None = None,
    inventory_location: str | None = None,
    default_location: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    under_par: bool | None = None,
    non_inventory: bool | None = None,
    db: Session = Depends(get_db),
) -> Response:
    items = get_inventory_items(
        db,
        warehouse=warehouse,
        inventory_location=inventory_location,
        default_location=default_location,
        category=category,
        brand=brand,
        under_par=under_par,
        non_inventory=non_inventory,
    )
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=INVENTORY_BY_LOCATION_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(item_to_inventory_by_location_row(item))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-inventory-by-location-export.csv"'},
    )


@router.get("/summary/by-location", response_model=InventoryLocationSummaryResponse)
def summarize_inventory_by_location(
    search: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    default_location: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    under_par: bool | None = None,
    non_inventory: bool | None = None,
    data_quality: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        return query_inventory_summary(
            db,
            search=search,
            warehouse=warehouse,
            inventory_location=inventory_location,
            default_location=default_location,
            category=category,
            brand=brand,
            under_par=under_par,
            non_inventory=non_inventory,
            data_quality=data_quality,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def query_inventory_location_rows(
    db: Session,
    search: str | None,
    sku: str | None,
    barcode: str | None,
    item_id: int | None,
    item_ids: list[int] | None,
    warehouse: str | None,
    inventory_location: str | None,
    brand: str | None,
    category: str | None,
    under_par: bool | None,
    active: bool | None,
    has_stock: bool | None,
    negative_sellable: bool | None,
    allocated_gt_stock: bool | None,
    limit: int | None,
    offset: int,
) -> list[InventoryItemLocation]:
    statement = build_inventory_location_statement(search, sku, barcode, item_id, item_ids, warehouse, inventory_location, brand, category, under_par, active, has_stock, negative_sellable, allocated_gt_stock)
    statement = statement.options(selectinload(InventoryItemLocation.inventory_item))
    statement = statement.order_by(
        InventoryItemLocation.warehouse.asc().nullslast(),
        InventoryItemLocation.inventory_location.asc().nullslast(),
        InventoryItem.sku.asc().nullslast(),
        InventoryItemLocation.id.asc(),
    )
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(max(1, min(limit, 1000)))
    return list(db.scalars(statement).all())


def build_inventory_location_statement(
    search: str | None,
    sku: str | None,
    barcode: str | None,
    item_id: int | None,
    item_ids: list[int] | None,
    warehouse: str | None,
    inventory_location: str | None,
    brand: str | None,
    category: str | None,
    under_par: bool | None,
    active: bool | None,
    has_stock: bool | None,
    negative_sellable: bool | None,
    allocated_gt_stock: bool | None,
):
    statement = select(InventoryItemLocation).join(InventoryItem)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                InventoryItem.sku.ilike(pattern),
                InventoryItem.barcode.ilike(pattern),
                InventoryItem.barcode.in_(barcode_scan_candidates(search)),
                InventoryItem.description.ilike(pattern),
                InventoryItem.brand.ilike(pattern),
                InventoryItem.category.ilike(pattern),
                InventoryItemLocation.warehouse.ilike(pattern),
                InventoryItemLocation.inventory_location.ilike(pattern),
                InventoryItemLocation.location_code.ilike(pattern),
                InventoryItemLocation.location_name.ilike(pattern),
            )
        )
    if sku:
        statement = statement.where(InventoryItem.sku == sku)
    if barcode:
        statement = statement.where(InventoryItem.barcode.in_(barcode_scan_candidates(barcode)))
    if item_id is not None:
        statement = statement.where(InventoryItemLocation.inventory_item_id == item_id)
    if item_ids is not None:
        statement = statement.where(InventoryItemLocation.inventory_item_id.in_(item_ids))
    if warehouse:
        statement = statement.where(InventoryItemLocation.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(InventoryItemLocation.inventory_location == inventory_location)
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if category:
        statement = statement.where(InventoryItem.category == category)
    if under_par is not None:
        statement = statement.where(InventoryItemLocation.under_par.is_(under_par))
    if active is not None:
        statement = statement.where(InventoryItemLocation.active.is_(active))
    if has_stock is True:
        statement = statement.where(InventoryItemLocation.in_stock > 0)
    elif has_stock is False:
        statement = statement.where(InventoryItemLocation.in_stock <= 0)
    if negative_sellable:
        statement = statement.where(InventoryItemLocation.sellable < 0)
    if allocated_gt_stock:
        statement = statement.where(InventoryItemLocation.allocated > InventoryItemLocation.in_stock)
    return statement


def parse_item_ids(value: str | None) -> list[int] | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise HTTPException(status_code=422, detail="item_ids must contain at least one positive integer")
    try:
        item_ids = [int(part) for part in parts]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="item_ids must be a comma-separated list of positive integers") from exc
    if any(item_id <= 0 for item_id in item_ids):
        raise HTTPException(status_code=422, detail="item_ids must be a comma-separated list of positive integers")
    return list(dict.fromkeys(item_ids))


def item_location_to_read(row: InventoryItemLocation) -> InventoryItemLocationRead:
    item = row.inventory_item
    recalculate_item_location(row, item)
    return InventoryItemLocationRead(
        id=row.id,
        item_id=row.inventory_item_id,
        sku=item.sku if item else None,
        barcode=item.barcode if item else None,
        description=item.description if item else None,
        brand=item.brand if item else None,
        category=item.category if item else None,
        unit_cost=float(item.unit_cost) if item and item.unit_cost is not None else None,
        item_active=item.active if item else None,
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


def transfer_to_read(transfer: InventoryTransfer) -> InventoryTransferRead:
    total_quantity = sum((line.quantity or 0 for line in transfer.lines), 0)
    return InventoryTransferRead(
        id=transfer.id,
        transfer_number=transfer.transfer_number,
        status=transfer.status,
        from_warehouse=transfer.from_warehouse,
        from_inventory_location=transfer.from_inventory_location,
        to_warehouse=transfer.to_warehouse,
        to_inventory_location=transfer.to_inventory_location,
        total_lines=len(transfer.lines),
        total_quantity=float(total_quantity),
        notes=transfer.notes,
        created_by=transfer.created_by,
        created_at=transfer.created_at,
        committed_at=transfer.committed_at,
    )


def transfer_line_to_read(line: InventoryTransferLine) -> InventoryTransferLineRead:
    return InventoryTransferLineRead(
        id=line.id,
        item_id=line.inventory_item_id,
        sku=line.sku,
        barcode=line.barcode,
        description=line.description,
        quantity=float(line.quantity or 0),
        from_inventory_item_location_id=line.from_inventory_item_location_id,
        to_inventory_item_location_id=line.to_inventory_item_location_id,
        from_warehouse=line.from_warehouse,
        from_inventory_location=line.from_inventory_location,
        to_warehouse=line.to_warehouse,
        to_inventory_location=line.to_inventory_location,
        notes=line.notes,
    )


def transfer_to_detail(transfer: InventoryTransfer) -> InventoryTransferDetail:
    base = transfer_to_read(transfer).model_dump()
    base["lines"] = [transfer_line_to_read(line) for line in transfer.lines]
    return InventoryTransferDetail.model_validate(base)


def adjustment_to_read(adjustment: StockAdjustment) -> StockAdjustmentRead:
    total_quantity = sum((line.quantity_change or 0 for line in adjustment.lines), 0)
    return StockAdjustmentRead(
        id=adjustment.id,
        adjustment_number=adjustment.adjustment_number,
        status=adjustment.status,
        adjustment_type=adjustment.adjustment_type,
        reason=adjustment.reason,
        total_lines=len(adjustment.lines),
        total_quantity_change=float(total_quantity),
        notes=adjustment.notes,
        created_by=adjustment.created_by,
        created_at=adjustment.created_at,
        committed_at=adjustment.committed_at,
    )


def adjustment_line_to_read(line: StockAdjustmentLine) -> StockAdjustmentLineRead:
    return StockAdjustmentLineRead(
        id=line.id,
        item_id=line.inventory_item_id,
        inventory_item_location_id=line.inventory_item_location_id,
        sku=line.sku,
        barcode=line.barcode,
        description=line.description,
        warehouse=line.warehouse,
        inventory_location=line.inventory_location,
        old_quantity=float(line.old_quantity or 0),
        new_quantity=float(line.new_quantity) if line.new_quantity is not None else None,
        quantity_change=float(line.quantity_change or 0),
        unit_cost=float(line.unit_cost) if line.unit_cost is not None else None,
        notes=line.notes,
    )


def adjustment_to_detail(adjustment: StockAdjustment) -> StockAdjustmentDetail:
    base = adjustment_to_read(adjustment).model_dump()
    base["lines"] = [adjustment_line_to_read(line) for line in adjustment.lines]
    return StockAdjustmentDetail.model_validate(base)
