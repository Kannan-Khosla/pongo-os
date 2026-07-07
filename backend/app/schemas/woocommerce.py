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


class WooCommerceSyncErrorRead(BaseModel):
    id: int
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
