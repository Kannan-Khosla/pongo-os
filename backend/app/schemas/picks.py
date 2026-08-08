from datetime import datetime

from pydantic import BaseModel, Field


class PickLineRequest(BaseModel):
    order_line_id: int
    quantity_to_pick: float
    idempotency_key: str | None = None


class PickRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=120)
    order_ids: list[int] = Field(default_factory=list)
    lines: list[PickLineRequest] = Field(default_factory=list)
    pick_strategy: str = "allocated_first"
    allow_partial: bool = False
    created_by: str | None = "system"
    notes: str | None = None


class PickCommitRequest(PickRequest):
    idempotency_key: str = Field(min_length=1, max_length=120)


class PickPreviewLine(BaseModel):
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
    quantity_previously_picked: float
    remaining_to_pick: float
    recommended_pick_quantity: float
    quantity_picked_after: float
    pick_status: str
    warnings: list[str] = []
    errors: list[str] = []


class PickPreviewOrder(BaseModel):
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    line_count: int
    pickable_lines: int
    partial_lines: int
    skipped_lines: int
    conflict_lines: int
    recommended_status: str
    warnings: list[str] = []
    errors: list[str] = []
    lines: list[PickPreviewLine] = []


class PickPreviewResponse(BaseModel):
    total_orders: int
    total_lines: int
    pickable_lines: int
    partial_lines: int
    skipped_lines: int
    conflict_lines: int
    total_quantity_to_pick: float
    warnings: list[str] = []
    errors: list[str] = []
    preview_orders: list[PickPreviewOrder] = []


class PickCommitResponse(BaseModel):
    pick_id: int | None = None
    pick_number: str | None = None
    status: str
    total_orders: int
    total_lines: int
    picked_lines: int
    partial_lines: int
    skipped_lines: int
    total_quantity_picked: float
    created_stock_movements: int = 0
    created_audit_events: int
    warnings: list[str] = []
    errors: list[str] = []


class PickLineRead(BaseModel):
    id: int
    order_id: int
    order_line_id: int
    item_id: int
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_previously_picked: float
    quantity_to_pick: float
    quantity_picked_after: float
    remaining_to_pick: float
    quantity_stock_reduced: float = 0
    stock_movement_id: int | None = None
    stock_reduced_at: datetime | None = None
    idempotency_key: str | None = None
    status: str
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class PickRead(BaseModel):
    id: int
    pick_number: str
    status: str
    pick_type: str
    order_id: int | None = None
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    total_lines: int
    total_quantity_picked: float
    created_by: str | None = None
    created_at: datetime
    posted_at: datetime | None = None


class PickDetail(PickRead):
    notes: str | None = None
    lines: list[PickLineRead]
    audit_event_ids: list[int] = []


class PickListResponse(BaseModel):
    picks: list[PickRead]
    total: int
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class PickScannerLine(BaseModel):
    order_line_id: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    ordered_quantity: float
    allocated_quantity: float
    picked_quantity: float
    remaining_to_pick: float
    warehouse: str | None = None
    inventory_location: str | None = None
    status: str
    warnings: list[str] = []


class PickScannerOrder(BaseModel):
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    local_status: str | None = None
    line_count: int
    complete_lines: int
    total_allocated_quantity: float
    total_picked_quantity: float
    lines: list[PickScannerLine] = []


class PickScanRequest(BaseModel):
    sku_or_barcode: str
    quantity: float = 1
    note: str | None = None
    created_by: str | None = "system"
    idempotency_key: str | None = None


class PickScanCommitRequest(PickScanRequest):
    idempotency_key: str = Field(min_length=1, max_length=120)


class PickScanResponse(BaseModel):
    status: str
    matched_line: PickScannerLine | None = None
    proposed_picked_quantity: float | None = None
    warnings: list[str] = []
    errors: list[str] = []
    commit: PickCommitResponse | None = None
