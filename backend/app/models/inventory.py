from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import OrderItem
    from app.models.receipts import ReceiptItem


class MovementType(str, Enum):
    direct_receiving = "direct_receiving"
    cycle_count = "cycle_count"
    manual_adjustment = "manual_adjustment"
    order_allocation = "order_allocation"
    order_pick = "order_pick"
    order_completion = "order_completion"
    import_update = "import_update"
    woocommerce_sync = "woocommerce_sync"


movement_type_enum = SqlEnum(
    MovementType,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    native_enum=False,
    length=32,
)


class InventoryItem(TimestampMixin, Base):
    __tablename__ = "inventory_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client: Mapped[str | None] = mapped_column(String(120), index=True)
    woo_product_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_variation_id: Mapped[int | None] = mapped_column(Integer, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(200), index=True)
    unit_of_measurement: Mapped[str | None] = mapped_column(String(50))
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    in_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    sellable: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    under_par: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    on_order: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    manufacturer_website: Mapped[str | None] = mapped_column(String(500))
    recommended_retail_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sales_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    default_econ_order: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    default_lead_time_days: Mapped[int | None] = mapped_column(Integer)
    par_level: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    assembly: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    serializable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    track_lot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    perishable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reorder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    storage_length: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    storage_width: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    storage_height: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    storage_volume: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    brand: Mapped[str | None] = mapped_column(String(200), index=True)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    source: Mapped[str | None] = mapped_column(String(60))

    locations: Mapped[list["InventoryItemLocation"]] = relationship(back_populates="inventory_item", cascade="all, delete-orphan")
    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="inventory_item")
    receipt_items: Mapped[list["ReceiptItem"]] = relationship(back_populates="inventory_item")
    order_items: Mapped[list["OrderItem"]] = relationship(back_populates="inventory_item")

    __table_args__ = (
        Index("ix_inventory_items_woo_product_variation", "woo_product_id", "woo_variation_id"),
    )


class InventoryLocation(TimestampMixin, Base):
    __tablename__ = "inventory_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client: Mapped[str | None] = mapped_column(String(120), index=True)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    location_code: Mapped[str | None] = mapped_column(String(120))
    location_name: Mapped[str | None] = mapped_column(String(200))
    zone: Mapped[str | None] = mapped_column(String(120), index=True)
    aisle: Mapped[str | None] = mapped_column(String(80))
    rack: Mapped[str | None] = mapped_column(String(80))
    shelf: Mapped[str | None] = mapped_column(String(80))
    bin: Mapped[str | None] = mapped_column(String(80))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    item_locations: Mapped[list["InventoryItemLocation"]] = relationship(back_populates="location", cascade="all, delete-orphan")
    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="inventory_location")
    receipt_items: Mapped[list["ReceiptItem"]] = relationship(back_populates="inventory_location")

    __table_args__ = (
        UniqueConstraint("client", "warehouse", "location_code", name="uq_inventory_locations_client_warehouse_code"),
    )


class InventoryItemLocation(TimestampMixin, Base):
    __tablename__ = "inventory_item_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("inventory_locations.id"), index=True, nullable=False)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    is_default_location: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    in_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    sellable: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    on_order: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)

    inventory_item: Mapped[InventoryItem] = relationship(back_populates="locations")
    location: Mapped[InventoryLocation] = relationship(back_populates="item_locations")

    __table_args__ = (
        UniqueConstraint("inventory_item_id", "location_id", name="uq_inventory_item_locations_item_location"),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    inventory_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_locations.id"), index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    movement_type: Mapped[MovementType] = mapped_column(movement_type_enum, index=True, nullable=False)
    quantity_change: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    old_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    new_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reason: Mapped[str | None] = mapped_column(String(500))
    reference_type: Mapped[str | None] = mapped_column(String(80), index=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    inventory_item: Mapped[InventoryItem] = relationship(back_populates="stock_movements")
    inventory_location: Mapped[InventoryLocation | None] = relationship(back_populates="stock_movements")
