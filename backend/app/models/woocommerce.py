from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WooCommerceSyncRun(Base):
    __tablename__ = "woocommerce_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    total_remote_records: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    errors: Mapped[list["WooCommerceSyncError"]] = relationship(back_populates="sync_run", cascade="all, delete-orphan")


class WooCommerceSyncError(Base):
    __tablename__ = "woocommerce_sync_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sync_run_id: Mapped[int] = mapped_column(ForeignKey("woocommerce_sync_runs.id"), index=True, nullable=False)
    remote_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    remote_line_item_id: Mapped[int | None] = mapped_column(Integer, index=True)
    remote_product_id: Mapped[int | None] = mapped_column(Integer, index=True)
    remote_variation_id: Mapped[int | None] = mapped_column(Integer, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sync_run: Mapped[WooCommerceSyncRun] = relationship(back_populates="errors")


class WooItemMapping(Base):
    __tablename__ = "woo_item_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    woo_product_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    woo_variation_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_sku: Mapped[str | None] = mapped_column(String(120), index=True)
    woo_name: Mapped[str | None] = mapped_column(String(500))
    mapping_source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("item_id", "woo_product_id", "woo_variation_id", "active", name="uq_woo_item_mappings_item_remote_active"),
    )


class WooWritebackQueue(Base):
    __tablename__ = "woo_writeback_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    woo_entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_product_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_variation_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True, nullable=False)
    environment: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    allowed_host: Mapped[str | None] = mapped_column(String(255), index=True)
    preview_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_json: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str | None] = mapped_column(String(120), index=True)
    approved_by: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)


class WooStockSyncJob(Base):
    __tablename__ = "woo_stock_sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True, nullable=False)
    force: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(120), index=True)
    chunk_size: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dry_run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_unmapped_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_item_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_item_ids: Mapped[list[int] | None] = mapped_column(JSON)
    terminal_failed_item_ids: Mapped[list[int] | None] = mapped_column(JSON)
    retry_attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list[str] | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)


class WooCommerceWebhookDelivery(Base):
    __tablename__ = "woocommerce_webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(191), index=True, nullable=False)
    webhook_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    topic: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    resource: Mapped[str | None] = mapped_column(String(80), index=True)
    event: Mapped[str | None] = mapped_column(String(80), index=True)
    source_host: Mapped[str | None] = mapped_column(String(255), index=True)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    local_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    sync_run_id: Mapped[int | None] = mapped_column(ForeignKey("woocommerce_sync_runs.id"), index=True)
    processing_status: Mapped[str] = mapped_column(String(40), default="received", index=True, nullable=False)
    created_order: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("webhook_id", "delivery_id", "payload_sha256", name="uq_woo_webhook_delivery_identity"),
    )


class WooCommerceOrderEvent(Base):
    __tablename__ = "woocommerce_order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    webhook_delivery_id: Mapped[int] = mapped_column(ForeignKey("woocommerce_webhook_deliveries.id"), unique=True, nullable=False)
    local_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, nullable=False)
    woo_order_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), default="order_created", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
