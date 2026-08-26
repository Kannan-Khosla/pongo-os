from datetime import datetime

from pydantic import BaseModel


class StockMovementRead(BaseModel):
    id: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    movement_type: str
    quantity_delta: float
    previous_in_stock: float | None = None
    new_in_stock: float | None = None
    previous_location_in_stock: float | None = None
    new_location_in_stock: float | None = None
    previous_item_in_stock: float | None = None
    new_item_in_stock: float | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    reference_number: str | None = None
    description: str | None = None
    reason: str | None = None
    unit_cost: float | None = None
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime


class StockMovementListResponse(BaseModel):
    movements: list[StockMovementRead]
    total: int
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False
