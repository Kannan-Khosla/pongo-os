from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import OrderItem
    from app.models.receipts import ReceiptItem


class MovementType(str, Enum):
    receiving = "receiving"
    receive_direct = "receive_direct"
    direct_receiving = "direct_receiving"
    cycle_count = "cycle_count"
    cycle_count_adjustment = "cycle_count_adjustment"
    allocation = "allocation"
    deallocation = "deallocation"
    pick = "pick"
    fulfillment = "fulfillment"
    transfer_out = "transfer_out"
    transfer_in = "transfer_in"
    adjustment_increase = "adjustment_increase"
    adjustment_decrease = "adjustment_decrease"
    damage = "damage"
    loss = "loss"
    correction = "correction"
    manual_adjustment = "manual_adjustment"
    order_allocation = "order_allocation"
    order_pick = "order_pick"
    order_completion = "order_completion"
    fulfill_order = "fulfill_order"
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
    woo_product_type: Mapped[str | None] = mapped_column(String(40), index=True)
    woo_permalink: Mapped[str | None] = mapped_column(String(1000))
    woo_status: Mapped[str | None] = mapped_column(String(80), index=True)
    woo_manage_stock: Mapped[bool | None] = mapped_column(Boolean)
    woo_stock_status: Mapped[str | None] = mapped_column(String(80), index=True)
    woo_stock_quantity_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    woo_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    woo_sync_status: Mapped[str | None] = mapped_column(String(80), index=True)
    woo_sync_error: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(200), index=True)
    unit_of_measurement: Mapped[str | None] = mapped_column(String(50))
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    default_location: Mapped[str | None] = mapped_column(String(200))
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
    non_inventory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
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
    description: Mapped[str | None] = mapped_column(String(500))
    zone: Mapped[str | None] = mapped_column(String(120), index=True)
    aisle: Mapped[str | None] = mapped_column(String(80))
    rack: Mapped[str | None] = mapped_column(String(80))
    shelf: Mapped[str | None] = mapped_column(String(80))
    bin: Mapped[str | None] = mapped_column(String(80))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    item_locations: Mapped[list["InventoryItemLocation"]] = relationship(back_populates="location", cascade="all, delete-orphan")
    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="location")
    receipt_items: Mapped[list["ReceiptItem"]] = relationship(back_populates="inventory_location")

    __table_args__ = (
        UniqueConstraint("client", "warehouse", "location_code", name="uq_inventory_locations_client_warehouse_code"),
    )


class InventoryItemLocation(TimestampMixin, Base):
    __tablename__ = "inventory_item_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_locations.id"), index=True)
    client: Mapped[str | None] = mapped_column(String(120), index=True)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    location_code: Mapped[str | None] = mapped_column(String(120), index=True)
    location_name: Mapped[str | None] = mapped_column(String(200))
    is_default_location: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    in_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    sellable: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    on_order: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    par_level: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    under_par: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    inventory_item: Mapped[InventoryItem] = relationship(back_populates="locations")
    location: Mapped[InventoryLocation | None] = relationship(back_populates="item_locations")

    __table_args__ = (
        UniqueConstraint("inventory_item_id", "location_id", name="uq_inventory_item_locations_item_location"),
        Index("ix_inventory_item_locations_item_warehouse_location", "inventory_item_id", "warehouse", "inventory_location"),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    inventory_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_locations.id"), index=True)
    inventory_item_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    from_inventory_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    to_inventory_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    movement_type: Mapped[MovementType] = mapped_column(movement_type_enum, index=True, nullable=False)
    quantity_change: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    old_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    new_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location_name: Mapped[str | None] = mapped_column("inventory_location", String(200), index=True)
    from_warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    from_inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    to_warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    to_inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    old_location_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    new_location_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    old_item_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    new_item_stock: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    movement_group_id: Mapped[str | None] = mapped_column(String(80), index=True)
    movement_source: Mapped[str | None] = mapped_column(String(80), index=True)
    reference_number: Mapped[str | None] = mapped_column(String(120), index=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reason: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(String(500))
    reference_type: Mapped[str | None] = mapped_column(String(80), index=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_by: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    inventory_item: Mapped[InventoryItem] = relationship(back_populates="stock_movements")
    location: Mapped[InventoryLocation | None] = relationship(back_populates="stock_movements")


class InventoryAuditEvent(Base):
    __tablename__ = "inventory_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    previous_in_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    new_in_stock: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    previous_allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    new_allocated: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    previous_sellable: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    new_sellable: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    reference_type: Mapped[str | None] = mapped_column(String(80), index=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, index=True)
    reference_number: Mapped[str | None] = mapped_column(String(120), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class InventoryTransfer(TimestampMixin, Base):
    __tablename__ = "inventory_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transfer_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, default="draft", nullable=False)
    from_warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    from_inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    to_warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    to_inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    lines: Mapped[list["InventoryTransferLine"]] = relationship(back_populates="transfer", cascade="all, delete-orphan")


class InventoryTransferLine(TimestampMixin, Base):
    __tablename__ = "inventory_transfer_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transfer_id: Mapped[int] = mapped_column(ForeignKey("inventory_transfers.id"), index=True, nullable=False)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    from_inventory_item_location_id: Mapped[int] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True, nullable=False)
    to_inventory_item_location_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True)
    from_warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    from_inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    to_warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    to_inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    transfer: Mapped[InventoryTransfer] = relationship(back_populates="lines")


class StockAdjustment(TimestampMixin, Base):
    __tablename__ = "stock_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adjustment_number: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, default="draft", nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    lines: Mapped[list["StockAdjustmentLine"]] = relationship(back_populates="adjustment", cascade="all, delete-orphan")


class StockAdjustmentLine(TimestampMixin, Base):
    __tablename__ = "stock_adjustment_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    adjustment_id: Mapped[int] = mapped_column(ForeignKey("stock_adjustments.id"), index=True, nullable=False)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    inventory_item_location_id: Mapped[int] = mapped_column(ForeignKey("inventory_item_locations.id"), index=True, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    old_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    new_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    quantity_change: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)

    adjustment: Mapped[StockAdjustment] = relationship(back_populates="lines")
