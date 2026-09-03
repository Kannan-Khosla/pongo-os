from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.inventory import InventoryItem, InventoryLocation


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    receipt_type: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str | None] = mapped_column(String(40), index=True)
    source: Mapped[str | None] = mapped_column(String(40), index=True)
    client: Mapped[str | None] = mapped_column(String(120), index=True)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    reference_number: Mapped[str | None] = mapped_column(String(120), index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    received_by: Mapped[str | None] = mapped_column(String(120))
    received_date: Mapped[date | None] = mapped_column(Date, index=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    items: Mapped[list["ReceiptItem"]] = relationship(back_populates="receipt", cascade="all, delete-orphan")


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"), index=True, nullable=False)
    inventory_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    inventory_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_locations.id"), index=True)
    inventory_item_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    line_status: Mapped[str | None] = mapped_column(String(40), index=True)
    scan_input: Mapped[str | None] = mapped_column(String(500))
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    category: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    uom: Mapped[str | None] = mapped_column(String(50))
    quantity_base_uom: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    previous_unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit_cost_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sales_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    brand: Mapped[str | None] = mapped_column(String(200))
    client: Mapped[str | None] = mapped_column(String(120), index=True)
    lot_number: Mapped[str | None] = mapped_column(String(120))
    expiration_date: Mapped[date | None] = mapped_column(Date)
    pkg_number: Mapped[str | None] = mapped_column(String(120))
    item_number: Mapped[str | None] = mapped_column(String(120))
    pallet_number: Mapped[str | None] = mapped_column(String(120))
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location_name: Mapped[str | None] = mapped_column("inventory_location", String(200), index=True)
    default_location: Mapped[str | None] = mapped_column(String(200))
    quantity_received: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    received_date: Mapped[date | None] = mapped_column(Date, index=True)
    po_or_receipt_number: Mapped[str | None] = mapped_column(String(120))
    name: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    receipt: Mapped[Receipt] = relationship(back_populates="items")
    inventory_item: Mapped["InventoryItem | None"] = relationship(back_populates="receipt_items")
    inventory_location: Mapped["InventoryLocation | None"] = relationship(back_populates="receipt_items")
