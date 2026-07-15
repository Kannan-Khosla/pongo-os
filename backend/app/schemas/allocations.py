from datetime import datetime

from pydantic import BaseModel, Field


class AllocationLineRequest(BaseModel):
    order_line_id: int
    quantity_to_allocate: float


class AllocationRequest(BaseModel):
    order_ids: list[int] = Field(default_factory=list)
    lines: list[AllocationLineRequest] = Field(default_factory=list)
    allocation_strategy: str = "available_first"
    allow_partial: bool = False
    created_by: str | None = "system"
    notes: str | None = None


class AllocationPreviewLine(BaseModel):
    order_id: int
    order_line_id: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    quantity_ordered: float
    quantity_previously_allocated: float
    remaining_to_allocate: float
    in_stock: float
    allocated: float
    sellable: float
    recommended_allocate_quantity: float
    shortage_quantity: float
    allocation_status: str
    warnings: list[str] = []
    errors: list[str] = []


class AllocationPreviewOrder(BaseModel):
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    line_count: int
    allocatable_lines: int
    partial_lines: int
    skipped_lines: int
    conflict_lines: int
    recommended_status: str
    warnings: list[str] = []
    errors: list[str] = []
    lines: list[AllocationPreviewLine] = []


class AllocationPreviewResponse(BaseModel):
    total_orders: int
    total_lines: int
    allocatable_lines: int
    partial_lines: int
    skipped_lines: int
    conflict_lines: int
    total_quantity_to_allocate: float
    total_shortage_quantity: float
    warnings: list[str] = []
    errors: list[str] = []
    preview_orders: list[AllocationPreviewOrder] = []


class AllocationCommitResponse(BaseModel):
    allocation_id: int | None = None
    allocation_number: str | None = None
    status: str
    total_orders: int
    total_lines: int
    allocated_lines: int
    partial_lines: int
    skipped_lines: int
    total_quantity_allocated: float
    total_shortage_quantity: float
    created_audit_events: int
    warnings: list[str] = []
    errors: list[str] = []


class AllocationLineRead(BaseModel):
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
    quantity_previously_allocated: float
    quantity_to_allocate: float
    quantity_allocated_after: float
    in_stock_before: float
    allocated_before: float
    sellable_before: float
    allocated_after: float
    sellable_after: float
    shortage_quantity: float
    status: str
    auto_allocated: bool = False
    allocation_source: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class AllocationRead(BaseModel):
    id: int
    allocation_number: str
    status: str
    allocation_type: str
    order_id: int | None = None
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    total_lines: int
    total_quantity_allocated: float
    created_by: str | None = None
    auto_allocated: bool = False
    allocation_source: str | None = None
    created_at: datetime
    posted_at: datetime | None = None


class AllocationDetail(AllocationRead):
    notes: str | None = None
    lines: list[AllocationLineRead]
    audit_event_ids: list[int] = []


class AllocationListResponse(BaseModel):
    allocations: list[AllocationRead]
    total: int


class AllocationExceptionLineRead(BaseModel):
    order_id: int
    order_line_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    ordered_at: datetime | None = None
    customer_name: str | None = None
    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_unallocated: float
    quantity_picked: float
    quantity_available: float
    allocation_status: str
    exception_reason: str


class AllocationExceptionListResponse(BaseModel):
    lines: list[AllocationExceptionLineRead] = []
    total_orders: int
    total_lines: int
    total_quantity_unallocated: float
    lines_with_available_stock: int
    lines_out_of_stock: int


class AutoAllocationQueueResponse(BaseModel):
    status: str
    attempted_orders: int
    allocated_orders: int
    partially_allocated_orders: int
    exception_orders: int
    total_quantity_allocated: float
    allocation_ids: list[int] = []
    errors: list[str] = []
