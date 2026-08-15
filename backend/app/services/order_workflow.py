from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session, defer, selectinload

from app.models.allocations import Allocation, AllocationLine
from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation
from app.models.orders import Order, OrderItem
from app.models.picks import PickLine
from app.services.location_inventory import (
    assert_item_invariants,
    assert_location_invariants,
    lock_inventory_stock,
    recalculate_item_location,
    recalculate_item_totals,
)

ACTIVE_LOCAL_STATUSES = {"open", "allocated", "partially_allocated", "partially_picked", "picked", None}
COMPLETED_LOCAL_STATUSES = {"completed", "closed", "fulfilled", "partially_fulfilled", "archived"}
BLOCKING_MATCH_STATUSES = {"unmatched", "conflict"}
BLOCKING_ALLOCATION_EXCEPTION_REASONS = {"woo_quantity_below_allocated"}
POSTGRES_FIFO_ALLOCATION_LOCK_KEY = int.from_bytes(b"PONGOFIF", byteorder="big")
POS_PAYMENT_METHOD_PREFIX = "foosales"


def is_pos_order(order: Order) -> bool:
    return (order.payment_method or "").strip().casefold().startswith(POS_PAYMENT_METHOD_PREFIX)


def is_operational_order(order: Order) -> bool:
    return not order.is_historical_snapshot and is_active_order(order) and (
        order.woo_status == "processing" or (order.woo_status == "completed" and is_pos_order(order))
    )


def operational_order_clause():
    return and_(
        Order.is_historical_snapshot.is_(False),
        or_(
            Order.woo_status == "processing",
            and_(
                Order.woo_status == "completed",
                func.lower(func.coalesce(Order.payment_method, "")).like(f"{POS_PAYMENT_METHOD_PREFIX}%"),
            ),
        ),
    )


def actionable_order_line_clause():
    return or_(
        func.coalesce(OrderItem.matched_status, "") != "removed",
        OrderItem.allocation_exception_reason.is_not(None),
        func.coalesce(OrderItem.quantity_ordered, 0) > 0,
        func.coalesce(OrderItem.quantity_allocated, 0) > 0,
        func.coalesce(OrderItem.quantity_picked, 0) > 0,
        func.coalesce(OrderItem.quantity_fulfilled, 0) > 0,
        func.coalesce(OrderItem.quantity_stock_reduced, 0) > 0,
    )


def is_actionable_order_line(line: OrderItem) -> bool:
    return (
        line.matched_status != "removed"
        or line.allocation_exception_reason is not None
        or any(
            to_decimal(quantity) > 0
            for quantity in (
                line.quantity_ordered,
                line.quantity_allocated,
                line.quantity_picked,
                line.quantity_fulfilled,
                line.quantity_stock_reduced,
            )
        )
    )


@dataclass
class AllocationPlanEntry:
    order_line_id: int
    item_id: int
    inventory_item_location_id: int
    quantity: Decimal
    warehouse: str | None = None
    inventory_location: str | None = None
    sellable_before: Decimal = Decimal("0")


@dataclass
class AllocationEvaluation:
    order_id: int
    can_fully_allocate: bool
    can_partially_allocate: bool
    unmatched_lines: list[dict] = field(default_factory=list)
    conflict_lines: list[dict] = field(default_factory=list)
    shortage_lines: list[dict] = field(default_factory=list)
    unavailable_lines: list[dict] = field(default_factory=list)
    allocation_plan: list[AllocationPlanEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def allocation_exception_count(self) -> int:
        return len(self.unmatched_lines) + len(self.conflict_lines) + len(self.shortage_lines) + len(self.unavailable_lines)

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "can_fully_allocate": self.can_fully_allocate,
            "can_partially_allocate": self.can_partially_allocate,
            "unmatched_lines": self.unmatched_lines,
            "conflict_lines": self.conflict_lines,
            "shortage_lines": self.shortage_lines,
            "unavailable_lines": self.unavailable_lines,
            "allocation_plan": [
                {
                    "order_line_id": entry.order_line_id,
                    "item_id": entry.item_id,
                    "inventory_item_location_id": entry.inventory_item_location_id,
                    "quantity": decimal_to_float(entry.quantity),
                    "warehouse": entry.warehouse,
                    "inventory_location": entry.inventory_location,
                    "sellable_before": decimal_to_float(entry.sellable_before),
                }
                for entry in self.allocation_plan
            ],
            "warnings": self.warnings,
        }


def evaluate_order_allocation(db: Session, order_id: int) -> AllocationEvaluation:
    order = load_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    plan: list[AllocationPlanEntry] = []
    unmatched_lines: list[dict] = []
    conflict_lines: list[dict] = []
    shortage_lines: list[dict] = []
    unavailable_lines: list[dict] = []
    warnings: list[str] = []
    allocation_needed = False
    planned_by_location: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

    for line in sorted(order.items, key=lambda row: row.line_number or row.id):
        if not is_actionable_order_line(line):
            continue
        ordered = to_decimal(line.quantity_ordered)
        allocated = to_decimal(line.quantity_allocated)
        remaining = max(ordered - allocated, Decimal("0"))
        if line.allocation_exception_reason in BLOCKING_ALLOCATION_EXCEPTION_REASONS:
            conflict_lines.append(
                line_reason(
                    line,
                    line.allocation_exception_reason,
                    line.sync_error or "WooCommerce reconciliation requires staff review.",
                )
            )
            line.allocation_status = "exception"
            continue
        if allocated > ordered:
            reason = "woo_quantity_below_allocated"
            conflict_lines.append(
                line_reason(
                    line,
                    reason,
                    "Allocated quantity exceeds the latest WooCommerce order quantity; allocation requires review.",
                )
            )
            line.allocation_status = "exception"
            line.allocation_exception_reason = reason
            continue
        line.allocation_exception_reason = None
        line.allocation_status = "allocated" if ordered > 0 and allocated >= ordered else ("partially_allocated" if allocated > 0 else "unallocated")
        item = line.inventory_item

        if item is not None and item.non_inventory:
            line.allocation_status = "not_required"
            continue
        if line.matched_status == "conflict":
            reason = "conflict"
            conflict_lines.append(line_reason(line, reason, "Order line matches conflicting local items."))
            line.allocation_status = "exception"
            line.allocation_exception_reason = reason
            continue
        if line.matched_status != "matched" or item is None:
            reason = "unmatched"
            unmatched_lines.append(line_reason(line, reason, "Order line is not matched to a local inventory item."))
            line.allocation_status = "exception"
            line.allocation_exception_reason = reason
            continue
        if remaining <= 0:
            continue

        allocation_needed = True
        segments, available = build_location_allocation_segments(db, item, remaining, planned_by_location)
        if not segments:
            reason = "no_location_stock"
            unavailable_lines.append(line_reason(line, reason, "Matched item has no sellable location stock."))
            line.allocation_status = "exception"
            line.allocation_exception_reason = reason
            line.shortage_quantity = remaining
            continue
        if available < remaining:
            shortage = remaining - available
            reason = "shortage"
            shortage_lines.append({**line_reason(line, reason, "Matched item does not have enough sellable stock."), "shortage_quantity": decimal_to_float(shortage), "available_quantity": decimal_to_float(available)})
            line.allocation_status = "partially_allocated" if allocated + available > 0 else "unallocated"
            line.allocation_exception_reason = reason
            line.shortage_quantity = shortage
        for row, quantity in segments:
            planned_by_location[row.id] += quantity
            plan.append(
                AllocationPlanEntry(
                    order_line_id=line.id,
                    item_id=item.id,
                    inventory_item_location_id=row.id,
                    quantity=quantity,
                    warehouse=row.warehouse,
                    inventory_location=row.inventory_location,
                    sellable_before=to_decimal(row.sellable),
                )
            )

    can_fully_allocate = not unmatched_lines and not conflict_lines and not shortage_lines and not unavailable_lines
    if allocation_needed and not plan:
        can_fully_allocate = False
    return AllocationEvaluation(
        order_id=order.id,
        can_fully_allocate=can_fully_allocate,
        can_partially_allocate=bool(plan),
        unmatched_lines=unmatched_lines,
        conflict_lines=conflict_lines,
        shortage_lines=shortage_lines,
        unavailable_lines=unavailable_lines,
        allocation_plan=plan,
        warnings=warnings,
    )


def auto_allocate_order_if_possible(db: Session, order_id: int, source: str = "auto") -> dict:
    order = load_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not is_operational_order(order):
        order.auto_allocation_status = "skipped_inactive"
        sync_order_workflow_statuses(order)
        return {"status": "skipped", "reason": "not_active_processing", "evaluation": None, "allocation_id": None, "allocated_quantity": 0}

    evaluation = evaluate_order_allocation(db, order.id)
    if not evaluation.allocation_plan:
        reason = allocation_exception_reason(evaluation) if not evaluation.can_fully_allocate else None
        any_allocated = any(to_decimal(line.quantity_allocated) > 0 for line in order.items)
        next_status = "partially_allocated" if reason and any_allocated else ("exception" if reason else "not_required")
        if reason and (order.auto_allocation_status != next_status or order.allocation_exception_reason != reason):
            order.workflow_notes = append_note(order.workflow_notes, f"Auto-allocation waiting: {reason}.")
        order.auto_allocation_status = next_status
        order.allocation_exception_reason = reason
        sync_order_workflow_statuses(order)
        return {"status": next_status, "reason": reason, "evaluation": evaluation.as_dict(), "allocation_id": None, "allocated_quantity": 0}

    now = datetime.now(timezone.utc)
    allocation = Allocation(
        allocation_number=next_allocation_number(db, now),
        status="posted",
        allocation_type="single_order",
        order_id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        notes=f"Auto-allocation from {source}",
        created_by=source or "auto",
        auto_allocated=True,
        allocation_source="auto",
        posted_at=now,
    )
    db.add(allocation)
    db.flush()

    plan_by_line: dict[int, list[AllocationPlanEntry]] = defaultdict(list)
    for entry in evaluation.allocation_plan:
        plan_by_line[entry.order_line_id].append(entry)

    audit_count = 0
    allocated_quantity = Decimal("0")
    for line_id, entries in plan_by_line.items():
        order_line = db.get(OrderItem, line_id)
        if order_line is None:
            raise ValueError(f"Order line {line_id} changed before auto-allocation commit.")
        line_allocated_before = to_decimal(order_line.quantity_allocated)
        line_allocated_after = line_allocated_before
        for entry in entries:
            item = db.get(InventoryItem, entry.item_id)
            row = db.get(InventoryItemLocation, entry.inventory_item_location_id)
            if item is None or row is None or row.inventory_item_id != item.id:
                raise ValueError("Auto-allocation location changed before commit.")
            quantity = to_decimal(entry.quantity)
            recalculate_item_location(row, item)
            in_stock_before = to_decimal(item.in_stock)
            item_allocated_before = to_decimal(item.allocated)
            sellable_before = to_decimal(item.sellable)
            location_allocated_before = to_decimal(row.allocated)
            if quantity <= 0 or row.sellable < quantity:
                raise ValueError(f"Order line {order_line.id} is no longer fully allocatable.")
            row.allocated = location_allocated_before + quantity
            recalculate_item_location(row, item)
            assert_location_invariants(row)
            item = recalculate_item_totals(db, item.id)
            assert_item_invariants(item)
            line_allocated_after += quantity
            shortage_after = max(to_decimal(order_line.quantity_ordered) - line_allocated_after, Decimal("0"))
            allocation_line = AllocationLine(
                allocation_id=allocation.id,
                order_id=order.id,
                order_line_id=order_line.id,
                item_id=item.id,
                inventory_item_location_id=row.id,
                sku=order_line.sku or item.sku,
                barcode=order_line.barcode or item.barcode,
                description=order_line.name or order_line.description or item.description,
                warehouse=row.warehouse,
                inventory_location=row.inventory_location,
                quantity_ordered=to_decimal(order_line.quantity_ordered),
                quantity_previously_allocated=line_allocated_after - quantity,
                quantity_to_allocate=quantity,
                quantity_allocated_after=line_allocated_after,
                in_stock_before=in_stock_before,
                allocated_before=item_allocated_before,
                sellable_before=sellable_before,
                allocated_after=to_decimal(item.allocated),
                sellable_after=to_decimal(item.sellable),
                shortage_quantity=shortage_after,
                status="allocated" if shortage_after == 0 else "partial",
                notes=f"Auto-allocation from {source}",
                auto_allocated=True,
                allocation_source="auto",
            )
            db.add(allocation_line)
            add_audit_event(
                db,
                item,
                row,
                "allocate",
                quantity,
                previous_in_stock=in_stock_before,
                new_in_stock=in_stock_before,
                previous_allocated=item_allocated_before,
                new_allocated=to_decimal(item.allocated),
                previous_sellable=sellable_before,
                new_sellable=to_decimal(item.sellable),
                reference_type="allocation",
                reference_id=allocation.id,
                reference_number=allocation.allocation_number,
                notes=f"Auto-allocation from {source}",
                created_by=source or "auto",
            )
            audit_count += 1
            allocated_quantity += quantity

        order_line.quantity_allocated = line_allocated_after
        order_line.allocated_qty = line_allocated_after
        order_line.shortage_quantity = max(to_decimal(order_line.quantity_ordered) - line_allocated_after, Decimal("0"))
        order_line.sellable_snapshot = Decimal("0")
        order_line.availability_status = "allocated" if order_line.shortage_quantity == 0 else "partial"
        order_line.allocation_status = "allocated" if order_line.shortage_quantity == 0 else "partially_allocated"
        order_line.status = order_line.allocation_status

    reason = None if evaluation.can_fully_allocate else allocation_exception_reason(evaluation)
    order.auto_allocation_status = "allocated" if evaluation.can_fully_allocate else "partially_allocated"
    order.allocation_exception_reason = reason
    if reason:
        order.workflow_notes = append_note(order.workflow_notes, f"Auto-allocation reserved available stock; waiting on {reason}.")
    sync_order_workflow_statuses(order)
    db.flush()
    return {
        "status": "allocated" if evaluation.can_fully_allocate else "partially_allocated",
        "reason": reason,
        "evaluation": evaluation.as_dict(),
        "allocation_id": allocation.id,
        "created_audit_events": audit_count,
        "allocated_quantity": decimal_to_float(allocated_quantity),
    }


def auto_allocate_processing_orders_fifo(db: Session, source: str = "fifo-auto-allocation", *, commit: bool = False) -> dict:
    """Reserve available stock for processing orders in oldest-order-first sequence."""
    acquire_fifo_allocation_lock(db)
    orders = list(
        db.scalars(
            select(Order)
            .where(operational_order_clause())
            .options(defer(Order.raw_woo_payload), selectinload(Order.items).selectinload(OrderItem.inventory_item))
            .order_by(Order.date_created.asc().nulls_last(), Order.id.asc())
        ).all()
    )
    lock_inventory_stock(
        db,
        {
            line.inventory_item_id
            for order in orders
            for line in order.items
            if line.inventory_item_id is not None
        },
    )
    summary = {
        "status": "completed",
        "attempted_orders": 0,
        "allocated_orders": 0,
        "partially_allocated_orders": 0,
        "exception_orders": 0,
        "total_quantity_allocated": 0.0,
        "allocation_ids": [],
        "errors": [],
    }
    for order in orders:
        sync_order_workflow_statuses(order)
        if not is_active_order(order) or not allocation_needs_attention(order):
            continue
        summary["attempted_orders"] += 1
        try:
            with db.begin_nested():
                result = auto_allocate_order_if_possible(db, order.id, source=source)
            if result["status"] == "allocated":
                summary["allocated_orders"] += 1
            elif result["status"] == "partially_allocated":
                summary["partially_allocated_orders"] += 1
            elif result["status"] == "exception":
                summary["exception_orders"] += 1
            summary["total_quantity_allocated"] += float(result.get("allocated_quantity") or 0)
            if result.get("allocation_id"):
                summary["allocation_ids"].append(result["allocation_id"])
        except Exception as exc:
            summary["exception_orders"] += 1
            summary["errors"].append(f"Order {order.woo_order_number or order.id}: {exc}")
    if summary["errors"]:
        summary["status"] = "completed_with_errors"
    if commit:
        db.commit()
    else:
        db.flush()
    return summary


def acquire_fifo_allocation_lock(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": POSTGRES_FIFO_ALLOCATION_LOCK_KEY})


def determine_order_workflow_flags(db: Session, order_id: int) -> dict:
    order = load_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    sync_order_workflow_statuses(order)
    return workflow_flags(order)


def workflow_flags(order: Order) -> dict:
    active = is_active_order(order)
    operational = is_operational_order(order)
    can_pick = operational and is_pickable(order)
    return {
        "shows_in_open_orders": operational,
        "shows_in_allocate": operational and allocation_needs_attention(order),
        "shows_in_pick_orders": can_pick,
        "shows_in_completed_orders": not active,
        "can_pick": can_pick,
        "can_complete": active,
        "completed_without_picking": bool(order.completed_without_picking),
    }


def complete_order_without_stock_reduction(db: Session, order_id: int, reason: str | None = None, *, created_by: str = "system") -> dict:
    order = lock_order_completion_scope(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("A reason is required when completing without picking.")
    now = datetime.now(timezone.utc)
    released_quantity = release_unpicked_allocations(db, order, f"Order completed without picking. Stock was not reduced. {reason}", "complete_without_picking", created_by=created_by)
    order.local_status = "completed"
    order.completion_status = "completed_without_picking"
    order.completed_without_picking = True
    order.completed_at = now
    order.closed_at = now
    order.workflow_notes = append_note(order.workflow_notes, f"Order completed without picking. Stock was not reduced. {reason}")
    if not any((line.quantity_picked or Decimal("0")) > 0 for line in order.items):
        order.pick_status = "completed_without_picking"
    add_order_audit_events(db, order, "completed_without_picking", f"Order completed without picking. Stock was not reduced. {reason}", created_by=created_by)
    sync_order_workflow_statuses(order)
    auto_allocate_processing_orders_fifo(db, source="completion-release")
    db.commit()
    db.refresh(order)
    return {"status": "completed_without_picking", "order_id": order.id, "released_quantity": decimal_to_float(released_quantity), "message": "Order completed without picking. Stock was not reduced."}


def complete_picked_order(db: Session, order_id: int, *, created_by: str = "system") -> dict:
    order = lock_order_completion_scope(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    required_lines = [
        line
        for line in order.items
        if not (line.inventory_item and line.inventory_item.non_inventory)
    ]
    if not required_lines:
        raise ValueError("Picked completion requires at least one inventory line.")
    incomplete_lines = [line for line in required_lines if not line_is_fully_picked_and_reduced(line)]
    if incomplete_lines:
        raise ValueError("Picked completion requires every inventory line to be fully picked.")
    now = datetime.now(timezone.utc)
    released_quantity = release_unpicked_allocations(db, order, "Order completed after picking; unpicked allocations released.", "complete_picked_order", created_by=created_by)
    order.local_status = "completed"
    order.completion_status = "completed"
    order.completed_at = now
    order.closed_at = now
    order.workflow_notes = append_note(order.workflow_notes, "Order completed locally. Stock was already reduced during picking.")
    add_order_audit_events(db, order, "complete_picked_order", "Order completed locally. Stock was already reduced during picking.", created_by=created_by)
    sync_order_workflow_statuses(order)
    auto_allocate_processing_orders_fifo(db, source="completion-release")
    db.commit()
    db.refresh(order)
    return {"status": "completed", "order_id": order.id, "released_quantity": decimal_to_float(released_quantity), "message": "Order completed locally. Stock was already reduced during picking."}


def release_line_allocations(
    db: Session,
    order: Order,
    line: OrderItem,
    requested_quantity: Decimal,
    notes: str,
    event_type: str,
    *,
    created_by: str = "system",
) -> Decimal:
    if line.inventory_item_id is not None:
        lock_inventory_stock(db, {line.inventory_item_id})
    unpicked_allocated = max(to_decimal(line.quantity_allocated) - to_decimal(line.quantity_picked), Decimal("0"))
    to_release = min(max(to_decimal(requested_quantity), Decimal("0")), unpicked_allocated)
    requested_release = to_release
    for row, available in allocation_remaining_by_location(db, line, include_inactive=True):
        if to_release <= 0:
            break
        quantity = min(available, to_decimal(row.allocated), to_release)
        if quantity <= 0:
            continue
        item = db.get(InventoryItem, row.inventory_item_id)
        if item is None:
            continue
        previous_in_stock = to_decimal(item.in_stock)
        previous_allocated = to_decimal(item.allocated)
        previous_sellable = to_decimal(item.sellable)
        row.allocated = to_decimal(row.allocated) - quantity
        recalculate_item_location(row, item)
        assert_location_invariants(row)
        item = recalculate_item_totals(db, item.id)
        assert_item_invariants(item)
        add_audit_event(
            db,
            item,
            row,
            "deallocate",
            -quantity,
            previous_in_stock=previous_in_stock,
            new_in_stock=to_decimal(item.in_stock),
            previous_allocated=previous_allocated,
            new_allocated=to_decimal(item.allocated),
            previous_sellable=previous_sellable,
            new_sellable=to_decimal(item.sellable),
            reference_type=event_type,
            reference_id=order.id,
            reference_number=order.woo_order_number or order.order_number,
            notes=notes,
            created_by=created_by,
        )
        to_release -= quantity
    released = requested_release - to_release
    line.quantity_allocated = max(to_decimal(line.quantity_allocated) - released, Decimal("0"))
    line.allocated_qty = line.quantity_allocated
    ordered = to_decimal(line.quantity_ordered)
    line.shortage_quantity = max(ordered - to_decimal(line.quantity_allocated), Decimal("0"))
    line.availability_status = (
        "allocated"
        if ordered > 0 and to_decimal(line.quantity_allocated) >= ordered
        else ("partial" if line.quantity_allocated else "unallocated")
    )
    line.allocation_status = line.availability_status
    return released


def release_unpicked_allocations(db: Session, order: Order, notes: str, event_type: str, *, created_by: str = "system") -> Decimal:
    released_total = Decimal("0")
    for line in order.items:
        released_total += release_line_allocations(
            db,
            order,
            line,
            max(to_decimal(line.quantity_allocated) - to_decimal(line.quantity_picked), Decimal("0")),
            notes,
            event_type,
            created_by=created_by,
        )
    return released_total


def allocation_remaining_by_location(
    db: Session,
    line: OrderItem,
    *,
    include_inactive: bool = False,
) -> list[tuple[InventoryItemLocation, Decimal]]:
    allocated_rows = db.execute(
        select(
            AllocationLine.id,
            AllocationLine.inventory_item_location_id,
            AllocationLine.quantity_to_allocate,
        )
        .join(Allocation, Allocation.id == AllocationLine.allocation_id)
        .where(
            AllocationLine.order_line_id == line.id,
            AllocationLine.inventory_item_location_id.is_not(None),
            Allocation.status == "posted",
        )
        .order_by(AllocationLine.id.asc())
    ).all()
    picked_by_location = dict(
        db.execute(
            select(PickLine.inventory_item_location_id, func.coalesce(func.sum(PickLine.quantity_stock_reduced), 0))
            .where(
                PickLine.order_line_id == line.id,
                PickLine.inventory_item_location_id.is_not(None),
                PickLine.status != "reversed",
            )
            .group_by(PickLine.inventory_item_location_id)
        ).all()
    )
    unpicked_segments: list[tuple[int, Decimal]] = []
    for _, location_id, allocated_quantity in allocated_rows:
        quantity = to_decimal(allocated_quantity)
        picked = min(quantity, to_decimal(picked_by_location.get(location_id)))
        picked_by_location[location_id] = max(to_decimal(picked_by_location.get(location_id)) - picked, Decimal("0"))
        if quantity > picked:
            unpicked_segments.append((location_id, quantity - picked))

    active_unpicked = max(to_decimal(line.quantity_allocated) - to_decimal(line.quantity_picked), Decimal("0"))
    active_by_location: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for location_id, quantity in reversed(unpicked_segments):
        if active_unpicked <= 0:
            break
        active_quantity = min(quantity, active_unpicked)
        active_by_location[location_id] += active_quantity
        active_unpicked -= active_quantity

    remaining: list[tuple[InventoryItemLocation, Decimal]] = []
    for location_id, allocated_quantity in active_by_location.items():
        row = db.get(InventoryItemLocation, location_id)
        if row is None or (not include_inactive and not row.active):
            continue
        quantity = min(to_decimal(allocated_quantity), to_decimal(row.allocated), to_decimal(row.in_stock))
        if quantity > 0:
            remaining.append((row, quantity))
    remaining.sort(key=lambda pair: (not pair[0].is_default_location, -pair[1], pair[0].id))
    return remaining


def sync_order_workflow_statuses(order: Order) -> None:
    lines = [line for line in order.items if is_actionable_order_line(line)]
    matched_lines = [line for line in lines if line.matched_status == "matched" and not (line.inventory_item and line.inventory_item.non_inventory)]
    blocked = [
        line
        for line in lines
        if line.matched_status in BLOCKING_MATCH_STATUSES or line.allocation_exception_reason in BLOCKING_ALLOCATION_EXCEPTION_REASONS
    ]
    any_allocated = any(to_decimal(line.quantity_allocated) > 0 for line in matched_lines)
    all_allocated = bool(matched_lines) and all(to_decimal(line.quantity_allocated) >= to_decimal(line.quantity_ordered) for line in matched_lines)
    any_picked = any(to_decimal(line.quantity_picked) > 0 for line in matched_lines)
    all_picked = bool(matched_lines) and all(line_is_fully_picked_and_reduced(line) for line in matched_lines)

    locally_completed = order.completion_status in {"completed", "completed_without_picking"}
    woo_operational = order.woo_status == "processing" or (order.woo_status == "completed" and is_pos_order(order))
    if order.woo_status and not woo_operational and not locally_completed:
        order.local_status = order.woo_status
        order.completion_status = order.woo_status
        order.allocation_status = "unallocated"
        order.pick_status = "not_ready"
        return
    if woo_operational and not locally_completed and not is_active_order(order):
        # Reconcile stale cached terminal state from an earlier Woo snapshot,
        # then derive the current queue state from line quantities below.
        order.local_status = "open"
        order.completion_status = "open"

    for line in lines:
        ordered = to_decimal(line.quantity_ordered)
        allocated = to_decimal(line.quantity_allocated)
        picked = to_decimal(line.quantity_picked)
        stock_reduced = to_decimal(getattr(line, "quantity_stock_reduced", Decimal("0")))
        if line.matched_status in BLOCKING_MATCH_STATUSES:
            line.allocation_status = "exception"
            line.pick_status = "not_ready"
        elif line.allocation_exception_reason in BLOCKING_ALLOCATION_EXCEPTION_REASONS:
            line.allocation_status = "exception"
            line.pick_status = "picked" if allocated > 0 and picked >= allocated and stock_reduced >= picked else ("partially_picked" if picked > 0 else "not_ready")
        else:
            line.allocation_status = "allocated" if ordered > 0 and allocated >= ordered else ("partially_allocated" if allocated > 0 else "unallocated")
            line.pick_status = "picked" if allocated > 0 and picked >= allocated and stock_reduced >= picked else ("partially_picked" if picked > 0 else ("ready_to_pick" if ordered > 0 and allocated >= ordered else "not_ready"))

    if locally_completed or order.local_status in {"completed", "closed"}:
        order.completion_status = order.completion_status or "completed"
        return

    if blocked:
        order.allocation_status = "exception"
        order.allocation_exception_reason = ", ".join(
            sorted(
                {
                    line.allocation_exception_reason
                    if line.allocation_exception_reason in BLOCKING_ALLOCATION_EXCEPTION_REASONS
                    else (line.matched_status or "unmatched")
                    for line in blocked
                }
            )
        )
    elif all_allocated:
        order.allocation_status = "auto_allocated" if order.auto_allocation_status == "allocated" else "allocated"
        order.allocation_exception_reason = None
    elif any_allocated:
        order.allocation_status = "partially_allocated"
        order.allocation_exception_reason = order.allocation_exception_reason or "partial_stock"
    elif matched_lines:
        order.allocation_status = "unallocated"
    else:
        order.allocation_status = "not_required"

    if blocked:
        order.pick_status = "partially_picked" if any_picked else "not_ready"
    elif all_picked:
        order.pick_status = "picked"
        order.picked_at = order.picked_at or datetime.now(timezone.utc)
    elif any_picked:
        order.pick_status = "partially_picked"
    elif all_allocated:
        order.pick_status = "ready_to_pick"
    else:
        order.pick_status = "not_ready"
    order.completion_status = order.completion_status or "open"

    if order.local_status not in COMPLETED_LOCAL_STATUSES:
        if all_picked:
            order.local_status = "picked"
        elif any_picked:
            order.local_status = "partially_picked"
        elif order.allocation_status in {"allocated", "auto_allocated"}:
            order.local_status = "allocated"
        elif order.allocation_status == "partially_allocated":
            order.local_status = "partially_allocated"
        else:
            order.local_status = "open"


def build_location_allocation_segments(
    db: Session,
    item: InventoryItem,
    needed: Decimal,
    planned_by_location: dict[int, Decimal] | None = None,
) -> tuple[list[tuple[InventoryItemLocation, Decimal]], Decimal]:
    rows = list(
        db.scalars(
            select(InventoryItemLocation)
            .where(InventoryItemLocation.inventory_item_id == item.id, InventoryItemLocation.active.is_(True))
            .order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.sellable.desc(), InventoryItemLocation.id.asc())
        ).all()
    )
    segments: list[tuple[InventoryItemLocation, Decimal]] = []
    remaining = to_decimal(needed)
    available = Decimal("0")
    for row in rows:
        recalculate_item_location(row, item)
        planned = (planned_by_location or {}).get(row.id, Decimal("0"))
        row_sellable = max(to_decimal(row.sellable) - planned, Decimal("0"))
        available += row_sellable
        if remaining > 0 and row_sellable > 0:
            quantity = min(row_sellable, remaining)
            segments.append((row, quantity))
            remaining -= quantity
    return segments, available


def load_order(db: Session, order_id: int) -> Order | None:
    return db.scalars(
        select(Order)
        .where(Order.id == order_id, Order.is_historical_snapshot.is_(False))
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
    ).one_or_none()


def lock_order_completion_scope(db: Session, order_id: int) -> Order | None:
    item_ids = set(
        db.scalars(
            select(OrderItem.inventory_item_id).where(
                OrderItem.order_id == order_id,
                OrderItem.inventory_item_id.is_not(None),
            )
        ).all()
    )
    lock_inventory_stock(db, item_ids)
    order = db.scalars(
        select(Order)
        .where(Order.id == order_id, Order.is_historical_snapshot.is_(False))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if order is None:
        return None
    db.scalars(
        select(OrderItem)
        .where(OrderItem.order_id == order_id)
        .order_by(OrderItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    db.expire(order, ["items"])
    return load_order(db, order_id)


def line_is_fully_picked_and_reduced(line: OrderItem) -> bool:
    ordered = to_decimal(line.quantity_ordered)
    return bool(
        line.matched_status == "matched"
        and ordered > 0
        and to_decimal(line.quantity_picked) >= ordered
        and to_decimal(line.quantity_stock_reduced) >= ordered
    )


def is_active_order(order: Order) -> bool:
    if order.completion_status in {"completed", "completed_without_picking"}:
        return False
    return order.local_status not in COMPLETED_LOCAL_STATUSES and order.local_status not in {"cancelled", "canceled", "failed", "refunded"}


def allocation_needs_attention(order: Order) -> bool:
    if order.allocation_status in {"exception", "partially_allocated", "unallocated"}:
        return True
    return any(
        line.allocation_status == "exception" or to_decimal(line.quantity_allocated) < to_decimal(line.quantity_ordered)
        for line in order.items
        if line.matched_status == "matched" and not (line.inventory_item and line.inventory_item.non_inventory)
    )


def is_pickable(order: Order) -> bool:
    if order.allocation_status not in {"allocated", "auto_allocated"}:
        return False
    required_lines = [
        line
        for line in order.items
        if is_actionable_order_line(line) and not (line.inventory_item and line.inventory_item.non_inventory)
    ]
    if not required_lines:
        return False
    if any(line.matched_status != "matched" or to_decimal(line.quantity_allocated) < to_decimal(line.quantity_ordered) for line in required_lines):
        return False
    if order.pick_status not in {"ready_to_pick", "partially_picked"}:
        return False
    return any(to_decimal(line.quantity_allocated) > to_decimal(line.quantity_picked) for line in required_lines)


def allocation_exception_reason(evaluation: AllocationEvaluation) -> str:
    reasons = []
    if evaluation.unmatched_lines:
        reasons.append("unmatched_line")
    if any(line.get("reason") == "woo_quantity_below_allocated" for line in evaluation.conflict_lines):
        reasons.append("woo_quantity_below_allocated")
    elif evaluation.conflict_lines:
        reasons.append("conflict_line")
    if evaluation.shortage_lines:
        reasons.append("shortage")
    if evaluation.unavailable_lines:
        reasons.append("no_location_stock")
    return ", ".join(reasons) or "allocation_exception"


def add_order_audit_events(db: Session, order: Order, event_type: str, notes: str, *, created_by: str = "system") -> None:
    seen_items: set[int] = set()
    for line in order.items:
        item = line.inventory_item
        if item is None or item.id in seen_items:
            continue
        row = first_item_location(db, item)
        if row is None:
            continue
        seen_items.add(item.id)
        add_audit_event(
            db,
            item,
            row,
            event_type,
            Decimal("0"),
            previous_in_stock=to_decimal(item.in_stock),
            new_in_stock=to_decimal(item.in_stock),
            previous_allocated=to_decimal(item.allocated),
            new_allocated=to_decimal(item.allocated),
            previous_sellable=to_decimal(item.sellable),
            new_sellable=to_decimal(item.sellable),
            reference_type="order",
            reference_id=order.id,
            reference_number=order.woo_order_number or order.order_number,
            notes=notes,
            created_by=created_by,
        )


def add_audit_event(
    db: Session,
    item: InventoryItem,
    row: InventoryItemLocation,
    event_type: str,
    quantity_delta: Decimal,
    *,
    previous_in_stock: Decimal,
    new_in_stock: Decimal,
    previous_allocated: Decimal,
    new_allocated: Decimal,
    previous_sellable: Decimal,
    new_sellable: Decimal,
    reference_type: str | None,
    reference_id: int | None,
    reference_number: str | None,
    notes: str | None,
    created_by: str | None,
) -> None:
    db.add(
        InventoryAuditEvent(
            item_id=item.id,
            sku=item.sku,
            barcode=item.barcode,
            event_type=event_type,
            quantity_delta=quantity_delta,
            previous_in_stock=previous_in_stock,
            new_in_stock=new_in_stock,
            previous_allocated=previous_allocated,
            new_allocated=new_allocated,
            previous_sellable=previous_sellable,
            new_sellable=new_sellable,
            warehouse=row.warehouse,
            inventory_location=row.inventory_location,
            reference_type=reference_type,
            reference_id=reference_id,
            reference_number=reference_number,
            notes=notes,
            created_by=created_by or "system",
        )
    )


def first_item_location(db: Session, item: InventoryItem) -> InventoryItemLocation | None:
    return db.scalars(
        select(InventoryItemLocation)
        .where(InventoryItemLocation.inventory_item_id == item.id, InventoryItemLocation.active.is_(True))
        .order_by(InventoryItemLocation.is_default_location.desc(), InventoryItemLocation.id.asc())
    ).first()


def line_reason(line: OrderItem, reason: str, message: str) -> dict:
    return {
        "order_line_id": line.id,
        "sku": line.sku,
        "barcode": line.barcode,
        "reason": reason,
        "message": message,
    }


def append_note(existing: str | None, note: str) -> str:
    if not existing:
        return note
    return f"{existing}\n{note}"


def next_allocation_number(db: Session, now: datetime) -> str:
    prefix = f"AL-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(Allocation.id)).where(Allocation.allocation_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)
