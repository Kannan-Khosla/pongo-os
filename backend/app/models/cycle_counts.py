from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.inventory import InventoryItem


class CycleCount(Base):
    __tablename__ = "cycle_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    count_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, default="draft", nullable=False)
    warehouse: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    count_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    lines: Mapped[list["CycleCountLine"]] = relationship(back_populates="cycle_count", cascade="all, delete-orphan")


class CycleCountLine(Base):
    __tablename__ = "cycle_count_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_count_id: Mapped[int] = mapped_column(ForeignKey("cycle_counts.id"), index=True, nullable=False)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    inventory_item_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    warehouse: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    system_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    counted_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    variance_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    variance_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    cycle_count: Mapped[CycleCount] = relationship(back_populates="lines")
    item: Mapped["InventoryItem | None"] = relationship()
