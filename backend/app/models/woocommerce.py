from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
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
