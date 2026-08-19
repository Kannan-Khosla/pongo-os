from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation
from app.models.orders import Order, OrderItem
from app.models.picks import Pick, PickLine
from app.schemas.picks import (
    PickCommitResponse,
    PickDetail,
    PickLineRead,
    PickPreviewLine,
    PickPreviewOrder,
    PickPreviewResponse,
    PickRead,
    PickRequest,
    PickScanRequest,
    PickScanResponse,
    PickScannerLine,
    PickScannerOrder,
)
from app.services.item_identifiers import sku_or_barcode_matches_scan
from app.services.location_inventory import lock_inventory_stock, reduce_pick_from_location, restore_unpick_to_location
from app.services.order_workflow import (
    actionable_order_line_clause,
    add_audit_event,
    allocation_remaining_by_location,
    is_operational_order,
    is_pickable as workflow_order_is_pickable,
    operational_line_identity,
    sync_order_workflow_statuses,
)
from app.services.stock_mutation_guard import IdempotencyConflict, begin_stock_mutation, complete_stock_mutation


def preview_pick(db: Session, payload: PickRequest) -> PickPreviewResponse:
    return build_preview_response(build_preview_orders(db, payload))


def get_scanner_order(db: Session, order_id: int) -> PickScannerOrder | None:
    order = db.scalars(
        select(Order)
        .where(Order.id == order_id, Order.is_historical_snapshot.is_(False))
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
    ).one_or_none()
    if order is None:
        return None
    lines = [scanner_line(line) for line in sorted(order.items, key=lambda row: row.line_number or row.id)]
    return PickScannerOrder(
        order_id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        local_status=order.local_status,
        line_count=len(lines),
        complete_lines=sum(1 for line in lines if line.remaining_to_pick <= 0 and line.allocated_quantity > 0),
        total_allocated_quantity=decimal_to_float(sum((line.quantity_allocated or Decimal("0")) for line in order.items)),
        total_picked_quantity=decimal_to_float(sum((line.quantity_picked or Decimal("0")) for line in order.items)),
        lines=lines,
    )


def preview_scan(db: Session, order_id: int, payload: PickScanRequest) -> PickScanResponse | None:
    line, response = find_scan_line(db, order_id, payload)
    if response is not None:
        return response
    assert line is not None
    preview = preview_pick(db, PickRequest(lines=[{"order_line_id": line.id, "quantity_to_pick": payload.quantity}], allow_partial=True, created_by=payload.created_by, notes=payload.note))
    preview_line = preview.preview_orders[0].lines[0] if preview.preview_orders and preview.preview_orders[0].lines else None
    return PickScanResponse(
        status="valid" if preview_line and not preview_line.errors and preview_line.recommended_pick_quantity > 0 else "rejected",
        matched_line=scanner_line(line),
        proposed_picked_quantity=preview_line.quantity_picked_after if preview_line else None,
        warnings=preview.warnings,
        errors=preview.errors,
    )


def commit_scan(db: Session, order_id: int, payload: PickScanRequest) -> PickScanResponse | None:
    matched_line = None
    if payload.idempotency_key:
        existing_lines = list(
            db.scalars(
                select(PickLine).where(
                    PickLine.order_id == order_id,
                    PickLine.idempotency_key == payload.idempotency_key,
                )
            ).all()
        )
        if existing_lines:
            matched_line = db.get(OrderItem, existing_lines[0].order_line_id)
            expected_quantity = sum((line.quantity_to_pick for line in existing_lines), Decimal("0"))
            if (
                matched_line is None
                or not scan_matches_line(matched_line, payload.sku_or_barcode)
                or to_decimal(payload.quantity) != expected_quantity
            ):
                raise IdempotencyConflict("Idempotency key was already used with a different scan request.")
    if matched_line is None:
        preview = preview_scan(db, order_id, payload)
        if preview is None or preview.status != "valid" or preview.matched_line is None:
            return preview
        matched_line = db.get(OrderItem, preview.matched_line.order_line_id)
    request = PickRequest(
        idempotency_key=payload.idempotency_key,
        lines=[
            {
                "order_line_id": matched_line.id,
                "quantity_to_pick": payload.quantity,
                "idempotency_key": payload.idempotency_key,
            }
        ],
        allow_partial=True,
        created_by=payload.created_by,
        notes=payload.note,
    )
    commit = commit_pick(db, request)
    refreshed = db.get(OrderItem, matched_line.id)
    return PickScanResponse(
        status=commit.status,
        matched_line=scanner_line(refreshed) if refreshed else scanner_line(matched_line),
        proposed_picked_quantity=commit.total_quantity_picked,
        warnings=commit.warnings,
        errors=commit.errors,
        commit=commit,
    )


def commit_pick(db: Session, payload: PickRequest) -> PickCommitResponse:
    mutation, replay = begin_stock_mutation(db, "pick", payload.idempotency_key, payload)
    if replay is not None:
        return PickCommitResponse.model_validate(replay)
    lock_pick_scope(db, payload)
    preview = preview_pick(db, payload)
    blocking_errors = list(preview.errors)
    if not payload.allow_partial:
        for order in preview.preview_orders:
            for line in order.lines:
                if line.pick_status != "picked":
                    blocking_errors.append(f"Order line {line.order_line_id} cannot be fully picked.")
    if blocking_errors:
        return persist_rejected_pick(db, mutation, PickCommitResponse(
            status="rejected",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=blocking_errors,
        ))

    pickable_preview_lines = [line for order in preview.preview_orders for line in order.lines if line.recommended_pick_quantity > 0 and line.pick_status in {"picked", "partial"}]
    if not pickable_preview_lines:
        return persist_rejected_pick(db, mutation, PickCommitResponse(
            status="rejected",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=["No order lines are eligible for picking."],
        ))

    now = datetime.now(timezone.utc)
    first_order = preview.preview_orders[0] if len(preview.preview_orders) == 1 else None
    pick = Pick(
        pick_number=next_pick_number(db, now),
        status="posted",
        pick_type="single_order" if len(preview.preview_orders) == 1 else "batch",
        order_id=first_order.order_id if first_order else None,
        woo_order_id=first_order.woo_order_id if first_order else None,
        woo_order_number=first_order.woo_order_number if first_order else None,
        notes=payload.notes,
        created_by=payload.created_by or "system",
        posted_at=now,
    )
    try:
        db.add(pick)
        db.flush()
        audit_count = 0
        movement_count = 0
        picked_lines = 0
        partial_lines = 0
        touched_order_ids: set[int] = set()
        for preview_line in pickable_preview_lines:
            order_line = db.get(OrderItem, preview_line.order_line_id)
            item = db.get(InventoryItem, preview_line.item_id) if preview_line.item_id else None
            if order_line is None or item is None:
                raise ValueError(f"Order line {preview_line.order_line_id} changed before pick commit.")
            quantity_to_pick = to_decimal(preview_line.recommended_pick_quantity)
            allocated = order_line.quantity_allocated or Decimal("0")
            previously_picked = order_line.quantity_picked or Decimal("0")
            remaining = remaining_to_pick(order_line)
            if quantity_to_pick <= 0 or quantity_to_pick > allocated or quantity_to_pick > remaining:
                raise ValueError(f"Order line {order_line.id} is no longer valid for picking.")
            location_plan = allocate_pick_locations(db, order_line, quantity_to_pick)
            line_idempotency_key = explicit_idempotency_key(payload, order_line.id)
            picked_after = previously_picked
            stock_reduced_after = to_decimal(order_line.quantity_stock_reduced)
            for location_row, segment_quantity in location_plan:
                item = db.get(InventoryItem, order_line.inventory_item_id)
                if item is None:
                    raise ValueError(f"Order line {order_line.id} has no matched item.")
                segment_previously_picked = picked_after
                change, movement = reduce_pick_from_location(
                    db,
                    item,
                    location_row,
                    segment_quantity,
                    reference_number=pick.pick_number,
                    reference_type="pick",
                    reference_id=pick.id,
                    notes=payload.notes,
                    created_by=payload.created_by or "system",
                )
                db.flush()
                picked_after += segment_quantity
                stock_reduced_after += segment_quantity
                remaining_after = max(allocated - picked_after, Decimal("0"))
                pick_line = PickLine(
                    pick_id=pick.id,
                    order_id=order_line.order_id,
                    order_line_id=order_line.id,
                    item_id=item.id,
                    inventory_item_location_id=location_row.id,
                    sku=operational_line_identity(order_line)[0],
                    barcode=operational_line_identity(order_line)[1],
                    description=operational_line_identity(order_line)[2],
                    warehouse=location_row.warehouse,
                    inventory_location=location_row.inventory_location,
                    quantity_ordered=order_line.quantity_ordered or Decimal("0"),
                    quantity_allocated=allocated,
                    quantity_previously_picked=segment_previously_picked,
                    quantity_to_pick=segment_quantity,
                    quantity_picked_after=picked_after,
                    remaining_to_pick=remaining_after,
                    quantity_stock_reduced=segment_quantity,
                    stock_movement_id=movement.id,
                    stock_reduced_at=now,
                    idempotency_key=line_idempotency_key,
                    status="picked" if remaining_after == 0 else "partial",
                    notes=payload.notes,
                )
                db.add(pick_line)
                add_audit_event(
                    db,
                    change.item,
                    change.item_location,
                    "pick_stock_reduction",
                    -segment_quantity,
                    previous_in_stock=change.old_item_stock,
                    new_in_stock=change.new_item_stock,
                    previous_allocated=change.old_item_allocated,
                    new_allocated=change.new_item_allocated,
                    previous_sellable=change.old_item_stock - change.old_item_allocated,
                    new_sellable=(change.item.sellable or Decimal("0")),
                    reference_type="pick",
                    reference_id=pick.id,
                    reference_number=pick.pick_number,
                    notes=payload.notes,
                    created_by=payload.created_by or "system",
                )
                audit_count += 1
                movement_count += 1
            remaining_after = max(allocated - picked_after, Decimal("0"))
            order_line.quantity_picked = picked_after
            order_line.picked_qty = picked_after
            order_line.quantity_stock_reduced = stock_reduced_after
            order_line.stock_reduced_at = now
            order_line.pick_status = "picked" if remaining_after == 0 else "partially_picked"
            order_line.status = "picked" if remaining_after == 0 else "partial"
            picked_lines += 1
            partial_lines += 1 if remaining_after > 0 else 0
            touched_order_ids.add(order_line.order_id)

        db.flush()
        for order_id in touched_order_ids:
            order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items))).one()
            update_order_picking_status(order)
        db.flush()
        response = PickCommitResponse(
            pick_id=pick.id,
            pick_number=pick.pick_number,
            status=pick.status,
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=picked_lines,
            partial_lines=partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=decimal_to_float(sum((line.quantity_to_pick for line in pick.lines), Decimal("0"))),
            created_stock_movements=movement_count,
            created_audit_events=audit_count,
            warnings=preview.warnings,
            errors=[],
        )
        complete_stock_mutation(mutation, response)
        db.commit()
        return response
    except Exception as exc:
        db.rollback()
        return PickCommitResponse(
            status="error",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=[str(exc)],
        )


def unpick_orders(
    db: Session,
    order_ids: list[int],
    *,
    created_by: str | None = "system",
    reason: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    selected_ids = list(dict.fromkeys(order_ids))
    notes = (reason or "Bulk unpick from order workflow.").strip()
    mutation, replay = begin_stock_mutation(
        db,
        "unpick",
        idempotency_key,
        {"order_ids": selected_ids, "created_by": created_by, "reason": notes},
    )
    if replay is not None:
        return replay
    item_ids = set(
        db.scalars(
            select(PickLine.item_id).where(
                PickLine.order_id.in_(selected_ids),
                PickLine.status != "reversed",
                PickLine.quantity_stock_reduced > 0,
            )
        ).all()
    )
    lock_inventory_stock(db, item_ids)
    db.scalars(
        select(OrderItem)
        .where(OrderItem.order_id.in_(selected_ids))
        .order_by(OrderItem.order_id, OrderItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    orders = list(
        db.scalars(
            select(Order)
            .where(Order.id.in_(selected_ids))
            .options(selectinload(Order.items))
            .order_by(Order.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    orders_by_id = {order.id: order for order in orders}
    errors = [f"Order {order_id} was not found." for order_id in selected_ids if order_id not in orders_by_id]
    for order in orders:
        if not is_operational_order(order):
            errors.append(f"Order {order.woo_order_number or order.id} is not an active processing order and cannot be unpicked.")
        if order.completed_at or order.closed_at or order.completion_status in {"completed", "closed"}:
            errors.append(f"Order {order.woo_order_number or order.id} is completed and cannot be unpicked.")
        if any(to_decimal(line.quantity_fulfilled) > 0 for line in order.items):
            errors.append(f"Order {order.woo_order_number or order.id} has fulfilled quantities and cannot be unpicked.")

    pick_lines = list(
        db.scalars(
            select(PickLine)
            .where(PickLine.order_id.in_(selected_ids), PickLine.status != "reversed", PickLine.quantity_stock_reduced > 0)
            .options(selectinload(PickLine.pick))
            .order_by(PickLine.id.desc())
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    lines_by_order: dict[int, list[PickLine]] = {}
    for pick_line in pick_lines:
        lines_by_order.setdefault(pick_line.order_id, []).append(pick_line)
    for order_id in selected_ids:
        if order_id in orders_by_id and not lines_by_order.get(order_id):
            errors.append(f"Order {orders_by_id[order_id].woo_order_number or order_id} has no reversible picked quantity.")

    reversal_plan: list[tuple[PickLine, OrderItem, InventoryItem, InventoryItemLocation, Decimal]] = []
    for pick_line in pick_lines:
        order_line = db.get(OrderItem, pick_line.order_line_id)
        item = db.get(InventoryItem, pick_line.item_id)
        location_row = db.get(InventoryItemLocation, pick_line.inventory_item_location_id) if pick_line.inventory_item_location_id else None
        quantity = to_decimal(pick_line.quantity_stock_reduced)
        if order_line is None or item is None or location_row is None:
            errors.append(f"Pick line {pick_line.id} is missing its original item or location and cannot be reversed.")
            continue
        if to_decimal(order_line.quantity_picked) < quantity or to_decimal(order_line.quantity_stock_reduced) < quantity:
            errors.append(f"Pick line {pick_line.id} exceeds the order line's current picked quantity.")
            continue
        reversal_plan.append((pick_line, order_line, item, location_row, quantity))

    if errors:
        response = {
            "status": "rejected",
            "requested_count": len(selected_ids),
            "succeeded_count": 0,
            "failed_count": len(selected_ids),
            "results": [],
            "errors": errors,
        }
        complete_stock_mutation(mutation, response)
        if mutation is not None:
            db.commit()
        return response

    now = datetime.now(timezone.utc)
    restored_by_order = {order_id: Decimal("0") for order_id in selected_ids}
    touched_picks: dict[int, Pick] = {}
    movement_count = 0
    audit_count = 0
    try:
        for pick_line, order_line, item, location_row, quantity in reversal_plan:
            change, _ = restore_unpick_to_location(
                db,
                item,
                location_row,
                quantity,
                reference_number=pick_line.pick.pick_number,
                reference_id=pick_line.pick_id,
                notes=notes,
                created_by=created_by,
            )
            add_audit_event(
                db,
                change.item,
                change.item_location,
                "unpick_stock_restoration",
                quantity,
                previous_in_stock=change.old_item_stock,
                new_in_stock=change.new_item_stock,
                previous_allocated=change.old_item_allocated,
                new_allocated=change.new_item_allocated,
                previous_sellable=change.old_item_stock - change.old_item_allocated,
                new_sellable=change.item.sellable or Decimal("0"),
                reference_type="unpick",
                reference_id=pick_line.pick_id,
                reference_number=pick_line.pick.pick_number,
                notes=notes,
                created_by=created_by or "system",
            )
            order_line.quantity_picked = to_decimal(order_line.quantity_picked) - quantity
            order_line.picked_qty = order_line.quantity_picked
            order_line.quantity_stock_reduced = to_decimal(order_line.quantity_stock_reduced) - quantity
            if order_line.quantity_stock_reduced == 0:
                order_line.stock_reduced_at = None
            pick_line.status = "reversed"
            pick_line.notes = f"{pick_line.notes + ' ' if pick_line.notes else ''}Reversed: {notes}".strip()
            restored_by_order[pick_line.order_id] += quantity
            touched_picks[pick_line.pick_id] = pick_line.pick
            movement_count += 1
            audit_count += 1

        db.flush()
        for pick in touched_picks.values():
            remaining_lines = db.scalars(select(PickLine).where(PickLine.pick_id == pick.id, PickLine.status != "reversed")).first()
            if remaining_lines is None:
                pick.status = "reversed"
                pick.cancelled_at = now
        for order in orders:
            sync_order_workflow_statuses(order)
    except Exception:
        db.rollback()
        raise

    results = [
        {
            "order_id": order_id,
            "status": "unpicked",
            "message": f"Restored {decimal_to_float(restored_by_order[order_id])} unit(s) to stock and allocation.",
        }
        for order_id in selected_ids
    ]
    response = {
        "status": "completed",
        "requested_count": len(selected_ids),
        "succeeded_count": len(selected_ids),
        "failed_count": 0,
        "total_quantity_restored": decimal_to_float(sum(restored_by_order.values(), Decimal("0"))),
        "created_stock_movements": movement_count,
        "created_audit_events": audit_count,
        "results": results,
        "errors": [],
    }
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def build_preview_orders(db: Session, payload: PickRequest) -> list[PickPreviewOrder]:
    order_lines = selected_order_lines(db, payload)
    orders_by_id: dict[int, list[OrderItem]] = {}
    for line in order_lines:
        orders_by_id.setdefault(line.order_id, []).append(line)
    preview_orders: list[PickPreviewOrder] = []
    for order_id, lines in orders_by_id.items():
        order = lines[0].order
        preview_lines = [build_preview_line(line, explicit_quantity(payload, line.id)) for line in lines]
        errors = []
        if not order_is_pickable(order):
            errors.append(f"Order status {order.local_status or 'unknown'} is not eligible for picking.")
        line_count = len(preview_lines)
        pickable_lines = sum(1 for line in preview_lines if line.pick_status == "picked")
        partial_lines = sum(1 for line in preview_lines if line.pick_status == "partial")
        skipped_lines = sum(1 for line in preview_lines if line.pick_status == "skipped")
        conflict_lines = sum(1 for line in preview_lines if line.pick_status == "conflict")
        recommended_status = "picked" if line_count and pickable_lines == line_count else ("partially_picked" if pickable_lines or partial_lines else order.local_status or "allocated")
        preview_orders.append(
            PickPreviewOrder(
                order_id=order.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                local_status=order.local_status,
                line_count=line_count,
                pickable_lines=pickable_lines,
                partial_lines=partial_lines,
                skipped_lines=skipped_lines,
                conflict_lines=conflict_lines,
                recommended_status=recommended_status,
                warnings=[],
                errors=errors + [error for line in preview_lines for error in line.errors],
                lines=preview_lines,
            )
        )
    return preview_orders


def selected_order_lines(db: Session, payload: PickRequest) -> list[OrderItem]:
    if payload.lines:
        ids = [line.order_line_id for line in payload.lines]
        return list(db.scalars(select(OrderItem).where(OrderItem.id.in_(ids)).options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))).all())
    if payload.order_ids:
        return list(
            db.scalars(
                select(OrderItem)
                .join(Order)
                .where(Order.id.in_(payload.order_ids), actionable_order_line_clause())
                .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
                .order_by(OrderItem.order_id.asc(), OrderItem.line_number.asc().nullslast(), OrderItem.id.asc())
            ).all()
        )
    return [] 


def lock_pick_scope(db: Session, payload: PickRequest) -> None:
    lines = selected_order_lines(db, payload)
    expected_item_ids = {line.id: line.inventory_item_id for line in lines}
    lock_inventory_stock(
        db,
        {line.inventory_item_id for line in lines if line.inventory_item_id is not None},
    )
    order_ids = sorted({line.order_id for line in lines})
    line_ids = sorted({line.id for line in lines})
    if order_ids:
        db.scalars(
            select(Order)
            .where(Order.id.in_(order_ids))
            .order_by(Order.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    if line_ids:
        locked_lines = list(db.scalars(
            select(OrderItem)
            .where(OrderItem.id.in_(line_ids))
            .order_by(OrderItem.order_id, OrderItem.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all())
        if any(line.inventory_item_id != expected_item_ids.get(line.id) for line in locked_lines):
            raise ValueError("Order line inventory mapping changed while the pick was starting; refresh and retry.")


def persist_rejected_pick(db: Session, mutation, response: PickCommitResponse) -> PickCommitResponse:
    complete_stock_mutation(mutation, response)
    if mutation is not None:
        db.commit()
    return response


def find_scan_line(db: Session, order_id: int, payload: PickScanRequest) -> tuple[OrderItem | None, PickScanResponse | None]:
    query = (payload.sku_or_barcode or "").strip()
    if not query:
        return None, PickScanResponse(status="rejected", errors=["Scan value is required."])
    if payload.quantity <= 0:
        return None, PickScanResponse(status="rejected", errors=["Quantity must be greater than zero."])
    order = db.scalars(
        select(Order)
        .where(Order.id == order_id, Order.is_historical_snapshot.is_(False))
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
    ).one_or_none()
    if order is None:
        return None, None
    matches = [line for line in order.items if scan_matches_line(line, query)]
    if not matches:
        return None, PickScanResponse(status="not_found", errors=["Scanned SKU/barcode is not in this order."])
    if len(matches) > 1:
        return None, PickScanResponse(status="rejected", errors=["Scan matches multiple order lines; choose the item line manually."])
    line = matches[0]
    if line.matched_status != "matched":
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), errors=["Matched order line is not linked to a local item."])
    remaining = remaining_to_pick(line)
    if remaining <= 0:
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), warnings=["This item is already fully picked."])
    if to_decimal(payload.quantity) > remaining:
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), errors=["Scanned quantity exceeds remaining quantity to pick."])
    if to_decimal(payload.quantity) > total_allocated_location_remaining(db, line):
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), errors=["Scanned quantity exceeds remaining allocated location stock."])
    return line, None


def scan_matches_line(line: OrderItem, query: str) -> bool:
    sku, barcode, _ = operational_line_identity(line)
    return sku_or_barcode_matches_scan(sku, barcode, query)


def scanner_line(line: OrderItem) -> PickScannerLine:
    item = line.inventory_item
    allocated = line.quantity_allocated or Decimal("0")
    picked = line.quantity_picked or Decimal("0")
    remaining = remaining_to_pick(line)
    item_location_id = None
    warehouse = item.warehouse if item else None
    inventory_location = item.inventory_location if item else None
    warnings = []
    if line.matched_status != "matched":
        warnings.append(f"Line match status is {line.matched_status or 'unknown'}.")
    if allocated <= 0:
        warnings.append("Line has no allocated quantity.")
    if item is not None and remaining > 0:
        try:
            db = object_session(line)
            if db is not None:
                location_rows = allocation_remaining_by_location(db, line)
                if location_rows:
                    location_row = location_rows[0][0]
                    item_location_id = location_row.id
                    warehouse = location_row.warehouse
                    inventory_location = location_row.inventory_location
        except Exception as exc:
            warnings.append(str(exc))
    return PickScannerLine(
        order_line_id=line.id,
        item_id=line.inventory_item_id,
        inventory_item_location_id=item_location_id,
        sku=operational_line_identity(line)[0],
        barcode=operational_line_identity(line)[1],
        description=operational_line_identity(line)[2],
        ordered_quantity=decimal_to_float(line.quantity_ordered),
        allocated_quantity=decimal_to_float(allocated),
        picked_quantity=decimal_to_float(picked),
        remaining_to_pick=decimal_to_float(remaining),
        warehouse=warehouse,
        inventory_location=inventory_location,
        status="picked" if remaining <= 0 and allocated > 0 else ("partial" if picked > 0 else "pending"),
        warnings=warnings,
    )


def explicit_quantity(payload: PickRequest, order_line_id: int) -> Decimal | None:
    for line in payload.lines:
        if line.order_line_id == order_line_id:
            return to_decimal(line.quantity_to_pick)
    return None


def build_preview_line(line: OrderItem, requested_quantity: Decimal | None = None) -> PickPreviewLine:
    warnings: list[str] = []
    errors: list[str] = []
    item = line.inventory_item
    ordered = line.quantity_ordered or Decimal("0")
    allocated = line.quantity_allocated or Decimal("0")
    previously_picked = line.quantity_picked or Decimal("0")
    remaining = max(allocated - previously_picked, Decimal("0"))
    recommended = Decimal("0")
    status = "skipped"
    item_location_id = None
    warehouse = item.warehouse if item else None
    inventory_location = item.inventory_location if item else None
    if line.matched_status != "matched":
        status = "conflict" if line.matched_status == "conflict" else "skipped"
        errors.append(f"Order line matched status is {line.matched_status or 'unknown'}.")
    elif not order_is_pickable(line.order):
        errors.append(f"Order status {line.order.local_status or 'unknown'} is not eligible.")
    elif item is None:
        errors.append("Order line has no matched local item.")
    elif allocated <= 0:
        warnings.append("Order line has no allocated quantity to pick.")
    elif previously_picked > allocated:
        status = "error"
        errors.append("Order line picked quantity exceeds allocated quantity.")
    elif remaining <= 0:
        warnings.append("Order line is already fully picked.")
    else:
        try:
            db = object_session(line)
            if db is None:
                raise ValueError("Order line is not attached to a database session.")
            location_rows = allocation_remaining_by_location(db, line)
            if not location_rows:
                raise ValueError("Order line has no remaining allocated location stock.")
            available_by_location = sum((quantity for _, quantity in location_rows), Decimal("0"))
            if (requested_quantity or remaining) > available_by_location:
                raise ValueError("Requested pick quantity exceeds remaining allocated location stock.")
            location_row = location_rows[0][0]
            item_location_id = location_row.id
            warehouse = location_row.warehouse
            inventory_location = location_row.inventory_location
        except Exception as exc:
            errors.append(str(exc))
        recommended = Decimal("0") if errors else remaining
        if requested_quantity is not None and not errors:
            if requested_quantity <= 0:
                errors.append("Requested pick quantity must be greater than zero.")
                recommended = Decimal("0")
            elif requested_quantity > allocated:
                errors.append("Requested pick quantity exceeds allocated quantity.")
                recommended = Decimal("0")
            elif requested_quantity > remaining:
                errors.append("Requested pick quantity exceeds remaining quantity to pick.")
                recommended = Decimal("0")
            else:
                recommended = requested_quantity
        status = "picked" if recommended == remaining and recommended > 0 else ("partial" if recommended > 0 else status)
    picked_after = previously_picked + recommended
    remaining_after = max(allocated - picked_after, Decimal("0"))
    return PickPreviewLine(
        order_id=line.order_id,
        order_line_id=line.id,
        item_id=item.id if item else None,
        inventory_item_location_id=item_location_id,
        sku=operational_line_identity(line)[0],
        barcode=operational_line_identity(line)[1],
        description=operational_line_identity(line)[2],
        warehouse=warehouse,
        inventory_location=inventory_location,
        quantity_ordered=decimal_to_float(ordered),
        quantity_allocated=decimal_to_float(allocated),
        quantity_previously_picked=decimal_to_float(previously_picked),
        remaining_to_pick=decimal_to_float(remaining),
        recommended_pick_quantity=decimal_to_float(recommended),
        quantity_picked_after=decimal_to_float(picked_after),
        pick_status=status,
        warnings=warnings,
        errors=errors,
    )


def build_preview_response(orders: list[PickPreviewOrder]) -> PickPreviewResponse:
    lines = [line for order in orders for line in order.lines]
    return PickPreviewResponse(
        total_orders=len(orders),
        total_lines=len(lines),
        pickable_lines=sum(1 for line in lines if line.pick_status == "picked"),
        partial_lines=sum(1 for line in lines if line.pick_status == "partial"),
        skipped_lines=sum(1 for line in lines if line.pick_status == "skipped"),
        conflict_lines=sum(1 for line in lines if line.pick_status == "conflict"),
        total_quantity_to_pick=decimal_to_float(sum((to_decimal(line.recommended_pick_quantity) for line in lines), Decimal("0"))),
        warnings=[warning for order in orders for warning in order.warnings] + [warning for line in lines for warning in line.warnings],
        errors=[error for order in orders for error in order.errors] + [error for line in lines for error in line.errors],
        preview_orders=orders,
    )


def update_order_picking_status(order: Order) -> None:
    sync_order_workflow_statuses(order)


def list_picks(
    db: Session,
    status: str | None = None,
    pick_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
):
    statement = build_picks_statement(
        status=status,
        pick_type=pick_type,
        order_id=order_id,
        woo_order_id=woo_order_id,
        woo_order_number=woo_order_number,
        date_from=date_from,
        date_to=date_to,
        created_by=created_by,
    )
    return list(db.scalars(statement.options(selectinload(Pick.lines)).order_by(Pick.created_at.desc(), Pick.id.desc())).all())


def list_picks_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    clamp_page: bool = True,
    status: str | None = None,
    pick_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
) -> tuple[list[Pick], int, int, int]:
    statement = build_picks_statement(
        status=status,
        pick_type=pick_type,
        order_id=order_id,
        woo_order_id=woo_order_id,
        woo_order_number=woo_order_number,
        date_from=date_from,
        date_to=date_to,
        created_by=created_by,
    )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    total_pages = (total + page_size - 1) // page_size
    effective_page = min(page, max(total_pages, 1)) if clamp_page else page
    rows = list(
        db.scalars(
            statement
            .options(selectinload(Pick.lines))
            .order_by(Pick.created_at.desc(), Pick.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total, effective_page, total_pages


def build_picks_statement(
    *,
    status: str | None = None,
    pick_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
):
    statement = select(Pick)
    if status:
        statement = statement.where(Pick.status == status)
    if pick_type:
        statement = statement.where(Pick.pick_type == pick_type)
    if order_id is not None:
        statement = statement.where(Pick.order_id == order_id)
    if woo_order_id is not None:
        statement = statement.where(Pick.woo_order_id == woo_order_id)
    if woo_order_number:
        statement = statement.where(Pick.woo_order_number == woo_order_number)
    if date_from:
        statement = statement.where(Pick.created_at >= date_from)
    if date_to:
        statement = statement.where(Pick.created_at <= date_to)
    if created_by:
        statement = statement.where(Pick.created_by == created_by)
    return statement


def get_pick_detail(db: Session, pick_id: int) -> PickDetail | None:
    pick = db.scalars(select(Pick).where(Pick.id == pick_id).options(selectinload(Pick.lines))).one_or_none()
    if pick is None:
        return None
    audit_ids = list(db.scalars(select(InventoryAuditEvent.id).where(InventoryAuditEvent.reference_type == "pick", InventoryAuditEvent.reference_id == pick.id)).all())
    base = pick_to_read(pick).model_dump()
    base["notes"] = pick.notes
    base["lines"] = [pick_line_to_read(line) for line in sorted(pick.lines, key=lambda row: row.id)]
    base["audit_event_ids"] = audit_ids
    return PickDetail.model_validate(base)


def export_pick_csv(db: Session, pick_id: int) -> str | None:
    detail = get_pick_detail(db, pick_id)
    if detail is None:
        return None
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Pick Number",
            "Status",
            "Created At",
            "Posted At",
            "Woo Order Number",
            "Order ID",
            "SKU",
            "Barcode",
            "Description",
            "Warehouse",
            "Inventory Location",
            "Quantity Ordered",
            "Quantity Allocated",
            "Previously Picked",
            "Quantity Picked",
            "Picked After",
            "Remaining To Pick",
            "Line Status",
            "Notes",
        ]
    )
    for line in detail.lines:
        writer.writerow(
            [
                detail.pick_number,
                detail.status,
                detail.created_at.isoformat() if detail.created_at else "",
                detail.posted_at.isoformat() if detail.posted_at else "",
                detail.woo_order_number or "",
                line.order_id,
                line.sku or "",
                line.barcode or "",
                line.description or "",
                line.warehouse or "",
                line.inventory_location or "",
                line.quantity_ordered,
                line.quantity_allocated,
                line.quantity_previously_picked,
                line.quantity_to_pick,
                line.quantity_picked_after,
                line.remaining_to_pick,
                line.status,
                line.notes or "",
            ]
        )
    return output.getvalue()


def pick_to_read(pick: Pick) -> PickRead:
    return PickRead(
        id=pick.id,
        pick_number=pick.pick_number,
        status=pick.status,
        pick_type=pick.pick_type,
        order_id=pick.order_id,
        woo_order_id=pick.woo_order_id,
        woo_order_number=pick.woo_order_number,
        total_lines=len(pick.lines),
        total_quantity_picked=decimal_to_float(sum((line.quantity_to_pick for line in pick.lines), Decimal("0"))),
        created_by=pick.created_by,
        created_at=pick.created_at,
        posted_at=pick.posted_at,
    )


def pick_line_to_read(line: PickLine) -> PickLineRead:
    return PickLineRead(
        id=line.id,
        order_id=line.order_id,
        order_line_id=line.order_line_id,
        item_id=line.item_id,
        inventory_item_location_id=line.inventory_item_location_id,
        sku=line.sku,
        barcode=line.barcode,
        description=line.description,
        warehouse=line.warehouse,
        inventory_location=line.inventory_location,
        quantity_ordered=decimal_to_float(line.quantity_ordered),
        quantity_allocated=decimal_to_float(line.quantity_allocated),
        quantity_previously_picked=decimal_to_float(line.quantity_previously_picked),
        quantity_to_pick=decimal_to_float(line.quantity_to_pick),
        quantity_picked_after=decimal_to_float(line.quantity_picked_after),
        remaining_to_pick=decimal_to_float(line.remaining_to_pick),
        quantity_stock_reduced=decimal_to_float(line.quantity_stock_reduced),
        stock_movement_id=line.stock_movement_id,
        stock_reduced_at=line.stock_reduced_at,
        idempotency_key=line.idempotency_key,
        status=line.status,
        notes=line.notes,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def next_pick_number(db: Session, now: datetime) -> str:
    prefix = f"PK-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(Pick.id)).where(Pick.pick_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def remaining_to_pick(line: OrderItem) -> Decimal:
    return max((line.quantity_allocated or Decimal("0")) - (line.quantity_picked or Decimal("0")), Decimal("0"))


def current_sellable(item: InventoryItem) -> Decimal:
    return (item.in_stock or Decimal("0")) - (item.allocated or Decimal("0"))


def order_is_pickable(order: Order) -> bool:
    return workflow_order_is_pickable(order)


def allocate_pick_locations(db: Session, line: OrderItem, quantity: Decimal) -> list[tuple]:
    remaining = to_decimal(quantity)
    plan: list[tuple] = []
    for row, available in allocation_remaining_by_location(db, line):
        if remaining <= 0:
            break
        segment = min(available, remaining)
        if segment > 0:
            plan.append((row, segment))
            remaining -= segment
    if remaining > 0:
        raise ValueError("Order line does not have enough remaining allocated location stock.")
    return plan


def total_allocated_location_remaining(db: Session, line: OrderItem) -> Decimal:
    return sum((quantity for _, quantity in allocation_remaining_by_location(db, line)), Decimal("0"))


def explicit_idempotency_key(payload: PickRequest, order_line_id: int) -> str | None:
    for line in payload.lines:
        if line.order_line_id == order_line_id:
            return line.idempotency_key
    return None


def to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)
