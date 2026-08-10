from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models.inventory import (
    InventoryItem,
    InventoryItemLocation,
    InventoryLocation,
    InventoryTransfer,
    InventoryTransferLine,
    MovementType,
    StockAdjustment,
    StockAdjustmentLine,
    StockMovement,
)
from app.services.stock_mutation_guard import begin_stock_mutation, complete_stock_mutation

STOCK_MUTATION_LOCK_KEY = int.from_bytes(b"PONGOFIF", byteorder="big")


@dataclass
class LocationStockChange:
    item: InventoryItem
    item_location: InventoryItemLocation
    old_location_stock: Decimal
    new_location_stock: Decimal
    old_item_stock: Decimal
    new_item_stock: Decimal
    old_location_allocated: Decimal
    new_location_allocated: Decimal
    old_item_allocated: Decimal
    new_item_allocated: Decimal


class StaleStockQuantityError(ValueError):
    pass


def to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def location_display(location: InventoryItemLocation | InventoryLocation | None) -> str | None:
    if location is None:
        return None
    return getattr(location, "inventory_location", None) or getattr(location, "location_code", None) or getattr(location, "location_name", None)


def find_item_location(db: Session, item_id: int, warehouse: str | None, inventory_location: str | None) -> InventoryItemLocation | None:
    warehouse = (warehouse or "").strip()
    inventory_location = (inventory_location or "").strip()
    statement = select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item_id, InventoryItemLocation.active.is_(True))
    if warehouse:
        statement = statement.where(InventoryItemLocation.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(InventoryItemLocation.inventory_location == inventory_location)
    return db.scalars(statement.order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.id.asc())).first()


def lock_inventory_stock(db: Session, item_ids: list[int] | set[int]) -> None:
    ids = sorted({int(item_id) for item_id in item_ids})
    if not ids:
        return
    lock_stock_mutation_scope(db)
    db.scalars(
        select(InventoryItem)
        .where(InventoryItem.id.in_(ids))
        .order_by(InventoryItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    db.scalars(
        select(InventoryItemLocation)
        .where(InventoryItemLocation.inventory_item_id.in_(ids))
        .order_by(InventoryItemLocation.inventory_item_id, InventoryItemLocation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()


def lock_stock_mutation_scope(db: Session) -> None:
    db.flush()
    # ponytail: one transaction lock keeps stock/allocation ordering deterministic;
    # replace with per-item advisory locks only if measured write throughput requires it.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": STOCK_MUTATION_LOCK_KEY})


def assert_stock_location_active(db: Session, row: InventoryItemLocation) -> None:
    if not row.active:
        raise ValueError("Inventory location is inactive and cannot be changed.")
    statement = select(InventoryLocation)
    if row.location_id is not None:
        statement = statement.where(InventoryLocation.id == row.location_id)
    elif row.warehouse and row.inventory_location:
        statement = statement.where(
            InventoryLocation.warehouse == row.warehouse,
            or_(
                InventoryLocation.location_code == row.inventory_location,
                InventoryLocation.location_name == row.inventory_location,
            ),
        )
    else:
        return
    locations = list(db.scalars(statement.order_by(InventoryLocation.id).with_for_update().execution_options(populate_existing=True).limit(2)).all())
    if row.location_id is not None and not locations:
        raise ValueError("Inventory location no longer exists.")
    if len(locations) > 1:
        raise ValueError("Inventory location mapping is ambiguous.")
    if locations and not locations[0].active:
        raise ValueError("Physical inventory location is inactive and cannot be changed.")


def get_or_create_item_location(
    db: Session,
    item: InventoryItem,
    warehouse: str | None,
    inventory_location: str | None,
    *,
    location_id: int | None = None,
    is_default_location: bool | None = None,
    par_level: Decimal | float | int | None = None,
    active: bool = True,
    create_physical_location: bool = True,
) -> InventoryItemLocation:
    warehouse = (warehouse or item.warehouse or "UNASSIGNED").strip() or "UNASSIGNED"
    inventory_location = (inventory_location or item.inventory_location or item.default_location or "UNASSIGNED").strip() or "UNASSIGNED"
    physical_location = resolve_or_create_physical_location(db, item.client, warehouse, inventory_location, location_id, create=create_physical_location)

    row = db.scalars(
        select(InventoryItemLocation).where(
            InventoryItemLocation.inventory_item_id == item.id,
            InventoryItemLocation.warehouse == warehouse,
            InventoryItemLocation.inventory_location == inventory_location,
            InventoryItemLocation.active.is_(True),
        )
    ).first()
    if row is None and physical_location is not None:
        row = db.scalars(
            select(InventoryItemLocation).where(
                InventoryItemLocation.inventory_item_id == item.id,
                InventoryItemLocation.location_id == physical_location.id,
                InventoryItemLocation.active.is_(True),
            )
        ).first()
    if row is None:
        existing_rows = db.scalar(select(func.count(InventoryItemLocation.id)).where(InventoryItemLocation.inventory_item_id == item.id)) or 0
        row = InventoryItemLocation(
            inventory_item_id=item.id,
            location_id=physical_location.id if physical_location else None,
            client=item.client,
            warehouse=warehouse,
            inventory_location=inventory_location,
            location_code=physical_location.location_code if physical_location else inventory_location,
            location_name=physical_location.location_name if physical_location else inventory_location,
            is_default_location=existing_rows == 0,
            in_stock=(item.in_stock or Decimal("0")) if existing_rows == 0 else Decimal("0"),
            allocated=(item.allocated or Decimal("0")) if existing_rows == 0 else Decimal("0"),
            sellable=(item.sellable or ((item.in_stock or Decimal("0")) - (item.allocated or Decimal("0")))) if existing_rows == 0 else Decimal("0"),
            on_order=(item.on_order or Decimal("0")) if existing_rows == 0 else Decimal("0"),
            par_level=to_decimal(par_level) if par_level is not None else item.par_level,
            active=active,
        )
        db.add(row)
        db.flush()
    else:
        row.location_id = physical_location.id if physical_location else row.location_id
        row.client = item.client
        row.warehouse = warehouse
        row.inventory_location = inventory_location
        row.location_code = physical_location.location_code if physical_location else (row.location_code or inventory_location)
        row.location_name = physical_location.location_name if physical_location else (row.location_name or inventory_location)
        if par_level is not None:
            row.par_level = to_decimal(par_level)
        row.active = active

    if is_default_location:
        set_default_item_location(db, item.id, row)
    recalculate_item_location(row, item)
    recalculate_item_totals(db, item.id)
    return row


def resolve_or_create_physical_location(db: Session, client: str | None, warehouse: str, inventory_location: str, location_id: int | None = None, *, create: bool = True) -> InventoryLocation | None:
    if location_id is not None:
        location = db.get(InventoryLocation, location_id)
        if location is None:
            raise HTTPException(status_code=404, detail="Inventory location not found.")
        if not location.active:
            raise HTTPException(status_code=409, detail="Inventory location is inactive.")
        return location
    location = db.scalars(
        select(InventoryLocation).where(
            InventoryLocation.warehouse == warehouse,
            or_(InventoryLocation.location_code == inventory_location, InventoryLocation.location_name == inventory_location),
        )
    ).first()
    if location is not None:
        if not location.active:
            raise HTTPException(status_code=409, detail="Inventory location is inactive.")
        return location
    if not create:
        return None
    location = InventoryLocation(
        client=client,
        warehouse=warehouse,
        location_code=inventory_location,
        location_name=inventory_location,
        active=True,
    )
    db.add(location)
    db.flush()
    return location


def set_default_item_location(db: Session, item_id: int, default_row: InventoryItemLocation) -> None:
    rows = db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item_id)).all()
    for row in rows:
        row.is_default_location = row.id == default_row.id


def recalculate_item_location(row: InventoryItemLocation, item: InventoryItem | None = None) -> None:
    row.in_stock = to_decimal(row.in_stock)
    row.allocated = to_decimal(row.allocated)
    row.on_order = to_decimal(row.on_order)
    row.sellable = row.in_stock - row.allocated
    par_level = row.par_level if row.par_level is not None else (item.par_level if item is not None else None)
    row.under_par = bool(par_level is not None and row.in_stock <= par_level)


def recalculate_item_totals(db: Session, item_id: int) -> InventoryItem:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found.")
    rows = list(db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item_id, InventoryItemLocation.active.is_(True))).all())
    for row in rows:
        recalculate_item_location(row, item)
    item.in_stock = sum((row.in_stock or Decimal("0") for row in rows), Decimal("0"))
    item.allocated = sum((row.allocated or Decimal("0") for row in rows), Decimal("0"))
    item.sellable = sum((row.sellable or Decimal("0") for row in rows), Decimal("0"))
    item.on_order = sum((row.on_order or Decimal("0") for row in rows), Decimal("0")) if rows else (item.on_order or Decimal("0"))
    item.under_par = bool(item.par_level is not None and item.in_stock <= item.par_level)
    default_row = next((row for row in rows if row.is_default_location), rows[0] if rows else None)
    if default_row is not None:
        item.warehouse = default_row.warehouse
        item.inventory_location = default_row.inventory_location
        item.default_location = default_row.inventory_location
    return item


def ensure_default_item_location_from_item(db: Session, item: InventoryItem, *, create_physical_location: bool = False) -> InventoryItemLocation:
    rows = list(
        db.scalars(
            select(InventoryItemLocation)
            .where(InventoryItemLocation.inventory_item_id == item.id)
            .order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.id.asc())
        ).all()
    )
    if rows:
        row = next((candidate for candidate in rows if candidate.is_default_location), rows[0])
        if not row.is_default_location:
            set_default_item_location(db, item.id, row)
        recalculate_item_totals(db, item.id)
        return row
    return get_or_create_item_location(
        db,
        item,
        item.warehouse,
        item.inventory_location or item.default_location,
        is_default_location=True,
        create_physical_location=create_physical_location,
    )


def assert_location_invariants(row: InventoryItemLocation) -> None:
    recalculate_item_location(row)
    if row.in_stock < 0:
        raise ValueError("Location In Stock cannot be negative.")
    if row.allocated < 0:
        raise ValueError("Location Allocated cannot be negative.")
    if row.allocated > row.in_stock:
        raise ValueError("Location Allocated cannot exceed In Stock.")
    if row.sellable < 0:
        raise ValueError("Location Sellable cannot be negative.")


def assert_item_invariants(item: InventoryItem) -> None:
    if (item.in_stock or Decimal("0")) < 0:
        raise ValueError("Item In Stock cannot be negative.")
    if (item.allocated or Decimal("0")) < 0:
        raise ValueError("Item Allocated cannot be negative.")
    if (item.allocated or Decimal("0")) > (item.in_stock or Decimal("0")):
        raise ValueError("Item Allocated cannot exceed In Stock.")
    if (item.sellable or Decimal("0")) < 0:
        raise ValueError("Item Sellable cannot be negative.")


def receive_to_location(
    db: Session,
    item: InventoryItem,
    warehouse: str,
    inventory_location: str,
    quantity: Decimal,
    *,
    unit_cost: Decimal | None = None,
    reference_number: str | None = None,
    reference_type: str = "direct_receipt",
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> LocationStockChange:
    quantity = to_decimal(quantity)
    if quantity <= 0:
        raise ValueError("Received quantity must be greater than zero.")
    row = get_or_create_item_location(db, item, warehouse, inventory_location, is_default_location=not bool(item.default_location))
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    row.in_stock = old_location_stock + quantity
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    create_stock_movement(
        db,
        item,
        MovementType.receive_direct,
        quantity,
        row,
        old_location_stock,
        row.in_stock,
        old_item_stock,
        item.in_stock,
        unit_cost=unit_cost,
        reason="Direct receiving without PO",
        reference_number=reference_number,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        created_by=created_by,
    )
    return LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)


def set_opening_balance(
    db: Session,
    item_id: int,
    *,
    in_stock: Decimal,
    allocated: Decimal,
    warehouse: str,
    inventory_location: str,
    idempotency_key: str,
    created_by: str | None = "system",
    reference_type: str = "opening_balance",
    reference_id: int | None = None,
    reason: str = "Explicit opening balance",
) -> dict:
    payload = {
        "item_id": item_id,
        "in_stock": in_stock,
        "allocated": allocated,
        "warehouse": warehouse,
        "inventory_location": inventory_location,
        "created_by": created_by,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "reason": reason,
    }
    mutation, replay = begin_stock_mutation(db, "opening_balance", idempotency_key, payload)
    if replay is not None:
        return replay
    if in_stock < 0 or allocated < 0 or allocated > in_stock:
        raise ValueError("Opening balance requires 0 <= Allocated <= In Stock.")
    lock_inventory_stock(db, {item_id})
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise ValueError("Item not found.")
    history_exists = bool(db.scalar(select(func.count(StockMovement.id)).where(StockMovement.inventory_item_id == item_id)))
    if to_decimal(item.in_stock) != 0 or to_decimal(item.allocated) != 0 or history_exists:
        raise ValueError("Opening balance is only allowed before any operational stock or movement history exists.")
    row = get_or_create_item_location(db, item, warehouse, inventory_location, is_default_location=True)
    old_location_stock = to_decimal(row.in_stock)
    old_item_stock = to_decimal(item.in_stock)
    old_item_allocated = to_decimal(item.allocated)
    old_item_sellable = to_decimal(item.sellable)
    row.in_stock = in_stock
    row.allocated = allocated
    recalculate_item_location(row, item)
    recalculate_item_totals(db, item.id)
    create_stock_movement(
        db,
        item,
        MovementType.opening_balance_import,
        in_stock - old_location_stock,
        row,
        old_location_stock,
        in_stock,
        old_item_stock,
        to_decimal(item.in_stock),
        unit_cost=item.unit_cost,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        reference_number=idempotency_key,
        created_by=created_by,
    )
    from app.models.inventory import InventoryAuditEvent

    db.add(
        InventoryAuditEvent(
            item_id=item.id,
            sku=item.sku,
            barcode=item.barcode,
            event_type="opening_balance",
            quantity_delta=in_stock - old_item_stock,
            previous_in_stock=old_item_stock,
            new_in_stock=to_decimal(item.in_stock),
            previous_allocated=old_item_allocated,
            new_allocated=to_decimal(item.allocated),
            previous_sellable=old_item_sellable,
            new_sellable=to_decimal(item.sellable),
            warehouse=row.warehouse,
            inventory_location=row.inventory_location,
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=idempotency_key,
            notes=reason,
            created_by=created_by or "system",
        )
    )
    response = {
        "status": "completed",
        "item_id": item.id,
        "in_stock": float(item.in_stock),
        "allocated": float(item.allocated),
        "sellable": float(item.sellable),
    }
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def cycle_count_location(
    db: Session,
    item: InventoryItem,
    warehouse: str,
    inventory_location: str,
    counted_quantity: Decimal,
    *,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> LocationStockChange:
    counted_quantity = to_decimal(counted_quantity)
    if counted_quantity < 0:
        raise ValueError("Counted quantity cannot be negative.")
    row = get_or_create_item_location(db, item, warehouse, inventory_location)
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    row.in_stock = counted_quantity
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    change = counted_quantity - old_location_stock
    if change != 0:
        create_stock_movement(
            db,
            item,
            MovementType.cycle_count_adjustment,
            change,
            row,
            old_location_stock,
            row.in_stock,
            old_item_stock,
            item.in_stock,
            unit_cost=item.unit_cost,
            reason="Cycle count adjustment",
            reference_number=reference_number,
            reference_type="cycle_count",
            reference_id=reference_id,
            notes=notes,
            created_by=created_by,
        )
    return LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)


def allocate_from_location(
    db: Session,
    item: InventoryItem,
    quantity: Decimal,
    *,
    preferred_location_id: int | None = None,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> LocationStockChange:
    quantity = to_decimal(quantity)
    if quantity <= 0:
        raise ValueError("Allocation quantity must be greater than zero.")
    row = choose_allocation_location(db, item, quantity, preferred_location_id)
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    row.allocated = old_location_allocated + quantity
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    return LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)


def choose_allocation_location(db: Session, item: InventoryItem, quantity: Decimal, preferred_location_id: int | None = None) -> InventoryItemLocation:
    statement = select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item.id, InventoryItemLocation.active.is_(True))
    if preferred_location_id is not None:
        statement = statement.where(InventoryItemLocation.id == preferred_location_id)
    rows = list(db.scalars(statement.order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.sellable.desc(), InventoryItemLocation.id.asc())).all())
    for row in rows:
        recalculate_item_location(row, item)
        if row.sellable >= quantity:
            return row
    raise ValueError(f"Item {item.sku or item.id} does not have enough sellable stock in one location.")


def pick_from_location_audit_only(
    db: Session,
    item: InventoryItem,
    quantity: Decimal,
    *,
    preferred_location_id: int | None = None,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> InventoryItemLocation:
    row = choose_allocated_location(db, item, to_decimal(quantity), preferred_location_id)
    create_audit_event(db, item, row, "pick", to_decimal(quantity), reference_number, "pick", reference_id, notes, created_by)
    return row


def reduce_pick_from_location(
    db: Session,
    item: InventoryItem,
    row: InventoryItemLocation,
    quantity: Decimal,
    *,
    reference_number: str | None = None,
    reference_type: str = "pick",
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> tuple[LocationStockChange, StockMovement]:
    quantity = to_decimal(quantity)
    if quantity <= 0:
        raise ValueError("Pick quantity must be greater than zero.")
    if row.inventory_item_id != item.id:
        raise ValueError("Pick location does not belong to the item.")
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    if old_location_stock < quantity:
        raise ValueError("Pick quantity exceeds location In Stock.")
    if old_location_allocated < quantity:
        raise ValueError("Pick quantity exceeds location Allocated.")
    row.in_stock = old_location_stock - quantity
    row.allocated = old_location_allocated - quantity
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    movement = create_stock_movement(
        db,
        item,
        MovementType.pick_stock_reduction,
        -quantity,
        row,
        old_location_stock,
        row.in_stock,
        old_item_stock,
        item.in_stock,
        unit_cost=item.unit_cost,
        reason="Pick stock reduction",
        reference_number=reference_number,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        created_by=created_by,
    )
    change = LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)
    return change, movement


def restore_unpick_to_location(
    db: Session,
    item: InventoryItem,
    row: InventoryItemLocation,
    quantity: Decimal,
    *,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> tuple[LocationStockChange, StockMovement]:
    quantity = to_decimal(quantity)
    if quantity <= 0:
        raise ValueError("Unpick quantity must be greater than zero.")
    if row.inventory_item_id != item.id:
        raise ValueError("Original pick location does not belong to the item.")
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    row.in_stock = old_location_stock + quantity
    row.allocated = old_location_allocated + quantity
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    movement = create_stock_movement(
        db,
        item,
        MovementType.unpick_stock_restoration,
        quantity,
        row,
        old_location_stock,
        row.in_stock,
        old_item_stock,
        item.in_stock,
        unit_cost=item.unit_cost,
        reason="Unpick stock restoration",
        reference_number=reference_number,
        reference_type="unpick",
        reference_id=reference_id,
        notes=notes,
        created_by=created_by,
    )
    change = LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)
    return change, movement


def fulfill_from_location(
    db: Session,
    item: InventoryItem,
    quantity: Decimal,
    *,
    preferred_location_id: int | None = None,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> LocationStockChange:
    quantity = to_decimal(quantity)
    if quantity <= 0:
        raise ValueError("Fulfillment quantity must be greater than zero.")
    row = choose_allocated_location(db, item, quantity, preferred_location_id)
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    row.in_stock = old_location_stock - quantity
    row.allocated = old_location_allocated - quantity
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    create_stock_movement(
        db,
        item,
        MovementType.fulfill_order,
        -quantity,
        row,
        old_location_stock,
        row.in_stock,
        old_item_stock,
        item.in_stock,
        unit_cost=item.unit_cost,
        reason="Local order fulfillment",
        reference_number=reference_number,
        reference_type="fulfillment",
        reference_id=reference_id,
        notes=notes,
        created_by=created_by,
    )
    return LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)


def choose_allocated_location(db: Session, item: InventoryItem, quantity: Decimal, preferred_location_id: int | None = None) -> InventoryItemLocation:
    statement = select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item.id, InventoryItemLocation.active.is_(True))
    if preferred_location_id is not None:
        statement = statement.where(InventoryItemLocation.id == preferred_location_id)
    rows = list(db.scalars(statement.order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.allocated.desc(), InventoryItemLocation.id.asc())).all())
    for row in rows:
        recalculate_item_location(row, item)
        if row.allocated >= quantity and row.in_stock >= quantity:
            return row
    raise ValueError(f"Item {item.sku or item.id} does not have enough allocated stock in one location.")


def transfer_between_locations(
    db: Session,
    item: InventoryItem,
    from_row: InventoryItemLocation,
    to_warehouse: str,
    to_inventory_location: str,
    quantity: Decimal,
    *,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> tuple[LocationStockChange, LocationStockChange]:
    quantity = to_decimal(quantity)
    if quantity <= 0:
        raise ValueError("Transfer quantity must be greater than zero.")
    if from_row.inventory_item_id != item.id:
        raise ValueError("Transfer source location does not belong to the item.")
    assert_stock_location_active(db, from_row)
    to_row = get_or_create_item_location(db, item, to_warehouse, to_inventory_location)
    assert_stock_location_active(db, to_row)
    old_item_stock = item.in_stock or Decimal("0")
    from_old_stock, from_old_allocated = from_row.in_stock or Decimal("0"), from_row.allocated or Decimal("0")
    to_old_stock, to_old_allocated = to_row.in_stock or Decimal("0"), to_row.allocated or Decimal("0")
    from_row.in_stock = from_old_stock - quantity
    to_row.in_stock = to_old_stock + quantity
    recalculate_item_location(from_row, item)
    recalculate_item_location(to_row, item)
    assert_location_invariants(from_row)
    assert_location_invariants(to_row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    movement_group_id = str(uuid4())
    create_stock_movement(db, item, MovementType.transfer_out, -quantity, from_row, from_old_stock, from_row.in_stock, old_item_stock, item.in_stock, reference_number=reference_number, reference_type="transfer", reference_id=reference_id, notes=notes, created_by=created_by, movement_group_id=movement_group_id, to_row=to_row)
    create_stock_movement(db, item, MovementType.transfer_in, quantity, to_row, to_old_stock, to_row.in_stock, old_item_stock, item.in_stock, reference_number=reference_number, reference_type="transfer", reference_id=reference_id, notes=notes, created_by=created_by, movement_group_id=movement_group_id, from_row=from_row)
    return (
        LocationStockChange(item, from_row, from_old_stock, from_row.in_stock, old_item_stock, item.in_stock, from_old_allocated, from_row.allocated, item.allocated, item.allocated),
        LocationStockChange(item, to_row, to_old_stock, to_row.in_stock, old_item_stock, item.in_stock, to_old_allocated, to_row.allocated, item.allocated, item.allocated),
    )


def adjust_location_stock(
    db: Session,
    item: InventoryItem,
    row: InventoryItemLocation,
    quantity_change: Decimal,
    *,
    adjustment_type: str,
    reason: str,
    reference_number: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
) -> LocationStockChange:
    quantity_change = to_decimal(quantity_change)
    if not reason or not reason.strip():
        raise ValueError("Stock adjustment reason is required.")
    if adjustment_type not in {"correction", "damage", "loss", "found", "manual_increase", "manual_decrease"}:
        raise ValueError("Adjustment type is invalid.")
    assert_stock_location_active(db, row)
    old_location_stock, old_item_stock = row.in_stock or Decimal("0"), item.in_stock or Decimal("0")
    old_location_allocated, old_item_allocated = row.allocated or Decimal("0"), item.allocated or Decimal("0")
    row.in_stock = old_location_stock + quantity_change
    recalculate_item_location(row, item)
    assert_location_invariants(row)
    item = recalculate_item_totals(db, item.id)
    assert_item_invariants(item)
    movement_type = MovementType.adjustment_increase if quantity_change > 0 else MovementType.adjustment_decrease
    if adjustment_type == "damage":
        movement_type = MovementType.damage
    elif adjustment_type == "loss":
        movement_type = MovementType.loss
    elif adjustment_type == "correction":
        movement_type = MovementType.correction
    create_stock_movement(
        db,
        item,
        movement_type,
        quantity_change,
        row,
        old_location_stock,
        row.in_stock,
        old_item_stock,
        item.in_stock,
        unit_cost=item.unit_cost,
        reason=reason,
        reference_number=reference_number,
        reference_type="stock_adjustment",
        reference_id=reference_id,
        notes=notes,
        created_by=created_by,
    )
    return LocationStockChange(item, row, old_location_stock, row.in_stock, old_item_stock, item.in_stock, old_location_allocated, row.allocated, old_item_allocated, item.allocated)


def create_stock_movement(
    db: Session,
    item: InventoryItem,
    movement_type: MovementType,
    quantity_change: Decimal,
    row: InventoryItemLocation,
    old_location_stock: Decimal,
    new_location_stock: Decimal,
    old_item_stock: Decimal,
    new_item_stock: Decimal,
    *,
    unit_cost: Decimal | None = None,
    reason: str | None = None,
    reference_number: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    created_by: str | None = "system",
    movement_group_id: str | None = None,
    from_row: InventoryItemLocation | None = None,
    to_row: InventoryItemLocation | None = None,
) -> StockMovement:
    movement = StockMovement(
        inventory_item_id=item.id,
        inventory_location_id=row.location_id,
        inventory_item_location_id=row.id,
        from_inventory_location_id=from_row.id if from_row else None,
        to_inventory_location_id=to_row.id if to_row else None,
        sku=item.sku,
        barcode=item.barcode,
        movement_type=movement_type,
        quantity_change=quantity_change,
        old_stock=old_item_stock,
        new_stock=new_item_stock,
        warehouse=row.warehouse,
        inventory_location_name=row.inventory_location,
        from_warehouse=from_row.warehouse if from_row else None,
        from_inventory_location=from_row.inventory_location if from_row else None,
        to_warehouse=to_row.warehouse if to_row else None,
        to_inventory_location=to_row.inventory_location if to_row else None,
        old_location_stock=old_location_stock,
        new_location_stock=new_location_stock,
        old_item_stock=old_item_stock,
        new_item_stock=new_item_stock,
        movement_group_id=movement_group_id,
        movement_source="local",
        reference_number=reference_number,
        unit_cost=unit_cost,
        reason=reason,
        notes=notes,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=created_by,
    )
    db.add(movement)
    return movement


def create_audit_event(db: Session, item: InventoryItem, row: InventoryItemLocation, event_type: str, quantity_delta: Decimal, reference_number: str | None, reference_type: str, reference_id: int | None, notes: str | None, created_by: str | None) -> None:
    from app.models.inventory import InventoryAuditEvent

    db.add(
        InventoryAuditEvent(
            item_id=item.id,
            sku=item.sku,
            barcode=item.barcode,
            event_type=event_type,
            quantity_delta=quantity_delta,
            previous_in_stock=item.in_stock or Decimal("0"),
            new_in_stock=item.in_stock or Decimal("0"),
            previous_allocated=item.allocated or Decimal("0"),
            new_allocated=item.allocated or Decimal("0"),
            previous_sellable=item.sellable or Decimal("0"),
            new_sellable=item.sellable or Decimal("0"),
            warehouse=row.warehouse,
            inventory_location=row.inventory_location,
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=reference_number,
            notes=notes,
            created_by=created_by or "system",
        )
    )


def next_transfer_number(db: Session, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    prefix = f"TR-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(InventoryTransfer.id)).where(InventoryTransfer.transfer_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def next_adjustment_number(db: Session, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    prefix = f"ADJ-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(StockAdjustment.id)).where(StockAdjustment.adjustment_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def create_committed_transfer(
    db: Session,
    *,
    item: InventoryItem,
    from_row: InventoryItemLocation,
    to_warehouse: str,
    to_inventory_location: str,
    quantity: Decimal,
    notes: str | None = None,
    created_by: str | None = "system",
    idempotency_key: str | None = None,
) -> InventoryTransfer:
    request_payload = {
        "item_id": item.id,
        "from_inventory_item_location_id": from_row.id,
        "to_warehouse": to_warehouse,
        "to_inventory_location": to_inventory_location,
        "quantity": quantity,
        "notes": notes,
        "created_by": created_by,
    }
    mutation, replay = begin_stock_mutation(db, "inventory_transfer", idempotency_key, request_payload)
    if replay is not None:
        transfer = db.get(InventoryTransfer, replay["transfer_id"])
        setattr(transfer, "_idempotent_replay", True)
        return transfer
    lock_inventory_stock(db, {item.id})
    now = datetime.now(timezone.utc)
    transfer = InventoryTransfer(
        transfer_number=next_transfer_number(db, now),
        status="committed",
        from_warehouse=from_row.warehouse,
        from_inventory_location=from_row.inventory_location,
        to_warehouse=to_warehouse,
        to_inventory_location=to_inventory_location,
        notes=notes,
        created_by=created_by or "system",
        committed_at=now,
    )
    db.add(transfer)
    db.flush()
    _, inbound = transfer_between_locations(db, item, from_row, to_warehouse, to_inventory_location, quantity, reference_number=transfer.transfer_number, reference_id=transfer.id, notes=notes, created_by=created_by)
    db.add(
        InventoryTransferLine(
            transfer_id=transfer.id,
            inventory_item_id=item.id,
            sku=item.sku,
            barcode=item.barcode,
            description=item.description,
            quantity=to_decimal(quantity),
            from_inventory_item_location_id=from_row.id,
            to_inventory_item_location_id=inbound.item_location.id,
            from_warehouse=from_row.warehouse,
            from_inventory_location=from_row.inventory_location,
            to_warehouse=inbound.item_location.warehouse,
            to_inventory_location=inbound.item_location.inventory_location,
            notes=notes,
        )
    )
    complete_stock_mutation(mutation, {"transfer_id": transfer.id})
    return transfer


def create_committed_transfer_batch(
    db: Session,
    lines: list[dict],
    *,
    notes: str | None = None,
    created_by: str | None = "system",
    idempotency_key: str | None = None,
) -> InventoryTransfer:
    if not lines:
        raise ValueError("At least one transfer line is required.")
    request_payload = {"lines": lines, "notes": notes, "created_by": created_by}
    mutation, replay = begin_stock_mutation(db, "inventory_transfer", idempotency_key, request_payload)
    if replay is not None:
        transfer = db.get(InventoryTransfer, replay["transfer_id"])
        setattr(transfer, "_idempotent_replay", True)
        return transfer
    lock_inventory_stock(db, {payload["item_id"] for payload in lines})
    now = datetime.now(timezone.utc)
    transfer = InventoryTransfer(
        transfer_number=next_transfer_number(db, now),
        status="committed",
        notes=notes,
        created_by=created_by or "system",
        committed_at=now,
    )
    db.add(transfer)
    db.flush()
    first_from = first_to = None
    for payload in lines:
        item = db.get(InventoryItem, payload["item_id"])
        from_row = db.get(InventoryItemLocation, payload["from_inventory_item_location_id"])
        if item is None or from_row is None or from_row.inventory_item_id != item.id:
            raise ValueError("Transfer line item/location is invalid.")
        _, inbound = transfer_between_locations(
            db,
            item,
            from_row,
            payload["to_warehouse"],
            payload["to_inventory_location"],
            payload["quantity"],
            reference_number=transfer.transfer_number,
            reference_id=transfer.id,
            notes=payload.get("notes") or notes,
            created_by=created_by,
        )
        first_from = first_from or from_row
        first_to = first_to or inbound.item_location
        db.add(
            InventoryTransferLine(
                transfer_id=transfer.id,
                inventory_item_id=item.id,
                sku=item.sku,
                barcode=item.barcode,
                description=item.description,
                quantity=to_decimal(payload["quantity"]),
                from_inventory_item_location_id=from_row.id,
                to_inventory_item_location_id=inbound.item_location.id,
                from_warehouse=from_row.warehouse,
                from_inventory_location=from_row.inventory_location,
                to_warehouse=inbound.item_location.warehouse,
                to_inventory_location=inbound.item_location.inventory_location,
                notes=payload.get("notes"),
            )
        )
    if first_from is not None:
        transfer.from_warehouse = first_from.warehouse
        transfer.from_inventory_location = first_from.inventory_location
    if first_to is not None:
        transfer.to_warehouse = first_to.warehouse
        transfer.to_inventory_location = first_to.inventory_location
    complete_stock_mutation(mutation, {"transfer_id": transfer.id})
    return transfer


def create_committed_adjustment(
    db: Session,
    *,
    item: InventoryItem,
    row: InventoryItemLocation,
    quantity_change: Decimal,
    adjustment_type: str,
    reason: str,
    notes: str | None = None,
    created_by: str | None = "system",
    idempotency_key: str | None = None,
) -> StockAdjustment:
    request_payload = {
        "item_id": item.id,
        "inventory_item_location_id": row.id,
        "quantity_change": quantity_change,
        "adjustment_type": adjustment_type,
        "reason": reason,
        "notes": notes,
        "created_by": created_by,
    }
    mutation, replay = begin_stock_mutation(db, "stock_adjustment", idempotency_key, request_payload)
    if replay is not None:
        adjustment = db.get(StockAdjustment, replay["adjustment_id"])
        setattr(adjustment, "_idempotent_replay", True)
        return adjustment
    lock_inventory_stock(db, {item.id})
    now = datetime.now(timezone.utc)
    adjustment = StockAdjustment(
        adjustment_number=next_adjustment_number(db, now),
        status="committed",
        adjustment_type=adjustment_type,
        reason=reason,
        notes=notes,
        created_by=created_by or "system",
        committed_at=now,
    )
    db.add(adjustment)
    db.flush()
    old_quantity = row.in_stock or Decimal("0")
    change = adjust_location_stock(db, item, row, quantity_change, adjustment_type=adjustment_type, reason=reason, reference_number=adjustment.adjustment_number, reference_id=adjustment.id, notes=notes, created_by=created_by)
    db.add(
        StockAdjustmentLine(
            adjustment_id=adjustment.id,
            inventory_item_id=item.id,
            inventory_item_location_id=row.id,
            sku=item.sku,
            barcode=item.barcode,
            description=item.description,
            warehouse=row.warehouse,
            inventory_location=row.inventory_location,
            old_quantity=old_quantity,
            new_quantity=change.new_location_stock,
            quantity_change=to_decimal(quantity_change),
            unit_cost=item.unit_cost,
            notes=notes,
        )
    )
    complete_stock_mutation(mutation, {"adjustment_id": adjustment.id})
    return adjustment


def create_committed_adjustment_batch(
    db: Session,
    lines: list[dict],
    *,
    adjustment_type: str,
    reason: str,
    notes: str | None = None,
    created_by: str | None = "system",
    idempotency_key: str | None = None,
) -> StockAdjustment:
    if not lines:
        raise ValueError("At least one adjustment line is required.")
    request_payload = {
        "lines": lines,
        "adjustment_type": adjustment_type,
        "reason": reason,
        "notes": notes,
        "created_by": created_by,
    }
    mutation, replay = begin_stock_mutation(db, "stock_adjustment", idempotency_key, request_payload)
    if replay is not None:
        adjustment = db.get(StockAdjustment, replay["adjustment_id"])
        setattr(adjustment, "_idempotent_replay", True)
        return adjustment
    lock_inventory_stock(db, {payload["item_id"] for payload in lines})
    now = datetime.now(timezone.utc)
    adjustment = StockAdjustment(
        adjustment_number=next_adjustment_number(db, now),
        status="committed",
        adjustment_type=adjustment_type,
        reason=reason,
        notes=notes,
        created_by=created_by or "system",
        committed_at=now,
    )
    db.add(adjustment)
    db.flush()
    for payload in lines:
        item = db.get(InventoryItem, payload["item_id"])
        row = db.get(InventoryItemLocation, payload["inventory_item_location_id"])
        if item is None or row is None or row.inventory_item_id != item.id:
            raise ValueError("Adjustment line item/location is invalid.")
        old_quantity = row.in_stock or Decimal("0")
        if "expected_quantity" in payload and old_quantity != to_decimal(payload["expected_quantity"]):
            raise StaleStockQuantityError(f"Stock changed after preview for SKU {item.sku or item.id} at {row.warehouse} / {row.inventory_location}.")
        if "new_quantity" in payload:
            new_quantity = to_decimal(payload["new_quantity"])
            if new_quantity < 0:
                raise ValueError("Exact stock quantity cannot be negative.")
            quantity_change = new_quantity - old_quantity
        else:
            quantity_change = to_decimal(payload["quantity_change"])
        change = adjust_location_stock(
            db,
            item,
            row,
            quantity_change,
            adjustment_type=adjustment_type,
            reason=reason,
            reference_number=adjustment.adjustment_number,
            reference_id=adjustment.id,
            notes=payload.get("notes") or notes,
            created_by=created_by,
        )
        db.add(
            StockAdjustmentLine(
                adjustment_id=adjustment.id,
                inventory_item_id=item.id,
                inventory_item_location_id=row.id,
                sku=item.sku,
                barcode=item.barcode,
                description=item.description,
                warehouse=row.warehouse,
                inventory_location=row.inventory_location,
                old_quantity=old_quantity,
                new_quantity=change.new_location_stock,
                quantity_change=quantity_change,
                unit_cost=item.unit_cost,
                notes=payload.get("notes"),
            )
        )
    complete_stock_mutation(mutation, {"adjustment_id": adjustment.id})
    return adjustment
