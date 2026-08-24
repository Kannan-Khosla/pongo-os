from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OrderNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=1, max_length=120)

    @field_validator("note", "idempotency_key")
    @classmethod
    def strip_nonblank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be blank.")
        return cleaned


class OrderNoteRead(BaseModel):
    id: int
    order_id: int
    note: str
    note_type: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class OrderNoteListResponse(BaseModel):
    notes: list[OrderNoteRead] = Field(default_factory=list)
    total: int


class OrderTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Tag name must not be blank.")
        return cleaned

    @field_validator("color")
    @classmethod
    def uppercase_color(cls, value: str) -> str:
        return value.upper()


class OrderTagRead(BaseModel):
    id: int
    name: str
    color: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class OrderTagListResponse(BaseModel):
    tags: list[OrderTagRead] = Field(default_factory=list)
    total: int


class OrderTagsUpdate(BaseModel):
    tag_ids: list[int] = Field(default_factory=list, max_length=20)
    highlight_tag_id: int | None = Field(default=None, gt=0)

    @field_validator("tag_ids")
    @classmethod
    def validate_tag_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Tag IDs must be positive integers.")
        if len(values) != len(set(values)):
            raise ValueError("Tag IDs must not contain duplicates.")
        return values

    @model_validator(mode="after")
    def validate_highlight(self):
        if self.highlight_tag_id is not None and self.highlight_tag_id not in self.tag_ids:
            raise ValueError("The highlighted tag must be included in tag_ids.")
        return self


class OrderTagsRead(BaseModel):
    tags: list[OrderTagRead] = Field(default_factory=list)
    highlight_tag_id: int | None = None
    highlight_color: str | None = None


class OpenOrderLineRead(BaseModel):
    id: int
    woo_line_item_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    item_id: int | None = None
    substituted_from_item_id: int | None = None
    substituted_from_sku: str | None = None
    substituted_from_name: str | None = None
    substitution_reason: str | None = None
    substituted_by: str | None = None
    substituted_at: datetime | None = None
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    effective_sku: str | None = None
    effective_barcode: str | None = None
    effective_name: str | None = None
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
    invoice_unit_price: float | None = None
    invoice_line_total: float | None = None
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
    tags: list[OrderTagRead] = Field(default_factory=list)
    highlight_tag_id: int | None = None
    highlight_color: str | None = None
    note_count: int = 0
    latest_note: OrderNoteRead | None = None


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
    invoice_subtotal: float | None = None
    invoice_total: float | None = None
    customer_note: str | None = None
    workflow_notes: str | None = None
    internal_notes: list[OrderNoteRead] = Field(default_factory=list)
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
    tags: list[OrderTagRead] = Field(default_factory=list)
    highlight_tag_id: int | None = None
    highlight_color: str | None = None
    note_count: int = 0
    latest_note: OrderNoteRead | None = None


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


class WooOrderStatusActionRequest(BaseModel):
    target_status: Literal["completed", "cancelled"]
    idempotency_key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=1000)
    completion_mode: Literal["complete", "complete_picked", "complete_without_picking"] = "complete"


class WooOrderStatusActionResponse(BaseModel):
    status: str
    target_status: str
    woo_order_id: int
    local_order_id: int
    local_status: str | None = None
    released_quantity: float = 0
    message: str
    woo_sync_status: str | None = None
    woo_writeback_queue_id: int | None = None
    woo_sync_error: str | None = None


class WooOrderReconcileRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)


class WooOrderReconcileResponse(BaseModel):
    status: Literal["reconciled"]
    woo_order_id: int
    local_order_id: int
    order: OpenOrderDetail


class OrderSubstitutionRequest(BaseModel):
    replacement_inventory_item_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class OrderSubstitutionResponse(BaseModel):
    status: str
    order_id: int
    order_line_id: int
    substituted_from_item_id: int
    replacement_inventory_item_id: int
    released_quantity: float = 0
    allocation_status: str | None = None
    pick_status: str | None = None
    message: str
    woo_stock_sync_status: str | None = None
    woo_stock_sync_error: str | None = None


class OrderLineAddRequest(BaseModel):
    inventory_item_id: int = Field(gt=0)
    quantity: float = Field(gt=0, le=100000)
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class OrderLineRemoveRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class OrderLineEditResponse(BaseModel):
    status: Literal["added", "removed"]
    order_id: int
    order_line_id: int
    inventory_item_id: int | None = None
    released_quantity: float = 0
    allocation_status: str | None = None
    pick_status: str | None = None
    message: str
    woo_stock_sync_status: str | None = None
    woo_stock_sync_error: str | None = None


class CompletedOrderPickRecoveryRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=120)


class CompletedOrderPickRecoveryResponse(BaseModel):
    status: str
    order_id: int
    allocation_status: str | None = None
    pick_status: str | None = None
    message: str


class CompletedOrderRecordPickedRequest(BaseModel):
    order_ids: list[int] = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=1000)
    idempotency_key: str = Field(min_length=1, max_length=120)

    @field_validator("order_ids")
    @classmethod
    def validate_order_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Order IDs must be positive integers.")
        return list(dict.fromkeys(values))

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        return cleaned or None

    @field_validator("idempotency_key")
    @classmethod
    def strip_idempotency_key(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Idempotency key must not be blank.")
        return cleaned


class CompletedOrderRecordPickedResult(BaseModel):
    order_id: int
    status: str
    message: str
    pick_id: int | None = None
    pick_number: str | None = None
    total_quantity_picked: float = 0
    created_stock_movements: int = 0
    created_audit_events: int = 0
    woo_stock_sync_status: str | None = None
    woo_stock_sync_error: str | None = None
    woo_stock_sync_job_id: int | None = None
    replayed: bool = False


class CompletedOrderRecordPickedResponse(BaseModel):
    status: str
    requested_count: int
    succeeded_count: int
    failed_count: int
    total_quantity_picked: float = 0
    created_stock_movements: int = 0
    created_audit_events: int = 0
    results: list[CompletedOrderRecordPickedResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
