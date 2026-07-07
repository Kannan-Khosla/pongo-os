from datetime import datetime

from pydantic import BaseModel, Field


class WooCommerceStatusResponse(BaseModel):
    configured: bool
    base_url_present: bool
    consumer_key_present: bool
    consumer_secret_present: bool
    message: str


class WooCommerceSyncRequest(BaseModel):
    include_statuses: list[str] = Field(default_factory=lambda: ["publish"])
    limit: int | None = 500
    created_by: str | None = "system"


class WooCommerceOrderSyncRequest(BaseModel):
    include_statuses: list[str] = Field(default_factory=lambda: ["processing", "on-hold"])
    limit: int | None = 500
    after: str | None = None
    before: str | None = None
    modified_after: str | None = None
    modified_before: str | None = None
    created_by: str | None = "system"


class WooCommerceProductPreviewRow(BaseModel):
    remote_type: str
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    price: float | None = None
    regular_price: float | None = None
    stock_status: str | None = None
    stock_quantity_snapshot: float | None = None
    local_item_id: int | None = None
    action: str
    status: str
    warnings: list[str] = []
    errors: list[str] = []


class WooCommerceProductPreviewResponse(BaseModel):
    configured: bool
    total_remote_records: int
    create_count: int
    update_count: int
    matched_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    warnings: list[str] = []
    errors: list[str] = []
    preview_rows: list[WooCommerceProductPreviewRow] = []


class WooCommerceProductCommitResponse(BaseModel):
    sync_run_id: int | None = None
    status: str
    total_remote_records: int
    created_count: int
    updated_count: int
    matched_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    warnings: list[str] = []
    errors: list[str] = []


class WooCommerceOrderPreviewLine(BaseModel):
    woo_line_item_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    quantity_ordered: float
    matched_status: str
    availability_status: str
    sellable_snapshot: float
    shortage_quantity: float
    warnings: list[str] = []
    errors: list[str] = []


class WooCommerceOrderPreviewOrder(BaseModel):
    woo_order_id: int
    woo_order_number: str | None = None
    woo_status: str | None = None
    local_order_id: int | None = None
    action: str
    local_status: str
    customer_name: str | None = None
    customer_email: str | None = None
    currency: str | None = None
    total: float | None = None
    date_created: datetime | None = None
    date_modified: datetime | None = None
    matched_status: str
    availability_status: str
    line_count: int
    warnings: list[str] = []
    errors: list[str] = []
    lines: list[WooCommerceOrderPreviewLine] = []


class WooCommerceOrderPreviewResponse(BaseModel):
    configured: bool
    total_remote_records: int
    create_count: int
    update_count: int
    matched_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    available_count: int
    partial_count: int
    unavailable_count: int
    unknown_count: int
    warnings: list[str] = []
    errors: list[str] = []
    preview_orders: list[WooCommerceOrderPreviewOrder] = []


class WooCommerceOrderCommitResponse(BaseModel):
    sync_run_id: int | None = None
    status: str
    total_remote_records: int
    created_count: int
    updated_count: int
    matched_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    available_count: int
    partial_count: int
    unavailable_count: int
    unknown_count: int
    warnings: list[str] = []
    errors: list[str] = []


class WooCommerceSyncErrorRead(BaseModel):
    id: int
    remote_order_id: int | None = None
    remote_line_item_id: int | None = None
    remote_product_id: int | None = None
    remote_variation_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    error_message: str | None = None
    raw_payload: dict | None = None
    created_at: datetime


class WooCommerceSyncRunRead(BaseModel):
    id: int
    sync_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    created_by: str | None = None
    total_remote_records: int
    created_count: int
    updated_count: int
    matched_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    notes: str | None = None


class WooCommerceSyncRunDetail(WooCommerceSyncRunRead):
    errors: list[WooCommerceSyncErrorRead] = []


class WooCommerceSyncRunListResponse(BaseModel):
    sync_runs: list[WooCommerceSyncRunRead]
    total: int
