from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class WooCommerceOrderReconciliationStatus(BaseModel):
    enabled: bool = False
    running: bool = False
    healthy: bool = False
    degraded: bool = False
    stale: bool = False
    interval_seconds: int = 60
    stale_after_seconds: int = 300
    statuses: list[str] = Field(default_factory=list)
    last_status: str | None = None
    error_count: int = 0
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    message: str = ""


class WooCommerceStatusResponse(BaseModel):
    configured: bool
    base_url_present: bool
    consumer_key_present: bool
    consumer_secret_present: bool
    base_url: str | None = None
    base_url_host: str | None = None
    environment: str = "development"
    access_mode: str = "read_only"
    access_mode_updated_by: str | None = None
    access_mode_updated_at: datetime | None = None
    configuration_source: str = "backend_environment"
    configuration_updated_by: str | None = None
    configuration_updated_at: datetime | None = None
    read_enabled: bool = True
    read_only: bool = True
    writeback_enabled: bool = False
    dry_run: bool = True
    staging_live_test_mode: bool = False
    stock_write_allowed: bool = False
    production_stock_authority: str = "disabled"
    order_status_write_allowed: bool = False
    product_metadata_write_allowed: bool = False
    customer_write_allowed: bool = False
    coupon_write_allowed: bool = False
    refund_write_allowed: bool = False
    delete_allowed: bool = False
    allowed_host: str | None = None
    host_allowed: bool = False
    webhook_enabled: bool = False
    webhook_configured: bool = False
    webhook_secret_present: bool = False
    last_webhook_delivery: dict | None = None
    last_product_sync: dict | None = None
    last_order_sync: dict | None = None
    order_history_import: dict | None = None
    order_history_coverage: dict = Field(default_factory=dict)
    order_reconciliation: WooCommerceOrderReconciliationStatus = Field(default_factory=WooCommerceOrderReconciliationStatus)
    last_error: str | None = None
    message: str


class WooCommerceConfigurationRequest(BaseModel):
    base_url: str
    consumer_key: str | None = None
    consumer_secret: str | None = None
    allow_host_change: bool = False


class WooCommerceAccessModeRequest(BaseModel):
    access_mode: str


class WooCommerceAccessModeResponse(BaseModel):
    access_mode: str
    changed_by: str
    changed_at: datetime
    message: str


class WooCommerceConfigurationResponse(BaseModel):
    connected: bool
    base_url: str
    base_url_host: str
    consumer_key_present: bool
    consumer_secret_present: bool
    message: str


class WooCommerceSyncRequest(BaseModel):
    include_statuses: list[str] = Field(default_factory=lambda: ["publish"])
    limit: int | None = 500
    page: int | None = Field(default=None, ge=1)
    per_page: int = Field(default=50, ge=1, le=100)
    blocked_skus: list[str] = Field(default_factory=list)
    created_by: str | None = "system"


class WooCommerceOrderSyncRequest(BaseModel):
    include_statuses: list[str] = Field(default_factory=lambda: ["processing", "on-hold", "pending"])
    limit: int | None = 500
    after: str | None = None
    before: str | None = None
    modified_after: str | None = None
    modified_before: str | None = None
    created_by: str | None = "system"


class WooCommerceProductPreviewRow(BaseModel):
    remote_type: str
    product_name: str | None = None
    parent_product_name: str | None = None
    variation_attributes: list[dict] = []
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
    current_mapping: dict | None = None
    proposed_item: dict | None = None
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
    page: int | None = None
    next_page: int | None = None
    has_more: bool = False
    unmatched_local_count: int = 0
    unmatched_local_skus: list[str] = []
    simple_products_examined: int = 0
    variable_parents_examined: int = 0
    purchasable_variations_examined: int = 0
    new_simple_count: int = 0
    new_variation_count: int = 0
    unchanged_count: int = 0
    skipped_parent_count: int = 0
    missing_sku_count: int = 0
    duplicate_sku_conflict_count: int = 0
    duplicate_mapping_conflict_count: int = 0
    unmapped_count: int = 0
    invalid_count: int = 0


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
    page: int | None = None
    next_page: int | None = None
    has_more: bool = False
    unmatched_local_count: int = 0
    unmatched_local_skus: list[str] = []
    unchanged_count: int = 0


class WooCommerceNewProductImportResponse(BaseModel):
    sync_run_id: int
    status: str
    checked_since: datetime | None = None
    total_remote_records: int
    created_count: int
    linked_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    created_item_ids: list[int] = Field(default_factory=list)
    setup_item_ids: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    message: str


class WooCatalogSyncCreateRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)


class WooCatalogSyncRunRead(BaseModel):
    id: int
    status: str
    stage: str
    created_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    updated_at: datetime
    attempt_count: int
    next_retry_at: datetime | None = None
    total_remote_records: int
    processed_records: int
    created_count: int
    updated_count: int
    matched_count: int
    unchanged_count: int
    skipped_count: int
    conflict_count: int
    error_count: int
    progress_percent: float
    message: str
    can_resume: bool
    can_cancel: bool
    can_resolve: bool
    deduplicated: bool = False


class WooCatalogSyncCurrentResponse(BaseModel):
    run: WooCatalogSyncRunRead | None = None


class WooCatalogSyncRowRead(BaseModel):
    id: int
    sync_run_id: int
    remote_type: str
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    product_name: str | None = None
    status: str
    action: str
    local_item_id: int | None = None
    message: str | None = None
    resolution_action: str | None = None
    resolution_item_id: int | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WooCatalogSyncRowListResponse(BaseModel):
    rows: list[WooCatalogSyncRowRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    returned_count: int
    has_previous: bool
    has_next: bool


class WooCatalogSyncResolveRequest(BaseModel):
    action: Literal["link", "create", "skip"]
    item_id: int | None = Field(default=None, ge=1)


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
    auto_allocated_count: int = 0
    allocation_exception_count: int = 0
    unmatched_line_count: int = 0
    conflict_line_count: int = 0
    pick_ready_count: int = 0
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
    auto_allocated_count: int = 0
    allocation_exception_count: int = 0
    unmatched_line_count: int = 0
    conflict_line_count: int = 0
    pick_ready_count: int = 0
    warnings: list[str] = []
    errors: list[str] = []


class WooCommerceWebhookDeliveryResponse(BaseModel):
    status: str
    duplicate: bool = False
    delivery_id: str | None = None
    event_id: int | None = None
    woo_order_id: int | None = None
    local_order_id: int | None = None
    sync_run_id: int | None = None
    created_order: bool = False
    message: str


class WooCommerceWebhookEventRead(BaseModel):
    id: int
    topic: str
    event_type: str
    woo_order_id: int | None = None
    local_order_id: int | None = None
    woo_order_number: str | None = None
    woo_status: str | None = None
    local_status: str | None = None
    customer_name: str | None = None
    currency: str | None = None
    total: float | None = None
    created_order: bool
    received_at: datetime


class WooCommerceWebhookEventListResponse(BaseModel):
    events: list[WooCommerceWebhookEventRead]
    latest_event_id: int
    next_after_id: int
    has_more: bool = False


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
    progress: dict | None = None


class WooCommerceSyncRunDetail(WooCommerceSyncRunRead):
    errors: list[WooCommerceSyncErrorRead] = []
    errors_total: int = 0
    errors_page: int = 1
    errors_page_size: int = 50
    errors_total_pages: int = 0
    errors_returned_count: int = 0
    errors_has_previous: bool = False
    errors_has_next: bool = False


class WooCommerceSyncRunListResponse(BaseModel):
    sync_runs: list[WooCommerceSyncRunRead]
    total: int
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class WooWritebackStockPreviewRequest(BaseModel):
    item_id: int | None = None
    sku: str | None = None
    proposed_stock_quantity: float | None = None
    proposed_stock_status: str | None = None
    fetch_live: bool = False


class WooWritebackOrderStatusPreviewRequest(BaseModel):
    order_id: int | None = None
    woo_order_id: int | None = None
    proposed_status: str
    fetch_live: bool = False


class WooWritebackPreviewResponse(BaseModel):
    operation_type: str
    entity_type: str
    entity_id: int
    woo_entity_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    woo_order_id: int | None = None
    payload_json: dict
    preview_json: dict
    environment: str
    dry_run: bool
    warnings: list[str] = []


class WooWritebackQueueCreateRequest(BaseModel):
    operation_type: str
    entity_type: str
    entity_id: int
    woo_entity_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    woo_order_id: int | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)
    payload_json: dict
    preview_json: dict
    requested_by: str | None = None


class WooWritebackQueueRead(BaseModel):
    id: int
    operation_type: str
    entity_type: str
    entity_id: int
    woo_entity_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    woo_order_id: int | None = None
    idempotency_key: str | None = None
    payload_json: dict
    status: str
    environment: str
    dry_run: bool
    allowed_host: str | None = None
    preview_json: dict
    response_json: dict | None = None
    error_message: str | None = None
    requested_by: str | None = None
    approved_by: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    updated_at: datetime | None = None


class WooWritebackQueueListResponse(BaseModel):
    queue: list[WooWritebackQueueRead]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class WooStockSyncRequest(BaseModel):
    force: bool = False
    requested_by: str | None = "inventory-page"
    idempotency_key: str = Field(min_length=1, max_length=120)
    chunk_size: int = Field(default=50, ge=10, le=200)
    item_ids: list[int] | None = Field(default=None, max_length=5000)

    @field_validator("item_ids")
    @classmethod
    def validate_item_ids(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        if any(value <= 0 for value in values):
            raise ValueError("Item IDs must be positive integers.")
        return list(dict.fromkeys(values))


class WooStockSyncResponse(BaseModel):
    status: str
    mode: str
    requested_count: int
    candidate_count: int
    sent_count: int
    dry_run_count: int
    failed_count: int
    skipped_unmapped_count: int
    unchanged_count: int
    queue_ids: list[int] = []
    errors: list[str] = []
    failed_item_ids: list[int] = []


class WooStockSyncJobRead(BaseModel):
    id: int
    status: str
    force: bool
    requested_by: str | None = None
    chunk_size: int
    total_items: int
    processed_items: int
    sent_count: int
    dry_run_count: int
    failed_count: int
    skipped_unmapped_count: int
    unchanged_count: int
    progress_percent: float
    errors: list[str] = []
    last_error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WooStockSyncJobListResponse(BaseModel):
    jobs: list[WooStockSyncJobRead]
    total: int
    page: int = 1
    page_size: int = 25
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class WooRemapItemSummary(BaseModel):
    item_id: int
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None


class WooRemapRemoteSummary(BaseModel):
    woo_product_id: int
    woo_variation_id: int | None = None
    woo_sku: str | None = None
    woo_name: str | None = None
    parent_product_name: str | None = None
    variation_attributes: list[dict] = []
    woo_stock_snapshot: float | None = None
    mapping_status: str | None = None
    reason: str = "manual_review"


class WooRemapMappingRead(BaseModel):
    id: int
    item_id: int
    woo_product_id: int
    woo_variation_id: int | None = None
    woo_sku: str | None = None
    woo_name: str | None = None
    mapping_source: str
    confidence: float | None = None
    active: bool
    note: str | None = None
    created_at: datetime
    updated_at: datetime


class WooRemapCandidate(BaseModel):
    remote: WooRemapRemoteSummary
    current_mapping: WooRemapMappingRead | None = None
    suggested_items: list[WooRemapItemSummary] = []


class WooRemapCandidateListResponse(BaseModel):
    candidates: list[WooRemapCandidate]
    total: int
    page: int = 1
    page_size: int = 100
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class WooRemapPreviewRequest(BaseModel):
    woo_product_id: int
    woo_variation_id: int | None = None
    item_id: int


class WooRemapPreviewResponse(BaseModel):
    remote: WooRemapRemoteSummary
    item: WooRemapItemSummary
    current_mapping: WooRemapMappingRead | None = None
    proposed_mapping: dict
    warnings: list[str] = []
    errors: list[str] = []
    safe_message: str


class WooRemapCommitRequest(WooRemapPreviewRequest):
    note: str | None = None


class WooRemapCommitResponse(BaseModel):
    status: str
    mapping: WooRemapMappingRead
    warnings: list[str] = []
    safe_message: str
    reprocessed_order_lines: int = 0
    allocation_summary: dict = {}


class WooRemapMappingListResponse(BaseModel):
    mappings: list[WooRemapMappingRead]
    total: int
    page: int = 1
    page_size: int = 100
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class WooRemapDeactivateRequest(BaseModel):
    mapping_id: int
    note: str | None = None
