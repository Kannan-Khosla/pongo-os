from datetime import datetime

from pydantic import BaseModel, Field


class FulfillmentLineRequest(BaseModel):
    order_line_id: int
    quantity_to_fulfill: float
    unit_cost: float | None = None


class FulfillmentRequest(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    lines: list[FulfillmentLineRequest] = Field(default_factory=list)
    fulfillment_strategy: str = "picked_first"
    allow_partial: bool = False
    created_by: str | None = "system"
    notes: str | None = None


class FulfillmentPreviewLine(BaseModel):
    order_id: int
    order_line_id: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_picked: float
    quantity_previously_fulfilled: float
    remaining_to_fulfill: float
    recommended_fulfill_quantity: float
    fulfillment_status: str
    in_stock: float
    allocated: float
    sellable: float
    warehouse: str | None = None
    inventory_location: str | None = None
    warnings: list[str] = []
    errors: list[str] = []


class FulfillmentPreviewOrder(BaseModel):
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    line_count: int
    fulfillable_lines: int
    partial_lines: int
    skipped_lines: int
    conflict_lines: int
    recommended_status: str
    warnings: list[str] = []
    errors: list[str] = []
    lines: list[FulfillmentPreviewLine] = []


class FulfillmentPreviewResponse(BaseModel):
    total_orders: int
    total_lines: int
    fulfillable_lines: int
    partial_lines: int
    skipped_lines: int
    conflict_lines: int
    total_quantity_to_fulfill: float
    warnings: list[str] = []
    errors: list[str] = []
    preview_orders: list[FulfillmentPreviewOrder] = []


class FulfillmentCommitResponse(BaseModel):
    fulfillment_id: int | None = None
    fulfillment_number: str | None = None
    status: str
    total_orders: int
    total_lines: int
    fulfilled_lines: int
    partial_lines: int
    skipped_lines: int
    total_quantity_fulfilled: float
    created_stock_movements: int
    created_audit_events: int
    warnings: list[str] = []
    errors: list[str] = []


class FulfillmentLineRead(BaseModel):
    id: int
    order_id: int
    order_line_id: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_picked: float
    quantity_previously_fulfilled: float
    quantity_to_fulfill: float
    quantity_fulfilled_after: float
    remaining_to_fulfill: float
    in_stock_before: float
    allocated_before: float
    sellable_before: float
    in_stock_after: float
    allocated_after: float
    sellable_after: float
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class FulfillmentRead(BaseModel):
    id: int
    fulfillment_number: str
    status: str
    fulfillment_type: str
    order_id: int | None = None
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    total_lines: int
    total_quantity_fulfilled: float
    created_by: str | None = None
    created_at: datetime
    posted_at: datetime | None = None


class FulfillmentDetail(FulfillmentRead):
    notes: str | None = None
    lines: list[FulfillmentLineRead]
    stock_movement_ids: list[int] = []
    audit_event_ids: list[int] = []


class FulfillmentListResponse(BaseModel):
    fulfillments: list[FulfillmentRead]
    total: int
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False
