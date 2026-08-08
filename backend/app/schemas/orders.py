from datetime import datetime

from pydantic import BaseModel, Field


class OpenOrderLineRead(BaseModel):
    id: int
    woo_line_item_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_picked: float
    quantity_fulfilled: float
    quantity_stock_reduced: float = 0
    remaining_to_allocate: float
    remaining_to_pick: float
    remaining_to_fulfill: float
    stock_reduced_at: datetime | None = None
    allocation_status: str | None = None
    pick_status: str | None = None
    allocation_exception_reason: str | None = None
    picking_status: str | None = None
    fulfillment_status: str | None = None
    unit_price: float | None = None
    line_tax: float | None = None
    line_total: float | None = None
    matched_status: str | None = None
    availability_status: str | None = None
    local_sellable: float
    sellable_snapshot: float
    shortage_quantity: float
    sync_status: str | None = None
    sync_error: str | None = None


class OpenOrderRead(BaseModel):
    id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    woo_status: str | None = None
    local_status: str | None = None
    allocation_status: str | None = None
    pick_status: str | None = None
    completion_status: str | None = None
    auto_allocation_status: str | None = None
    completed_without_picking: bool = False
    completed_at: datetime | None = None
    closed_at: datetime | None = None
    picked_at: datetime | None = None
    allocation_exception_reason: str | None = None
    currency: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    order_source: str = "WooCommerce"
    shipping_city: str | None = None
    shipping_state: str | None = None
    shipping_zip: str | None = None
    shipping_via: str | None = None
    company: str | None = None
    ship_from: str = "Main Warehouse"
    skus: list[str] = []
    item_names: list[str] = []
    total_quantity_ordered: float = 0
    total_quantity_allocated: float = 0
    total_quantity_picked: float = 0
    total_quantity_fulfilled: float = 0
    total: float | None = None
    date_created: datetime | None = None
    date_modified: datetime | None = None
    line_count: int
    availability_status: str | None = None
    matched_status: str | None = None
    can_pick: bool = False
    can_complete: bool = False
    shows_in_open_orders: bool = True
    shows_in_allocate: bool = False
    shows_in_pick_orders: bool = False
    shows_in_completed_orders: bool = False
    last_synced_at: datetime | None = None


class OpenOrderDetail(OpenOrderRead):
    customer_id: int | None = None
    billing_summary: dict | None = None
    shipping_summary: dict | None = None
    payment_method: str | None = None
    payment_method_title: str | None = None
    subtotal: float | None = None
    discount_total: float | None = None
    shipping_total: float | None = None
    tax_total: float | None = None
    workflow_notes: str | None = None
    lines: list[OpenOrderLineRead]


class OpenOrderListResponse(BaseModel):
    orders: list[OpenOrderRead]
    total: int
    available_count: int
    partial_count: int
    unavailable_count: int
    unknown_count: int
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class BulkOrderActionRequest(BaseModel):
    order_ids: list[int] = Field(min_length=1)
    created_by: str | None = "system"
    reason: str | None = None


class BulkUnpickRequest(BulkOrderActionRequest):
    idempotency_key: str = Field(min_length=1, max_length=120)


class BulkOrderActionResult(BaseModel):
    order_id: int
    status: str
    message: str
    woo_sync_status: str | None = None
    woo_writeback_queue_id: int | None = None
    woo_sync_error: str | None = None


class BulkOrderActionResponse(BaseModel):
    status: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    total_quantity_restored: float = 0
    created_stock_movements: int = 0
    created_audit_events: int = 0
    results: list[BulkOrderActionResult] = []
    errors: list[str] = []


class CompletedOrderRead(BaseModel):
    id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    woo_status: str | None = None
    local_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    total: float | None = None
    date_created: datetime | None = None
    date_modified: datetime | None = None
    line_count: int
    fulfilled_line_count: int
    total_quantity_ordered: float
    total_quantity_allocated: float
    total_quantity_picked: float
    total_quantity_fulfilled: float
    total_quantity_stock_reduced: float = 0
    total_remaining_to_fulfill: float
    total_fulfilled_value: float
    completed_without_picking: bool = False
    completion_status: str | None = None
    pick_status: str | None = None
    completed_at: datetime | None = None
    closed_at: datetime | None = None


class CompletedOrderListResponse(BaseModel):
    orders: list[CompletedOrderRead]
    total: int
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class OrderWorkflowPreviewResponse(BaseModel):
    order_id: int
    status: str
    message: str | None = None
    warnings: list[str] = []
    errors: list[str] = []
    workflow: dict | None = None


class OrderCompletionRequest(BaseModel):
    completion_mode: str
    reason: str | None = None
    queue_woo_status_update: bool = True


class OrderCompletionResponse(BaseModel):
    status: str
    order_id: int
    released_quantity: float = 0
    message: str
    queue_woo_status_update: bool = True
    woo_sync_status: str | None = None
    woo_writeback_queue_id: int | None = None
    woo_sync_error: str | None = None
