from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import Order, OrderItem


class Pick(TimestampMixin, Base):
    __tablename__ = "picks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pick_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="posted")
    pick_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="single_order")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_order_number: Mapped[str | None] = mapped_column(String(120), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    order: Mapped["Order | None"] = relationship()
    lines: Mapped[list["PickLine"]] = relationship(back_populates="pick", cascade="all, delete-orphan")


class PickLine(TimestampMixin, Base):
    __tablename__ = "pick_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pick_id: Mapped[int] = mapped_column(ForeignKey("picks.id"), index=True, nullable=False)
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
    quantity_allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_previously_picked: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_to_pick: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_picked_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    remaining_to_pick: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_stock_reduced: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    stock_movement_id: Mapped[int | None] = mapped_column(ForeignKey("stock_movements.id"), index=True)
    stock_reduced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    pick: Mapped[Pick] = relationship(back_populates="lines")
    order: Mapped["Order"] = relationship()
    order_line: Mapped["OrderItem"] = relationship()
