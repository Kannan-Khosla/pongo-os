from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.inventory import StockMovement
from app.schemas.stock_movements import StockMovementListResponse, StockMovementRead

router = APIRouter(prefix="/stock-movements", tags=["stock-movements"])


@router.get("", response_model=StockMovementListResponse)
def list_stock_movements(
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
    statement = select(StockMovement).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
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
    movements = list(db.scalars(statement).all())
    return StockMovementListResponse(movements=[movement_to_read(movement) for movement in movements], total=len(movements))


def movement_to_read(movement: StockMovement) -> StockMovementRead:
    return StockMovementRead(
        id=movement.id,
        item_id=movement.inventory_item_id,
        sku=movement.sku,
        barcode=movement.barcode,
        movement_type=movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type),
        quantity_delta=float(movement.quantity_change),
        previous_in_stock=float(movement.old_stock) if movement.old_stock is not None else None,
        new_in_stock=float(movement.new_stock) if movement.new_stock is not None else None,
        warehouse=movement.warehouse,
        inventory_location=movement.inventory_location_name,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        reference_number=movement.reference_number,
        unit_cost=float(movement.unit_cost) if movement.unit_cost is not None else None,
        notes=movement.notes,
        created_by=movement.created_by,
        created_at=movement.created_at,
    )
