from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory import InventoryItem
    from app.models.orders import Order, OrderItem


class Fulfillment(TimestampMixin, Base):
    __tablename__ = "fulfillments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fulfillment_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="posted")
    fulfillment_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="single_order")
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_order_number: Mapped[str | None] = mapped_column(String(120), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    order: Mapped["Order | None"] = relationship()
    lines: Mapped[list["FulfillmentLine"]] = relationship(back_populates="fulfillment", cascade="all, delete-orphan")


class FulfillmentLine(TimestampMixin, Base):
    __tablename__ = "fulfillment_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fulfillment_id: Mapped[int] = mapped_column(ForeignKey("fulfillments.id"), index=True, nullable=False)
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
    quantity_picked: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_previously_fulfilled: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_to_fulfill: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    quantity_fulfilled_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    remaining_to_fulfill: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    in_stock_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    allocated_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    sellable_before: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    in_stock_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    allocated_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    sellable_after: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    fulfillment: Mapped[Fulfillment] = relationship(back_populates="lines")
    order: Mapped["Order"] = relationship()
    order_line: Mapped["OrderItem"] = relationship()
    inventory_item: Mapped["InventoryItem"] = relationship()
