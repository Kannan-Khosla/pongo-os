from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import Order, OrderItem


class Allocation(TimestampMixin, Base):
    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allocation_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="posted")
    allocation_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="single_order")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_order_number: Mapped[str | None] = mapped_column(String(120), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    auto_allocated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    allocation_source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False, index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    order: Mapped["Order | None"] = relationship()
    lines: Mapped[list["AllocationLine"]] = relationship(back_populates="allocation", cascade="all, delete-orphan")


class AllocationLine(TimestampMixin, Base):
    __tablename__ = "allocation_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    allocation_id: Mapped[int] = mapped_column(ForeignKey("allocations.id"), index=True, nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, nullable=False)
    order_line_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"), index=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    inventory_item_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_previously_allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_to_allocate: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_allocated_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    in_stock_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    allocated_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    sellable_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    allocated_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    sellable_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    shortage_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    auto_allocated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    allocation_source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False, index=True)

    allocation: Mapped[Allocation] = relationship(back_populates="lines")
    order: Mapped["Order"] = relationship()
    order_line: Mapped["OrderItem"] = relationship()
