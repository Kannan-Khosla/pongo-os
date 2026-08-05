from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.inventory import InventoryItem
    from app.models.routes import RouteStop


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, unique=True, index=True)
    woo_order_number: Mapped[str | None] = mapped_column(String(120), index=True)
    woo_status: Mapped[str | None] = mapped_column(String(80), index=True)
    local_status: Mapped[str | None] = mapped_column(String(80), index=True)
    currency: Mapped[str | None] = mapped_column(String(12))
    customer_id: Mapped[int | None] = mapped_column(Integer, index=True)
    customer_first_name: Mapped[str | None] = mapped_column(String(120))
    customer_last_name: Mapped[str | None] = mapped_column(String(120))
    customer_phone: Mapped[str | None] = mapped_column(String(80))
    billing_summary: Mapped[dict | None] = mapped_column(JSON)
    shipping_summary: Mapped[dict | None] = mapped_column(JSON)
    payment_method: Mapped[str | None] = mapped_column(String(120))
    payment_method_title: Mapped[str | None] = mapped_column(String(240))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    shipping_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tax_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    date_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    date_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    date_paid: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str | None] = mapped_column(String(80), index=True)
    sync_error: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    order_number: Mapped[str | None] = mapped_column(String(120), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(240))
    customer_email: Mapped[str | None] = mapped_column(String(240))
    placed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    completed_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column(String(80), index=True)
    allocation_status: Mapped[str | None] = mapped_column(String(80), index=True)
    pick_status: Mapped[str | None] = mapped_column(String(80), index=True)
    completion_status: Mapped[str | None] = mapped_column(String(80), index=True)
    auto_allocation_status: Mapped[str | None] = mapped_column(String(80), index=True)
    completed_without_picking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_historical_snapshot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    historical_source_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    allocation_exception_reason: Mapped[str | None] = mapped_column(Text)
    workflow_notes: Mapped[str | None] = mapped_column(Text)
    shipping_address_1: Mapped[str | None] = mapped_column(String(240))
    shipping_address_2: Mapped[str | None] = mapped_column(String(240))
    shipping_address_3: Mapped[str | None] = mapped_column(String(240))
    shipping_city: Mapped[str | None] = mapped_column(String(120))
    shipping_state: Mapped[str | None] = mapped_column(String(120))
    shipping_country: Mapped[str | None] = mapped_column(String(120))
    shipping_zip: Mapped[str | None] = mapped_column(String(40))
    shipping_phone: Mapped[str | None] = mapped_column(String(80))
    billing_address_1: Mapped[str | None] = mapped_column(String(240))
    billing_address_2: Mapped[str | None] = mapped_column(String(240))
    billing_address_3: Mapped[str | None] = mapped_column(String(240))
    billing_city: Mapped[str | None] = mapped_column(String(120))
    billing_state: Mapped[str | None] = mapped_column(String(120))
    billing_country: Mapped[str | None] = mapped_column(String(120))
    billing_zip: Mapped[str | None] = mapped_column(String(40))
    billing_phone: Mapped[str | None] = mapped_column(String(80))
    company: Mapped[str | None] = mapped_column(String(240))
    tracking_number: Mapped[str | None] = mapped_column(String(240))
    raw_woo_payload: Mapped[dict | None] = mapped_column(JSON)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    route_stops: Mapped[list["RouteStop"]] = relationship(back_populates="order")


class OrderItem(TimestampMixin, Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, nullable=False)
    woo_order_item_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_product_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_variation_id: Mapped[int | None] = mapped_column(Integer, index=True)
    inventory_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    line_number: Mapped[int | None] = mapped_column(Integer)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantity_allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantity_picked: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantity_fulfilled: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    quantity_stock_reduced: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    stock_reduced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ordered_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    ordered_uom: Mapped[str | None] = mapped_column(String(50))
    allocated_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    picked_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    fulfilled_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    line_subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    line_tax: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    matched_status: Mapped[str | None] = mapped_column(String(80), index=True)
    availability_status: Mapped[str | None] = mapped_column(String(80), index=True)
    allocation_status: Mapped[str | None] = mapped_column(String(80), index=True)
    pick_status: Mapped[str | None] = mapped_column(String(80), index=True)
    allocation_exception_reason: Mapped[str | None] = mapped_column(Text)
    sellable_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    shortage_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    sync_status: Mapped[str | None] = mapped_column(String(80), index=True)
    sync_error: Mapped[str | None] = mapped_column(Text)
    unit_cost_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    brand: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(80), index=True)

    order: Mapped[Order] = relationship(back_populates="items")
    inventory_item: Mapped["InventoryItem | None"] = relationship(back_populates="order_items")
