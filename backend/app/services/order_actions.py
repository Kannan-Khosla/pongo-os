from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.models.picks import PickLine
from app.models.woocommerce import WooWritebackQueue
from app.schemas.orders import (
    CompletedOrderPickRecoveryRequest,
    CompletedOrderPickRecoveryResponse,
    OrderLineAddRequest,
    OrderLineEditResponse,
    OrderLineRemoveRequest,
    OrderSubstitutionRequest,
    OrderSubstitutionResponse,
    WooOrderStatusActionRequest,
    WooOrderStatusActionResponse,
    WooOrderReconcileRequest,
    WooOrderReconcileResponse,
)
from app.services.location_inventory import lock_inventory_stock
from app.services.order_workflow import (
    add_audit_event,
    add_order_audit_events,
    append_note,
    auto_allocate_order_if_possible,
    complete_order_without_stock_reduction,
    complete_picked_order,
    first_item_location,
    is_actionable_order_line,
    is_operational_order,
    line_is_fully_picked_and_reduced,
    lock_order_completion_scope,
    release_line_allocations,
    sync_order_workflow_statuses,
    to_decimal,
)
from app.services.stock_mutation_guard import begin_stock_mutation, complete_stock_mutation
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_orders import RETIRED_WOO_LINE_STATUS, commit_remote_order_records, get_open_order_detail
from app.services.woocommerce_writeback import sync_inventory_stock, sync_order_status, validate_item_mapping


class OrderActionConflict(ValueError):
    pass


def reconcile_live_woo_order(
    db: Session,
    client: WooCommerceClient,
    woo_order_id: int,
    payload: WooOrderReconcileRequest,
    *,
    actor: str,
) -> WooOrderReconcileResponse:
    idempotency_key = required_idempotency_key(payload.idempotency_key)
    mutation_payload = {
        "woo_order_id": woo_order_id,
        "idempotency_key": idempotency_key,
    }
    mutation, replay = begin_stock_mutation(db, "reconcile_live_woo_order", idempotency_key, mutation_payload)
    if replay is not None:
        return WooOrderReconcileResponse.model_validate(replay)
    remote = validate_remote_order(client.get_order(woo_order_id), woo_order_id)
    if str(remote.get("status") or "").strip().casefold() != "processing":
        raise OrderActionConflict("Only a live processing WooCommerce order can be opened for operations.")
    commit_remote_order_records(db, [remote], ["processing"], actor, commit=False)
    order = load_local_order_by_woo(db, woo_order_id)
    detail = get_open_order_detail(db, order.id) if order is not None else None
    if order is None or detail is None:
        raise OrderActionConflict("WooCommerce order could not be reconciled into the local operational store.")
    response = WooOrderReconcileResponse(
        status="reconciled",
        woo_order_id=woo_order_id,
        local_order_id=order.id,
        order=detail,
    )
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def change_live_woo_order_status(
    db: Session,
    settings: Settings,
    client: WooCommerceClient,
    woo_order_id: int,
    payload: WooOrderStatusActionRequest,
    *,
    actor: str,
) -> WooOrderStatusActionResponse:
    reason = required_reason(payload.reason)
    idempotency_key = required_idempotency_key(payload.idempotency_key)
    remote = validate_remote_order(client.get_order(woo_order_id), woo_order_id)
    remote_status = str(remote.get("status") or "").strip().casefold()
    existing_queue = status_queue_for_key(db, idempotency_key)
    if existing_queue is not None:
        validate_status_queue_replay(existing_queue, woo_order_id, payload.target_status, reason)

    if remote_status == payload.target_status:
        if existing_queue is None:
            raise OrderActionConflict(
                f"WooCommerce order {woo_order_id} is already {payload.target_status}; "
                "this action has no matching idempotent writeback record."
            )
        local_order = reconcile_one_remote_order(db, remote, payload.target_status, actor)
        if existing_queue.status != "sent":
            existing_queue.status = "sent"
            existing_queue.sent_at = datetime.now(timezone.utc)
            existing_queue.response_json = remote
            existing_queue.error_message = None
            db.commit()
            db.refresh(existing_queue)
        record_status_action_audit(
            db,
            local_order,
            payload.target_status,
            reason,
            actor,
            idempotency_key,
            existing_queue.status,
        )
        return WooOrderStatusActionResponse(
            status="already_applied",
            target_status=payload.target_status,
            woo_order_id=woo_order_id,
            local_order_id=local_order.id,
            local_status=local_order.local_status,
            released_quantity=0,
            message=f"WooCommerce order is already {payload.target_status}.",
            woo_sync_status=existing_queue.status,
            woo_writeback_queue_id=existing_queue.id,
            woo_sync_error=existing_queue.error_message,
        )
    if remote_status != "processing":
        raise OrderActionConflict(
            f"WooCommerce order {woo_order_id} is {remote_status or 'unknown'}, not processing. "
            "Only a live processing order can be changed here."
        )

    cached_order = load_local_order_by_woo(db, woo_order_id)
    if (
        payload.target_status == "cancelled"
        and existing_queue is not None
        and cached_order is not None
        and cached_order.completion_status == "cancellation_pending"
    ):
        local_order = cached_order
    else:
        local_order = reconcile_one_remote_order(db, remote, "processing", actor)
    released_quantity = Decimal("0")
    stock_sync = None

    if payload.target_status == "completed":
        completion_mode = infer_completion_mode(local_order, payload.completion_mode)
        result = complete_local_order_once(db, local_order.id, completion_mode, reason, actor)
        released_quantity = to_decimal(result.get("released_quantity"))
        if completion_mode == "complete_picked":
            stock_sync = sync_completed_picked_stock(db, settings, client, local_order.id, actor)
    else:
        local_order = begin_cancellation_guard(
            db,
            local_order.id,
            reason=reason,
            actor=actor,
            idempotency_key=idempotency_key,
        )

    writeback = sync_order_status(
        db,
        settings,
        client,
        local_order.id,
        payload.target_status,
        requested_by=actor,
        idempotency_key=idempotency_key,
        action_reason=reason,
    )

    if writeback.status == "sent":
        post_write_remote = writeback.response_json
        if not isinstance(post_write_remote, dict) or "line_items" not in post_write_remote:
            post_write_remote = validate_remote_order(client.get_order(woo_order_id), woo_order_id)
        post_write_remote = validate_remote_order(post_write_remote, woo_order_id)
        if str(post_write_remote.get("status") or "").strip().casefold() != payload.target_status:
            raise WooCommerceClientError(
                f"WooCommerce acknowledged the write but returned status {post_write_remote.get('status') or 'unknown'}."
            )
        before_allocated = total_allocated(local_order)
        local_order = reconcile_one_remote_order(db, post_write_remote, payload.target_status, actor)
        if payload.target_status == "cancelled":
            released_quantity = max(before_allocated - total_allocated(local_order), Decimal("0"))
        action_status = payload.target_status
        message = f"Order changed to {payload.target_status} in WooCommerce."
    else:
        local_order = load_local_order_by_woo(db, woo_order_id) or local_order
        action_status = "writeback_pending"
        message = (
            f"Local workflow was saved, but WooCommerce status is still processing. "
            f"Writeback status: {writeback.status}."
            if payload.target_status == "completed"
            else f"Cancellation was not applied locally because WooCommerce writeback status is {writeback.status}."
        )

    record_status_action_audit(
        db,
        local_order,
        payload.target_status,
        reason,
        actor,
        idempotency_key,
        writeback.status,
    )

    return WooOrderStatusActionResponse(
        status=action_status,
        target_status=payload.target_status,
        woo_order_id=woo_order_id,
        local_order_id=local_order.id,
        local_status=local_order.local_status,
        released_quantity=float(released_quantity),
        message=message,
        woo_sync_status=writeback.status,
        woo_writeback_queue_id=writeback.id,
        woo_sync_error=writeback.error_message or stock_sync_error(stock_sync),
    )


def substitute_order_line(
    db: Session,
    order_id: int,
    order_line_id: int,
    payload: OrderSubstitutionRequest,
    *,
    actor: str,
) -> OrderSubstitutionResponse:
    reason = optional_reason(payload.reason)
    idempotency_key = required_idempotency_key(payload.idempotency_key)
    mutation_payload = {
        "order_id": order_id,
        "order_line_id": order_line_id,
        "replacement_inventory_item_id": payload.replacement_inventory_item_id,
        "reason": reason,
        "idempotency_key": idempotency_key,
    }
    mutation, replay = begin_stock_mutation(db, "order_line_substitution", idempotency_key, mutation_payload)
    if replay is not None:
        return OrderSubstitutionResponse.model_validate(replay)

    current_item_id = db.scalar(
        select(OrderItem.inventory_item_id).where(
            OrderItem.id == order_line_id,
            OrderItem.order_id == order_id,
        )
    )
    if current_item_id is None:
        raise OrderActionConflict("Order line is not linked to an inventory item and cannot be substituted.")
    lock_inventory_stock(db, {current_item_id, payload.replacement_inventory_item_id})
    line = db.scalars(
        select(OrderItem)
        .where(OrderItem.id == order_line_id, OrderItem.order_id == order_id)
        .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if line is None:
        raise OrderActionConflict("Order line was not found.")
    if line.inventory_item_id != current_item_id:
        raise OrderActionConflict("Order line changed during substitution; refresh it and try again.")
    order = line.order
    if not is_operational_order(order) or order.woo_status != "processing":
        raise OrderActionConflict("Only a live processing order can be substituted.")
    if any(
        to_decimal(value) > 0
        for value in (line.quantity_picked, line.quantity_fulfilled, line.quantity_stock_reduced)
    ):
        raise OrderActionConflict("A picked, fulfilled, or stock-reduced line cannot be substituted.")

    current_item = line.inventory_item
    replacement = db.get(InventoryItem, payload.replacement_inventory_item_id)
    if replacement is None or not replacement.active:
        raise OrderActionConflict("Replacement inventory item was not found or is inactive.")
    if replacement.non_inventory:
        raise OrderActionConflict("Replacement must be an inventory-tracked item.")
    validate_item_mapping(db, replacement)
    if current_item is None:
        raise OrderActionConflict("Current inventory item was not found.")
    if replacement.id == current_item.id:
        raise OrderActionConflict("Replacement item is already the effective item on this order line.")

    original_item_id = line.substituted_from_inventory_item_id or current_item.id
    released = release_line_allocations(
        db,
        order,
        line,
        max(to_decimal(line.quantity_allocated) - to_decimal(line.quantity_picked), Decimal("0")),
        f"Substituted order line {line.id}." + (f" Reason: {reason}" if reason else ""),
        "order_line_substitution",
        created_by=actor,
    )
    reverting = replacement.id == original_item_id
    line.inventory_item_id = replacement.id
    line.inventory_item = replacement
    line.substituted_from_inventory_item_id = None if reverting else original_item_id
    line.substitution_reason = None if reverting else (reason or None)
    line.substituted_by = None if reverting else actor
    line.substituted_at = None if reverting else datetime.now(timezone.utc)
    line.matched_status = "matched"
    line.sync_status = "synced" if reverting else "substituted"
    line.sync_error = None
    line.allocation_status = "unallocated"
    line.availability_status = "unallocated"
    line.pick_status = "not_ready"
    line.allocation_exception_reason = None
    line.sellable_snapshot = to_decimal(replacement.sellable)
    line.shortage_quantity = max(to_decimal(line.quantity_ordered), Decimal("0"))
    line.status = order.local_status
    order.workflow_notes = append_note(
        order.workflow_notes,
        f"Order line {line.id} {'reverted to its original item' if reverting else f'substituted from item {original_item_id} to item {replacement.id}'}."
        + (f" Reason: {reason}" if reason else ""),
    )
    audit_substitution(db, order, current_item, replacement, reason, actor)
    sync_order_workflow_statuses(order)
    auto_allocate_order_if_possible(db, order.id, source=f"substitution:{actor}")
    db.flush()
    db.refresh(line)
    response = OrderSubstitutionResponse(
        status="reverted" if reverting else "substituted",
        order_id=order.id,
        order_line_id=line.id,
        substituted_from_item_id=original_item_id,
        replacement_inventory_item_id=replacement.id,
        released_quantity=float(released),
        allocation_status=line.allocation_status,
        pick_status=line.pick_status,
        message=(
            "Order line was restored to its original product and reallocated where stock was available."
            if reverting
            else "Order line was substituted locally and reallocated where stock was available. WooCommerce line items were not changed."
        ),
    )
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def add_local_order_line(
    db: Session,
    order_id: int,
    payload: OrderLineAddRequest,
    *,
    actor: str,
) -> OrderLineEditResponse:
    reason = optional_reason(payload.reason)
    idempotency_key = required_idempotency_key(payload.idempotency_key)
    quantity = Decimal(str(payload.quantity))
    mutation_payload = {
        "order_id": order_id,
        "inventory_item_id": payload.inventory_item_id,
        "quantity": str(quantity),
        "reason": reason,
        "idempotency_key": idempotency_key,
    }
    mutation, replay = begin_stock_mutation(db, "order_line_addition", idempotency_key, mutation_payload)
    if replay is not None:
        return OrderLineEditResponse.model_validate(replay)

    lock_inventory_stock(db, {payload.inventory_item_id})
    order = db.scalars(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if order is None:
        raise OrderActionConflict("Order was not found.")
    if not is_operational_order(order) or order.woo_status != "processing":
        raise OrderActionConflict("Products can only be added to a live processing order.")
    item = db.get(InventoryItem, payload.inventory_item_id)
    if item is None or not item.active:
        raise OrderActionConflict("Inventory item was not found or is inactive.")
    if item.non_inventory:
        raise OrderActionConflict("Added products must be inventory-tracked items.")
    validate_item_mapping(db, item)

    line = OrderItem(
        order=order,
        woo_order_item_id=None,
        woo_product_id=item.woo_product_id,
        woo_variation_id=item.woo_variation_id,
        inventory_item_id=item.id,
        line_number=max((existing.line_number or 0 for existing in order.items), default=0) + 1,
        sku=item.sku,
        barcode=item.barcode,
        description=item.description,
        name=item.description,
        quantity_ordered=quantity,
        ordered_qty=quantity,
        ordered_uom="Each",
        quantity_allocated=Decimal("0"),
        allocated_qty=Decimal("0"),
        quantity_picked=Decimal("0"),
        picked_qty=Decimal("0"),
        quantity_fulfilled=Decimal("0"),
        fulfilled_qty=Decimal("0"),
        quantity_stock_reduced=Decimal("0"),
        unit_cost=item.unit_cost,
        unit_price=item.sales_price or item.recommended_retail_price,
        unit_cost_total=(item.unit_cost * quantity if item.unit_cost is not None else None),
        brand=item.brand,
        matched_status="matched",
        availability_status="unallocated",
        allocation_status="unallocated",
        pick_status="not_ready",
        sellable_snapshot=to_decimal(item.sellable),
        shortage_quantity=quantity,
        sync_status="local_added",
        status=order.local_status,
    )
    db.add(line)
    db.flush()
    order.workflow_notes = append_note(
        order.workflow_notes,
        f"Added item {item.id} as local-only order line {line.id} with quantity {quantity}."
        + (f" Reason: {reason}" if reason else ""),
    )
    sync_order_workflow_statuses(order)
    auto_allocate_order_if_possible(db, order.id, source=f"local-order-edit:{actor}")
    db.flush()
    db.refresh(line)
    response = OrderLineEditResponse(
        status="added",
        order_id=order.id,
        order_line_id=line.id,
        inventory_item_id=item.id,
        allocation_status=line.allocation_status,
        pick_status=line.pick_status,
        message="Product was added to the Pongo order and allocated where stock was available. The WooCommerce order was not changed.",
    )
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def remove_local_order_line(
    db: Session,
    order_id: int,
    order_line_id: int,
    payload: OrderLineRemoveRequest,
    *,
    actor: str,
) -> OrderLineEditResponse:
    reason = optional_reason(payload.reason)
    idempotency_key = required_idempotency_key(payload.idempotency_key)
    mutation_payload = {
        "order_id": order_id,
        "order_line_id": order_line_id,
        "reason": reason,
        "idempotency_key": idempotency_key,
    }
    mutation, replay = begin_stock_mutation(db, "order_line_removal", idempotency_key, mutation_payload)
    if replay is not None:
        return OrderLineEditResponse.model_validate(replay)

    item_id = db.scalar(
        select(OrderItem.inventory_item_id).where(OrderItem.id == order_line_id, OrderItem.order_id == order_id)
    )
    if item_id is not None:
        lock_inventory_stock(db, {item_id})
    line = db.scalars(
        select(OrderItem)
        .where(OrderItem.id == order_line_id, OrderItem.order_id == order_id)
        .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if line is None:
        raise OrderActionConflict("Order line was not found.")
    order = line.order
    if not is_operational_order(order) or order.woo_status != "processing":
        raise OrderActionConflict("Products can only be removed from a live processing order.")
    if line.matched_status == "removed":
        raise OrderActionConflict("Order line was already removed from the Pongo order.")
    if any(
        to_decimal(value) > 0
        for value in (line.quantity_picked, line.quantity_fulfilled, line.quantity_stock_reduced)
    ):
        raise OrderActionConflict("A picked, fulfilled, or stock-reduced line cannot be removed.")

    released = release_line_allocations(
        db,
        order,
        line,
        to_decimal(line.quantity_allocated),
        f"Removed order line {line.id} from the local Pongo order."
        + (f" Reason: {reason}" if reason else ""),
        "order_line_removal",
        created_by=actor,
    )
    if to_decimal(line.quantity_allocated) > 0:
        raise OrderActionConflict("The order line allocation could not be fully released; refresh it and try again.")
    line.quantity_ordered = Decimal("0")
    line.ordered_qty = Decimal("0")
    line.shortage_quantity = Decimal("0")
    line.matched_status = "removed"
    line.availability_status = "removed"
    line.allocation_status = "removed"
    line.pick_status = "not_ready"
    line.allocation_exception_reason = None
    line.status = RETIRED_WOO_LINE_STATUS
    line.sync_status = "local_removed"
    line.sync_error = None
    order.workflow_notes = append_note(
        order.workflow_notes,
        f"Removed order line {line.id} from the local Pongo order."
        + (f" Reason: {reason}" if reason else ""),
    )
    sync_order_workflow_statuses(order)
    response = OrderLineEditResponse(
        status="removed",
        order_id=order.id,
        order_line_id=line.id,
        inventory_item_id=item_id,
        released_quantity=float(released),
        allocation_status=line.allocation_status,
        pick_status=line.pick_status,
        message="Product was removed from the Pongo order and its unpicked allocation was released. The WooCommerce order was not changed.",
    )
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def prepare_completed_order_for_picking(
    db: Session,
    client: WooCommerceClient,
    order_id: int,
    payload: CompletedOrderPickRecoveryRequest,
    *,
    actor: str,
) -> CompletedOrderPickRecoveryResponse:
    reason = required_reason(payload.reason)
    idempotency_key = required_idempotency_key(payload.idempotency_key)
    mutation_payload = {
        "order_id": order_id,
        "reason": reason,
        "idempotency_key": idempotency_key,
    }
    cached_order = db.get(Order, order_id)
    if cached_order is None or cached_order.woo_order_id is None:
        raise OrderActionConflict("Order is not linked to WooCommerce.")
    remote = validate_remote_order(client.get_order(cached_order.woo_order_id), cached_order.woo_order_id)
    remote_status = str(remote.get("status") or "").strip().casefold()
    mutation, replay = begin_stock_mutation(db, "prepare_completed_order_pick", idempotency_key, mutation_payload)
    if replay is not None:
        if remote_status != "completed" or cached_order.completion_status != "picking_recovery":
            raise OrderActionConflict("Recovery picking is no longer active for this order.")
        return CompletedOrderPickRecoveryResponse.model_validate(replay)
    if remote_status != "completed":
        raise OrderActionConflict("Recovery picking requires the live WooCommerce order to still be completed.")
    commit_remote_order_records(db, [remote], ["completed"], actor, commit=False)
    order = lock_order_completion_scope(db, order_id)
    if order is None:
        raise OrderActionConflict("Order was not found.")
    if not order.completed_without_picking or order.completion_status != "completed_without_picking":
        raise OrderActionConflict("Only an order completed without picking can be prepared for recovery picking.")
    if order.woo_status != "completed":
        raise OrderActionConflict("Recovery picking requires the WooCommerce order to remain completed.")
    if any(
        to_decimal(value) > 0
        for line in order.items
        for value in (line.quantity_picked, line.quantity_fulfilled, line.quantity_stock_reduced)
    ):
        raise OrderActionConflict("Recovery picking is blocked because this order already has processed quantities.")
    if db.scalar(select(PickLine.id).where(PickLine.order_id == order.id).limit(1)) is not None:
        raise OrderActionConflict("Recovery picking is blocked because this order has prior pick history.")

    order.completion_status = "picking_recovery"
    order.local_status = "open"
    order.allocation_status = "unallocated"
    order.auto_allocation_status = None
    order.pick_status = "not_ready"
    order.allocation_exception_reason = None
    order.workflow_notes = append_note(
        order.workflow_notes,
        f"Prepared completed-without-picking order for recovery picking. {reason}",
    )
    for line in order.items:
        line.allocation_status = "unallocated"
        line.availability_status = "unallocated"
        line.pick_status = "not_ready"
        line.allocation_exception_reason = None
    add_order_audit_events(
        db,
        order,
        "prepare_completed_order_pick",
        f"Prepared completed-without-picking order for recovery picking. {reason}",
        created_by=actor,
    )
    sync_order_workflow_statuses(order)
    auto_allocate_order_if_possible(db, order.id, source=f"picking-recovery:{actor}")
    db.flush()
    response = CompletedOrderPickRecoveryResponse(
        status="prepared",
        order_id=order.id,
        allocation_status=order.allocation_status,
        pick_status=order.pick_status,
        message="Completed order is prepared for picking. WooCommerce status was not changed.",
    )
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def sync_completed_picked_stock(
    db: Session,
    settings: Settings,
    woo_client: WooCommerceClient,
    order_id: int,
    requested_by: str,
):
    ids = db.execute(
        select(OrderItem.inventory_item_id, OrderItem.substituted_from_inventory_item_id).where(
            OrderItem.order_id == order_id
        )
    ).all()
    item_ids = {item_id for pair in ids for item_id in pair if item_id}
    return sync_inventory_stock(
        db,
        settings,
        woo_client,
        item_ids=item_ids,
        requested_by=requested_by,
    )


def required_reason(value: str) -> str:
    reason = (value or "").strip()
    if not reason:
        raise OrderActionConflict("A nonblank reason is required.")
    return reason


def optional_reason(value: str | None) -> str:
    return (value or "").strip()


def required_idempotency_key(value: str) -> str:
    key = (value or "").strip()
    if not key:
        raise OrderActionConflict("A nonblank idempotency key is required.")
    return key


def validate_remote_order(remote: Any, expected_woo_order_id: int) -> dict[str, Any]:
    if not isinstance(remote, dict):
        raise WooCommerceClientError("WooCommerce returned an invalid order response.")
    remote_id = remote.get("id")
    if not isinstance(remote_id, int) or remote_id != expected_woo_order_id:
        raise WooCommerceClientError("WooCommerce returned an unexpected order identifier.")
    if not str(remote.get("status") or "").strip():
        raise WooCommerceClientError("WooCommerce returned an order without a status.")
    return remote


def reconcile_one_remote_order(db: Session, remote: dict[str, Any], status: str, actor: str) -> Order:
    commit_remote_order_records(db, [remote], [status], actor)
    order = load_local_order_by_woo(db, int(remote["id"]))
    if order is None:
        raise OrderActionConflict("WooCommerce order could not be reconciled into the local operational store.")
    return order


def load_local_order_by_woo(db: Session, woo_order_id: int) -> Order | None:
    return db.scalars(
        select(Order)
        .where(Order.woo_order_id == woo_order_id, Order.is_historical_snapshot.is_(False))
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
    ).one_or_none()


def status_queue_for_key(db: Session, idempotency_key: str) -> WooWritebackQueue | None:
    return db.scalars(
        select(WooWritebackQueue).where(
            WooWritebackQueue.operation_type == "update_order_status",
            WooWritebackQueue.idempotency_key == idempotency_key,
        )
    ).one_or_none()


def validate_status_queue_replay(
    row: WooWritebackQueue,
    woo_order_id: int,
    target_status: str,
    reason: str,
) -> None:
    queued_target = str(((row.payload_json or {}).get("body") or {}).get("status") or "").strip().casefold()
    queued_reason = str((row.preview_json or {}).get("action_reason") or "").strip()
    if row.woo_order_id != woo_order_id or queued_target != target_status or queued_reason != reason:
        raise OrderActionConflict("Idempotency key was already used for a different order status action.")


def infer_completion_mode(order: Order, requested: str) -> str:
    inventory_lines = [
        line
        for line in order.items
        if is_actionable_order_line(line) and not (line.inventory_item and line.inventory_item.non_inventory)
    ]
    processed = [
        value
        for line in inventory_lines
        for value in (line.quantity_picked, line.quantity_fulfilled, line.quantity_stock_reduced)
    ]
    if not any(to_decimal(value) > 0 for value in processed):
        if requested == "complete_picked":
            raise OrderActionConflict("This order has not been picked; picked completion is not allowed.")
        return "complete_without_picking"
    if inventory_lines and all(line_is_fully_picked_and_reduced(line) for line in inventory_lines):
        if requested == "complete_without_picking":
            raise OrderActionConflict("This order is fully picked; completion without picking is not allowed.")
        return "complete_picked"
    raise OrderActionConflict(
        "Order completion is blocked because picked, fulfilled, or stock-reduced quantities are only partial."
    )


def complete_local_order_once(
    db: Session,
    order_id: int,
    completion_mode: str,
    reason: str,
    actor: str,
) -> dict[str, Any]:
    order = db.get(Order, order_id)
    if order is None:
        raise OrderActionConflict("Local order was not found.")
    if order.completion_status == "cancellation_pending":
        raise OrderActionConflict("Order completion is blocked because cancellation is already pending.")
    if order.completion_status in {"completed", "completed_without_picking"}:
        expected = "completed" if completion_mode == "complete_picked" else "completed_without_picking"
        if order.completion_status != expected:
            raise OrderActionConflict(
                f"Local order was already completed using {order.completion_status}; it cannot be replayed as {completion_mode}."
            )
        return {
            "status": order.completion_status,
            "order_id": order.id,
            "released_quantity": 0,
            "message": "Local completion was already applied.",
        }
    try:
        if completion_mode == "complete_picked":
            return complete_picked_order(db, order_id, created_by=actor)
        return complete_order_without_stock_reduction(db, order_id, reason, created_by=actor)
    except ValueError as error:
        if "cancellation is already pending" in str(error):
            raise OrderActionConflict(str(error)) from error
        raise


def assert_cancellable(order: Order) -> None:
    if any(
        to_decimal(value) > 0
        for line in order.items
        for value in (line.quantity_picked, line.quantity_fulfilled, line.quantity_stock_reduced)
    ):
        raise OrderActionConflict(
            "Cancellation is blocked because the order has picked, fulfilled, or stock-reduced quantities."
        )


def begin_cancellation_guard(
    db: Session,
    order_id: int,
    *,
    reason: str,
    actor: str,
    idempotency_key: str,
) -> Order:
    order = lock_order_completion_scope(db, order_id)
    if order is None:
        raise OrderActionConflict("Local order was not found.")
    if order.completion_status in {"completed", "completed_without_picking"}:
        raise OrderActionConflict("Cancellation is blocked because local completion was already applied.")
    guard_marker = f"idempotency={idempotency_key!r}; reason={reason}"
    if order.completion_status == "cancellation_pending" and guard_marker not in (order.workflow_notes or ""):
        raise OrderActionConflict("A different cancellation action is already pending for this order.")
    assert_cancellable(order)
    if order.completion_status != "cancellation_pending":
        order.completion_status = "cancellation_pending"
        order.local_status = "cancellation_pending"
        order.pick_status = "not_ready"
        order.workflow_notes = append_note(
            order.workflow_notes,
            f"Cancellation guard created by {actor}; idempotency={idempotency_key!r}; reason={reason}",
        )
    db.commit()
    return load_local_order_by_woo(db, int(order.woo_order_id)) or order


def total_allocated(order: Order) -> Decimal:
    return sum((to_decimal(line.quantity_allocated) for line in order.items), Decimal("0"))


def audit_substitution(
    db: Session,
    order: Order,
    current_item: InventoryItem,
    replacement: InventoryItem,
    reason: str,
    actor: str,
) -> None:
    for item, role in ((current_item, "original"), (replacement, "replacement")):
        row = first_item_location(db, item)
        if row is None:
            continue
        add_audit_event(
            db,
            item,
            row,
            "order_line_substitution",
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
            notes=f"{role.title()} item recorded for local order substitution. {reason}",
            created_by=actor,
        )


def record_status_action_audit(
    db: Session,
    order: Order,
    target_status: str,
    reason: str,
    actor: str,
    idempotency_key: str,
    woo_sync_status: str,
) -> None:
    marker = f"idempotency={idempotency_key!r}; woo_writeback={woo_sync_status!r}"
    locked = db.scalars(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if marker in (locked.workflow_notes or ""):
        return
    note = (
        f"Order status action target={target_status}; actor={actor}; {marker}; reason={reason}"
    )
    locked.workflow_notes = append_note(locked.workflow_notes, note)
    add_order_audit_events(db, locked, "order_status_action", note, created_by=actor)
    db.commit()


def stock_sync_error(sync) -> str | None:
    if sync is None:
        return None
    if sync.failed_count:
        return f"{sync.failed_count} completed-order stock update(s) failed to reach WooCommerce."
    if sync.dry_run_count:
        return "WooCommerce stock writeback ran in dry-run mode; remote stock was not changed."
    if sync.skipped_unmapped_count:
        return f"{sync.skipped_unmapped_count} completed-order stock target(s) were not mapped to WooCommerce."
    if sync.status not in {"sent", "no_changes"}:
        details = "; ".join(sync.errors) if sync.errors else f"Stock sync status is {sync.status}."
        return f"Completed-order stock was not fully synchronized to WooCommerce. {details}"
    return None
