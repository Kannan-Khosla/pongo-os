from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation, InventoryLocation
from app.services.location_inventory import (
    assert_item_invariants,
    assert_location_invariants,
    create_committed_transfer_batch,
    get_or_create_item_location,
    lock_inventory_stock,
    recalculate_item_location,
    recalculate_item_totals,
)
from app.services.stock_mutation_guard import begin_stock_mutation, complete_stock_mutation


def consolidate_locations(
    db: Session,
    target_location_id: int,
    *,
    actor: str,
    idempotency_key: str,
    apply: bool = False,
) -> dict:
    target_location = db.get(InventoryLocation, target_location_id)
    if target_location is None or not target_location.active:
        raise ValueError("The target inventory location is missing or inactive.")

    items = list(db.scalars(select(InventoryItem).order_by(InventoryItem.id)).all())
    assignments = list(
        db.scalars(
            select(InventoryItemLocation)
            .where(InventoryItemLocation.active.is_(True))
            .order_by(InventoryItemLocation.inventory_item_id, InventoryItemLocation.id)
        ).all()
    )
    sources = [row for row in assignments if row.location_id != target_location.id]
    plan = {
        "target_location_id": target_location.id,
        "target": f"{target_location.warehouse} / {target_location.location_code} / {target_location.location_name}",
        "items": len(items),
        "source_item_locations": len(sources),
        "stock_to_move": _sum(sources, "in_stock"),
        "allocated_outside_target": _sum(sources, "allocated"),
        "on_order_to_move": _sum(sources, "on_order"),
        "physical_locations_to_retire": len(
            [location for location in db.scalars(select(InventoryLocation).where(InventoryLocation.active.is_(True))).all() if location.id != target_location.id]
        ),
    }
    if not apply:
        return _serializable(plan | {"applied": False})
    if plan["allocated_outside_target"]:
        raise ValueError("Allocated stock exists outside the target location. Finish or release those reservations before consolidating.")

    mutation, replay = begin_stock_mutation(
        db,
        "location_consolidation",
        idempotency_key,
        {"target_location_id": target_location.id, "actor": actor},
    )
    if replay is not None:
        return replay

    lock_inventory_stock(db, {item.id for item in items})
    target_location = db.scalar(
        select(InventoryLocation).where(InventoryLocation.id == target_location.id).with_for_update()
    )
    if target_location is None or not target_location.active:
        raise ValueError("The target inventory location changed during consolidation; no changes were committed.")
    locations = list(db.scalars(select(InventoryLocation).order_by(InventoryLocation.id).with_for_update()).all())
    before = {
        item.id: (
            Decimal(item.in_stock or 0),
            Decimal(item.allocated or 0),
            Decimal(item.sellable or 0),
            Decimal(item.on_order or 0),
        )
        for item in items
    }

    target_rows: dict[int, InventoryItemLocation] = {}
    for item in items:
        target_rows[item.id] = get_or_create_item_location(
            db,
            item,
            target_location.warehouse,
            target_location.location_code or target_location.location_name,
            location_id=target_location.id,
            is_default_location=True,
            create_physical_location=False,
        )

    assignments = list(
        db.scalars(
            select(InventoryItemLocation)
            .where(InventoryItemLocation.active.is_(True))
            .order_by(InventoryItemLocation.inventory_item_id, InventoryItemLocation.id)
        ).all()
    )
    sources = [row for row in assignments if row.location_id != target_location.id]
    if _sum(sources, "allocated"):
        raise ValueError("Allocated stock changed during consolidation; no changes were committed.")

    transfer_lines = [
        {
            "item_id": source.inventory_item_id,
            "from_inventory_item_location_id": source.id,
            "to_warehouse": target_location.warehouse,
            "to_inventory_location": target_location.location_code or target_location.location_name,
            "quantity": Decimal(source.in_stock or 0),
            "notes": "Consolidated into the single active Pongo inventory location.",
        }
        for source in sources
        if Decimal(source.in_stock or 0) > 0
    ]
    transfer = None
    if transfer_lines:
        transfer = create_committed_transfer_batch(
            db,
            transfer_lines,
            notes="One-location production consolidation",
            created_by=actor,
            idempotency_key=f"{idempotency_key[:111]}-transfer",
        )

    changed_item_ids: set[int] = set()
    for source in sources:
        target_row = target_rows[source.inventory_item_id]
        on_order = Decimal(source.on_order or 0)
        if on_order:
            source.on_order = Decimal("0")
            target_row.on_order = Decimal(target_row.on_order or 0) + on_order
        source.is_default_location = False
        source.active = False
        recalculate_item_location(source, source.inventory_item)
        recalculate_item_location(target_row, target_row.inventory_item)
        assert_location_invariants(source)
        assert_location_invariants(target_row)
        changed_item_ids.add(source.inventory_item_id)

    for item in items:
        target_row = target_rows[item.id]
        target_row.active = True
        target_row.is_default_location = True
        item = recalculate_item_totals(db, item.id)
        assert_item_invariants(item)
        after = (Decimal(item.in_stock or 0), Decimal(item.allocated or 0), Decimal(item.sellable or 0), Decimal(item.on_order or 0))
        if after != before[item.id]:
            raise ValueError(f"Item {item.sku or item.id} totals changed during consolidation; no changes were committed.")
        if item.id in changed_item_ids:
            db.add(
                InventoryAuditEvent(
                    item_id=item.id,
                    sku=item.sku,
                    barcode=item.barcode,
                    event_type="location_consolidation",
                    quantity_delta=Decimal("0"),
                    previous_in_stock=before[item.id][0],
                    new_in_stock=after[0],
                    previous_allocated=before[item.id][1],
                    new_allocated=after[1],
                    previous_sellable=before[item.id][2],
                    new_sellable=after[2],
                    warehouse=target_location.warehouse,
                    inventory_location=target_location.location_code or target_location.location_name,
                    reference_type="inventory_transfer",
                    reference_id=transfer.id if transfer else None,
                    reference_number=transfer.transfer_number if transfer else None,
                    notes="Moved current balances to Main Warehouse / 001 / Store and retired the old assignment.",
                    created_by=actor,
                )
            )

    target_location.active = True
    target_location.is_default = True
    for location in locations:
        if location.id != target_location.id:
            location.active = False
            location.is_default = False

    result = _serializable(
        plan
        | {
            "applied": True,
            "transfer_id": transfer.id if transfer else None,
            "transfer_number": transfer.transfer_number if transfer else None,
            "active_locations": 1,
        }
    )
    complete_stock_mutation(mutation, result)
    return result


def _sum(rows: list[InventoryItemLocation], attribute: str) -> Decimal:
    return sum((Decimal(getattr(row, attribute) or 0) for row in rows), Decimal("0"))


def _serializable(value: dict) -> dict:
    return {key: str(item) if isinstance(item, Decimal) else item for key, item in value.items()}
