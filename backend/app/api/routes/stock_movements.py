from datetime import datetime
import csv
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.inventory import InventoryItem, StockMovement
from app.schemas.stock_movements import StockMovementListResponse, StockMovementRead

router = APIRouter(prefix="/stock-movements", tags=["stock-movements"])


@router.get("", response_model=StockMovementListResponse)
def list_stock_movements(
    search: str | None = None,
    item_id: int | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    movement_type: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> StockMovementListResponse:
    statement = build_stock_movements_statement(search, item_id, sku, barcode, warehouse, inventory_location, movement_type, reference_type, reference_id, date_from, date_to)
    movements = list(db.scalars(statement).all())
    return StockMovementListResponse(movements=[movement_to_read(movement) for movement in movements], total=len(movements))


@router.get("/export")
def export_stock_movements(
    search: str | None = None,
    item_id: int | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    movement_type: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> Response:
    movements = list(db.scalars(build_stock_movements_statement(search, item_id, sku, barcode, warehouse, inventory_location, movement_type, reference_type, reference_id, date_from, date_to)).all())
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["Date", "Movement Type", "SKU", "Barcode", "Description", "Warehouse", "Location", "Quantity Change", "Old Stock", "New Stock", "Reference", "Reason", "Notes"])
    writer.writeheader()
    for movement in movements:
        item = movement.inventory_item
        writer.writerow(
            {
                "Date": movement.created_at.isoformat() if movement.created_at else "",
                "Movement Type": movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type),
                "SKU": movement.sku or "",
                "Barcode": movement.barcode or "",
                "Description": item.description if item else "",
                "Warehouse": movement.warehouse or "",
                "Location": movement.inventory_location_name or "",
                "Quantity Change": float(movement.quantity_change or 0),
                "Old Stock": float(movement.old_stock) if movement.old_stock is not None else "",
                "New Stock": float(movement.new_stock) if movement.new_stock is not None else "",
                "Reference": movement.reference_number or movement.reference_type or "",
                "Reason": movement.reason or "",
                "Notes": movement.notes or "",
            }
        )
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="pongo-stock-movements-export.csv"'})


def build_stock_movements_statement(
    search: str | None,
    item_id: int | None,
    sku: str | None,
    barcode: str | None,
    warehouse: str | None,
    inventory_location: str | None,
    movement_type: str | None,
    reference_type: str | None,
    reference_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
):
    statement = select(StockMovement).join(InventoryItem).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                StockMovement.sku.ilike(pattern),
                StockMovement.barcode.ilike(pattern),
                StockMovement.reference_number.ilike(pattern),
                StockMovement.notes.ilike(pattern),
                StockMovement.reason.ilike(pattern),
                InventoryItem.description.ilike(pattern),
                InventoryItem.brand.ilike(pattern),
                InventoryItem.category.ilike(pattern),
            )
        )
    if item_id is not None:
        statement = statement.where(StockMovement.inventory_item_id == item_id)
    if sku:
        statement = statement.where(StockMovement.sku == sku)
    if barcode:
        statement = statement.where(StockMovement.barcode == barcode)
    if warehouse:
        statement = statement.where(StockMovement.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(StockMovement.inventory_location_name == inventory_location)
    if movement_type:
        statement = statement.where(StockMovement.movement_type == movement_type)
    if reference_type:
        statement = statement.where(StockMovement.reference_type == reference_type)
    if reference_id is not None:
        statement = statement.where(StockMovement.reference_id == reference_id)
    if date_from:
        statement = statement.where(StockMovement.created_at >= date_from)
    if date_to:
        statement = statement.where(StockMovement.created_at <= date_to)
    return statement


def movement_to_read(movement: StockMovement) -> StockMovementRead:
    item = movement.inventory_item
    return StockMovementRead(
        id=movement.id,
        item_id=movement.inventory_item_id,
        inventory_item_location_id=movement.inventory_item_location_id,
        sku=movement.sku,
        barcode=movement.barcode,
        movement_type=movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type),
        quantity_delta=float(movement.quantity_change),
        previous_in_stock=float(movement.old_stock) if movement.old_stock is not None else None,
        new_in_stock=float(movement.new_stock) if movement.new_stock is not None else None,
        previous_location_in_stock=float(movement.old_location_stock) if movement.old_location_stock is not None else None,
        new_location_in_stock=float(movement.new_location_stock) if movement.new_location_stock is not None else None,
        previous_item_in_stock=float(movement.old_item_stock) if movement.old_item_stock is not None else None,
        new_item_in_stock=float(movement.new_item_stock) if movement.new_item_stock is not None else None,
        warehouse=movement.warehouse,
        inventory_location=movement.inventory_location_name,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        reference_number=movement.reference_number,
        description=item.description if item else None,
        reason=movement.reason,
        unit_cost=float(movement.unit_cost) if movement.unit_cost is not None else None,
        notes=movement.notes,
        created_by=movement.created_by,
        created_at=movement.created_at,
    )
