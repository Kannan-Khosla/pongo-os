from datetime import datetime

from pydantic import BaseModel, Field


class InventoryLocationSummaryRow(BaseModel):
    warehouse: str
    inventory_location: str
    item_count: int
    total_in_stock: float
    total_allocated: float
    total_sellable: float
    total_on_order: float
    total_inventory_value: float
    under_par_count: int


class InventoryLocationSummaryResponse(BaseModel):
    groups: list[InventoryLocationSummaryRow]
    total_items: int
    total_in_stock: float
    total_allocated: float
    total_sellable: float
    total_on_order: float
    total_inventory_value: float
    under_par_count: int


class InventoryItemLocationRead(BaseModel):
    id: int
    item_id: int
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    location_code: str | None = None
    location_name: str | None = None
    is_default_location: bool
    in_stock: float
    allocated: float
    sellable: float
    on_order: float
    par_level: float | None = None
    under_par: bool
    active: bool
    updated_at: datetime


class InventoryItemLocationListResponse(BaseModel):
    locations: list[InventoryItemLocationRead]
    total: int


class InventoryItemLocationCreate(BaseModel):
    warehouse: str
    inventory_location: str
    location_id: int | None = None
    is_default_location: bool = False
    par_level: float | None = None
    active: bool = True


class InventoryItemLocationUpdate(BaseModel):
    is_default_location: bool | None = None
    par_level: float | None = None
    active: bool | None = None
    location_code: str | None = None
    location_name: str | None = None


class InventoryLocationInventoryListResponse(BaseModel):
    rows: list[InventoryItemLocationRead]
    total: int


class InventoryTransferLineInput(BaseModel):
    item_id: int
    from_inventory_item_location_id: int
    to_warehouse: str
    to_inventory_location: str
    quantity: float = Field(gt=0)
    notes: str | None = None


class InventoryTransferRequest(BaseModel):
    created_by: str | None = "system"
    notes: str | None = None
    lines: list[InventoryTransferLineInput] = Field(default_factory=list)


class InventoryTransferLineRead(BaseModel):
    id: int
    item_id: int
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    quantity: float
    from_inventory_item_location_id: int
    to_inventory_item_location_id: int | None = None
    from_warehouse: str | None = None
    from_inventory_location: str | None = None
    to_warehouse: str | None = None
    to_inventory_location: str | None = None
    notes: str | None = None


class InventoryTransferRead(BaseModel):
    id: int
    transfer_number: str
    status: str
    from_warehouse: str | None = None
    from_inventory_location: str | None = None
    to_warehouse: str | None = None
    to_inventory_location: str | None = None
    total_lines: int
    total_quantity: float
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    committed_at: datetime | None = None


class InventoryTransferDetail(InventoryTransferRead):
    lines: list[InventoryTransferLineRead] = []


class InventoryTransferListResponse(BaseModel):
    transfers: list[InventoryTransferRead]
    total: int


class StockAdjustmentLineInput(BaseModel):
    item_id: int
    inventory_item_location_id: int
    quantity_change: float
    notes: str | None = None


class StockAdjustmentRequest(BaseModel):
    adjustment_type: str
    reason: str
    notes: str | None = None
    created_by: str | None = "system"
    lines: list[StockAdjustmentLineInput] = Field(default_factory=list)


class StockAdjustmentLineRead(BaseModel):
    id: int
    item_id: int
    inventory_item_location_id: int
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    old_quantity: float
    new_quantity: float | None = None
    quantity_change: float
    unit_cost: float | None = None
    notes: str | None = None


class StockAdjustmentRead(BaseModel):
    id: int
    adjustment_number: str
    status: str
    adjustment_type: str
    reason: str
    total_lines: int
    total_quantity_change: float
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    committed_at: datetime | None = None


class StockAdjustmentDetail(StockAdjustmentRead):
    lines: list[StockAdjustmentLineRead] = []


class StockAdjustmentListResponse(BaseModel):
    adjustments: list[StockAdjustmentRead]
    total: int
