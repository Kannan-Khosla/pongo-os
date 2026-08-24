from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.fulfillments import FulfillmentLine
from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.models.picks import PickLine
from app.models.stock_mutations import StockMutationRequest
from app.models.woocommerce import WooWritebackQueue
from app.schemas.orders import (
    CompletedOrderPickRecoveryRequest,
    CompletedOrderPickRecoveryResponse,
    CompletedOrderRecordPickedRequest,
    CompletedOrderRecordPickedResponse,
    CompletedOrderRecordPickedResult,
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
from app.schemas.picks import PickCommitRequest
from app.schemas.woocommerce import WooStockSyncRequest
from app.services.location_inventory import lock_inventory_stock
from app.services.order_metadata import add_order_note
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
from app.services.picks import commit_pick, unpick_orders
from app.services.stock_mutation_guard import IdempotencyConflict, begin_stock_mutation, complete_stock_mutation
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_orders import RETIRED_WOO_LINE_STATUS, commit_remote_order_records, get_open_order_detail
from app.services.woocommerce_stock_sync_jobs import create_stock_sync_job, resume_stock_sync_job
from app.services.woocommerce_writeback import (
    stock_writeback_enabled,
    sync_inventory_stock,
    sync_order_status,
    validate_item_mapping,
)


class OrderActionConflict(ValueError):
    pass


_REMOTE_ORDER_UNSET = object()
_REMOTE_ORDER_MISSING = object()
_REMOTE_ORDER_VALIDATION_FAILED = object()


def register_completed_pick_batch_fingerprint(
    db: Session,
    payload: CompletedOrderRecordPickedRequest,
    *,
    actor: str,
) -> None:
    """Persist request identity without claiming ownership of batch execution."""
    fingerprint_payload = {
        "order_ids": list(dict.fromkeys(payload.order_ids)),
        "reason": payload.reason,
        "actor": actor,
        "idempotency_key": payload.idempotency_key,
    }
    mutation, replay = begin_stock_mutation(
        db,
        "record_completed_pick_batch_fingerprint",
        payload.idempotency_key,
        fingerprint_payload,
    )
    if replay is not None:
        return
    # This row records only immutable request identity. It is deliberately
    # completed before work begins, so a crash cannot leave an ownership lease
    # that blocks replay. Child mutation and stock-job keys provide execution
    # idempotency.
    complete_stock_mutation(mutation, {"status": "accepted"})
    db.commit()


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

    if (
        payload.target_status == "cancelled"
        and remote_status in {"cancelled", "refunded", "failed"}
        and not (remote_status == payload.target_status and existing_queue is not None)
    ):
        local_order = load_local_order_by_woo(db, woo_order_id)
        before_allocated = total_allocated(local_order) if local_order is not None else Decimal("0")
        restored_quantity = Decimal("0")
        has_fulfilled_quantity = bool(
            local_order
            and any(to_decimal(line.quantity_fulfilled) > 0 for line in local_order.items)
        )
        if (
            local_order is not None
            and not has_fulfilled_quantity
            and any(
                to_decimal(value) > 0
                for line in local_order.items
                for value in (line.quantity_picked, line.quantity_stock_reduced)
            )
        ):
            unpick_result = unpick_orders(
                db,
                [local_order.id],
                created_by=actor,
                reason=f"WooCommerce already {remote_status}: {reason}",
                idempotency_key=idempotency_key,
                commit=False,
            )
            if unpick_result.get("status") != "completed":
                raise OrderActionConflict(
                    "Pongo could not restore picked stock before closing this WooCommerce order. "
                    + " ".join(unpick_result.get("errors") or [])
                )
            restored_quantity = to_decimal(unpick_result.get("total_quantity_restored"))

        local_order = reconcile_one_remote_order(db, remote, remote_status, actor)
        released_quantity = max(before_allocated - total_allocated(local_order), Decimal("0"))
        if existing_queue is not None and existing_queue.status != "sent":
            existing_queue.status = "sent"
            existing_queue.sent_at = datetime.now(timezone.utc)
            existing_queue.response_json = remote
            existing_queue.error_message = None
        stock_sync = sync_order_inventory_stock(db, settings, client, local_order.id, actor)
        woo_sync_status = existing_queue.status if existing_queue is not None else "not_required"
        record_status_action_audit(
            db,
            local_order,
            remote_status,
            reason,
            actor,
            idempotency_key,
            woo_sync_status,
        )
        db.commit()
        message = (
            f"WooCommerce already marked this order {remote_status}. "
            "Pongo removed it from Open Orders"
        )
        if restored_quantity > 0:
            message += f", restored {restored_quantity} picked unit(s)"
        if released_quantity > 0:
            message += f", and released {released_quantity} allocated unit(s)"
        message += "."
        if has_fulfilled_quantity:
            message += " Fulfilled stock history was preserved."
        return WooOrderStatusActionResponse(
            status="reconciled",
            target_status=payload.target_status,
            woo_order_id=woo_order_id,
            local_order_id=local_order.id,
            local_status=local_order.local_status,
            released_quantity=float(released_quantity),
            message=message,
            woo_sync_status=woo_sync_status,
            woo_writeback_queue_id=existing_queue.id if existing_queue is not None else None,
            woo_sync_error=stock_sync_error(stock_sync),
        )

    if remote_status == payload.target_status:
        if existing_queue is None:
            raise OrderActionConflict(
                f"WooCommerce order {woo_order_id} is already {payload.target_status}; "
                "this action has no matching idempotent writeback record."
            )
        local_order = reconcile_one_remote_order(db, remote, payload.target_status, actor)
        stock_sync = (
            sync_order_inventory_stock(db, settings, client, local_order.id, actor)
            if payload.target_status == "cancelled"
            else None
        )
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
            woo_sync_error=existing_queue.error_message or stock_sync_error(stock_sync),
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
    restored_quantity = Decimal("0")
    stock_sync = None

    if payload.target_status == "completed":
        completion_mode = infer_completion_mode(local_order, payload.completion_mode)
        result = complete_local_order_once(db, local_order.id, completion_mode, reason, actor)
        released_quantity = to_decimal(result.get("released_quantity"))
        if completion_mode == "complete_picked":
            stock_sync = sync_order_inventory_stock(db, settings, client, local_order.id, actor)
    else:
        if any(
            to_decimal(value) > 0
            for line in local_order.items
            for value in (line.quantity_picked, line.quantity_stock_reduced)
        ):
            unpick_result = unpick_orders(
                db,
                [local_order.id],
                created_by=actor,
                reason=f"Cancellation: {reason}",
                idempotency_key=idempotency_key,
                commit=False,
            )
            if unpick_result.get("status") != "completed":
                raise OrderActionConflict(
                    "Cancellation could not restore picked stock. "
                    + " ".join(unpick_result.get("errors") or [])
                )
            restored_quantity = to_decimal(unpick_result.get("total_quantity_restored"))
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
            stock_sync = sync_order_inventory_stock(db, settings, client, local_order.id, actor)
        action_status = payload.target_status
        message = f"Order changed to {payload.target_status} in WooCommerce."
        if restored_quantity > 0:
            message += f" Restored {restored_quantity} picked unit(s) to Pongo stock."
    else:
        local_order = load_local_order_by_woo(db, woo_order_id) or local_order
        action_status = "writeback_pending"
        message = (
            f"Local workflow was saved, but WooCommerce status is still processing. "
            f"Writeback status: {writeback.status}."
            if payload.target_status == "completed"
            else (
                f"Cancellation is pending in Pongo because WooCommerce writeback status is {writeback.status}. "
                "Remaining allocation stays reserved until WooCommerce confirms cancellation."
            )
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
    line.local_invoice_unit_price = None if reverting else item_invoice_unit_price(replacement, line.unit_price)
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
        unit_price=item_invoice_unit_price(item),
        local_invoice_unit_price=item_invoice_unit_price(item),
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


def record_completed_orders_picked(
    db: Session,
    settings: Settings,
    client: WooCommerceClient,
    payload: CompletedOrderRecordPickedRequest,
    *,
    actor: str,
) -> CompletedOrderRecordPickedResponse:
    selected_ids = list(dict.fromkeys(payload.order_ids))
    register_completed_pick_batch_fingerprint(db, payload, actor=actor)
    prefetched_remote = prefetch_live_orders_for_record_picked(
        db,
        client,
        selected_ids,
        payload.idempotency_key,
    )
    results: list[CompletedOrderRecordPickedResult] = []
    errors: list[str] = []
    for order_id in selected_ids:
        child_key = completed_pick_idempotency_key(payload.idempotency_key, order_id)
        try:
            result = record_completed_order_picked(
                db,
                client,
                order_id,
                reason=payload.reason,
                idempotency_key=child_key,
                actor=actor,
                remote=prefetched_remote.get(order_id, _REMOTE_ORDER_UNSET),
            )
        except IdempotencyConflict:
            db.rollback()
            raise
        except Exception as error:
            db.rollback()
            message = getattr(error, "message", None) or str(error) or "Order could not be recorded as picked."
            result = CompletedOrderRecordPickedResult(
                order_id=order_id,
                status="rejected",
                message=message,
            )
            errors.append(f"Order {order_id}: {message}")
        # Aggregate replay is intentionally rebuilt from the independently
        # guarded child operations. Normalizing this presentation flag keeps a
        # successful retry byte-for-byte stable without a crash-prone batch
        # ownership row.
        result.replayed = False
        results.append(result)

    queue_recorded_batch_stock(
        db,
        settings,
        results,
        batch_key=payload.idempotency_key,
        actor=actor,
    )
    succeeded = [result for result in results if result.status == "completed"]
    pending = [result for result in results if result.status == "pending_stock_sync"]
    failed_count = len(results) - len(succeeded)
    if len(succeeded) == len(results):
        status = "completed"
    elif len(pending) == len(results):
        status = "pending_stock_sync"
    elif succeeded or pending:
        status = "partial"
    else:
        status = "rejected"
    for result in pending:
        error = result.woo_stock_sync_error or "WooCommerce stock sync still needs to be queued."
        errors.append(f"Order {result.order_id}: {error}")
    locally_recorded = [
        result for result in results if result.status in {"completed", "pending_stock_sync"}
    ]
    response = CompletedOrderRecordPickedResponse(
        status=status,
        requested_count=len(selected_ids),
        succeeded_count=len(succeeded),
        failed_count=failed_count,
        total_quantity_picked=sum(result.total_quantity_picked for result in locally_recorded),
        created_stock_movements=sum(result.created_stock_movements for result in locally_recorded),
        created_audit_events=sum(result.created_audit_events for result in locally_recorded),
        results=results,
        errors=errors,
    )
    return response


def record_completed_order_picked(
    db: Session,
    client: WooCommerceClient,
    order_id: int,
    *,
    reason: str | None,
    idempotency_key: str,
    actor: str,
    remote: Any = _REMOTE_ORDER_UNSET,
) -> CompletedOrderRecordPickedResult:
    mutation_payload = {
        "order_id": order_id,
        "reason": reason,
        "actor": actor,
        "idempotency_key": idempotency_key,
    }
    mutation, replay = begin_stock_mutation(
        db,
        "record_completed_order_picked",
        idempotency_key,
        mutation_payload,
    )
    if replay is not None:
        return CompletedOrderRecordPickedResult.model_validate(replay).model_copy(update={"replayed": True})

    cached_order = db.get(Order, order_id)
    if cached_order is None or cached_order.woo_order_id is None:
        raise OrderActionConflict("Order is not linked to WooCommerce.")
    if remote is _REMOTE_ORDER_VALIDATION_FAILED:
        raise WooCommerceClientError(
            "Live WooCommerce batch validation is unavailable. No local stock was changed; retry the batch."
        )
    if remote is _REMOTE_ORDER_UNSET:
        remote = client.get_order(cached_order.woo_order_id)
    if remote is _REMOTE_ORDER_MISSING:
        raise WooCommerceClientError(
            f"WooCommerce did not return order {cached_order.woo_order_id} during live validation."
        )
    remote = validate_remote_order(remote, cached_order.woo_order_id)
    if str(remote.get("status") or "").strip().casefold() != "completed":
        raise OrderActionConflict("The live WooCommerce order must still be completed.")

    order = lock_order_completion_scope(db, order_id)
    if order is None:
        raise OrderActionConflict("Order was not found.")
    assert_completed_order_can_be_recorded_picked(db, order)
    original_completed_at = order.completed_at
    original_closed_at = order.closed_at
    original_local_status = order.local_status

    order.completion_status = "picking_recovery"
    order.local_status = "open"
    order.allocation_status = "unallocated"
    order.auto_allocation_status = None
    order.pick_status = "not_ready"
    order.allocation_exception_reason = None
    for line in order.items:
        if not is_actionable_order_line(line):
            continue
        line.allocation_status = "unallocated"
        line.availability_status = "unallocated"
        line.pick_status = "not_ready"
        line.allocation_exception_reason = None
    sync_order_workflow_statuses(order)

    allocation = auto_allocate_order_if_possible(
        db,
        order.id,
        source=f"completed-record-picked:{actor}",
    )
    if allocation["status"] != "allocated":
        raise OrderActionConflict(
            allocation.get("reason") or "Every inventory line must be fully allocatable before stock can be recorded."
        )
    required_lines = actionable_inventory_lines(order)
    if not required_lines or any(
        to_decimal(line.quantity_allocated) < to_decimal(line.quantity_ordered)
        for line in required_lines
    ):
        raise OrderActionConflict("Every inventory line must be fully allocated before stock can be recorded.")

    note_text = f"Manually recorded as picked from Completed Orders by {actor}."
    if reason:
        note_text += f" Reason: {reason}"
    pick_result = commit_pick(
        db,
        PickCommitRequest(
            order_ids=[order.id],
            allow_partial=False,
            created_by=actor,
            notes=note_text,
            idempotency_key=completed_pick_step_key(idempotency_key),
        ),
        commit=False,
    )
    if pick_result.status != "posted" or pick_result.errors:
        raise OrderActionConflict(" ".join(pick_result.errors) or "Order could not be fully picked.")

    # A fully picked recovery releases no sellable stock, so running the global
    # FIFO allocator for every row only adds batch latency and lock contention.
    complete_picked_order(db, order.id, created_by=actor, commit=False, run_fifo=False)
    order = lock_order_completion_scope(db, order.id)
    if order is None:
        raise OrderActionConflict("Order was not found after picking.")
    order.local_status = original_local_status if original_local_status in {"completed", "closed"} else "completed"
    order.completion_status = "completed"
    order.completed_without_picking = False
    order.completed_at = original_completed_at
    order.closed_at = original_closed_at
    order.workflow_notes = append_note(order.workflow_notes, note_text)
    add_order_note(
        db,
        order.id,
        note_text,
        note_type="system",
        created_by=actor,
    )
    db.flush()

    response = CompletedOrderRecordPickedResult(
        order_id=order.id,
        status="completed",
        message="Stock was recorded through a real Pongo pick. The WooCommerce order remained completed.",
        pick_id=pick_result.pick_id,
        pick_number=pick_result.pick_number,
        total_quantity_picked=pick_result.total_quantity_picked,
        created_stock_movements=pick_result.created_stock_movements,
        created_audit_events=pick_result.created_audit_events,
    )
    complete_stock_mutation(mutation, response)
    db.commit()
    return response


def assert_completed_order_can_be_recorded_picked(db: Session, order: Order) -> None:
    if order.woo_status != "completed":
        raise OrderActionConflict("The local WooCommerce status must be completed.")
    if order.local_status not in {"completed", "closed"}:
        raise OrderActionConflict("Only a locally completed order can be recorded as picked.")
    if order.completion_status not in {"completed", "completed_without_picking"}:
        raise OrderActionConflict("Only a completed order with no picking history can be recorded as picked.")
    if any(
        to_decimal(value) > 0
        for line in order.items
        for value in (
            line.quantity_allocated,
            line.quantity_picked,
            line.quantity_fulfilled,
            line.quantity_stock_reduced,
        )
    ):
        raise OrderActionConflict("The order already has allocated, picked, fulfilled, or stock-reduced quantities.")
    if db.scalar(select(PickLine.id).where(PickLine.order_id == order.id).limit(1)) is not None:
        raise OrderActionConflict("The order has prior pick history and cannot be recorded again.")
    if db.scalar(select(FulfillmentLine.id).where(FulfillmentLine.order_id == order.id).limit(1)) is not None:
        raise OrderActionConflict("The order has prior fulfillment history and cannot be recorded again.")
    required_lines = actionable_inventory_lines(order)
    if not required_lines:
        raise OrderActionConflict("The order has no actionable inventory lines to pick.")
    if any(
        line.matched_status != "matched"
        or line.inventory_item is None
        or not line.inventory_item.active
        for line in required_lines
    ):
        raise OrderActionConflict("Every inventory line must be matched to an active Pongo item.")
    for line in required_lines:
        try:
            validate_item_mapping(db, line.inventory_item)
        except ValueError as error:
            raise OrderActionConflict(
                f"Item {line.inventory_item.sku or line.inventory_item.id} cannot sync stock to WooCommerce: {error}"
            ) from error


def actionable_inventory_lines(order: Order) -> list[OrderItem]:
    return [
        line
        for line in order.items
        if is_actionable_order_line(line)
        and line.inventory_item is not None
        and not line.inventory_item.non_inventory
    ]


def queue_recorded_batch_stock(
    db: Session,
    settings: Settings,
    results: list[CompletedOrderRecordPickedResult],
    *,
    batch_key: str,
    actor: str,
) -> None:
    pending = [
        result
        for result in results
        if result.status in {"completed", "pending_stock_sync"}
        and result.woo_stock_sync_status not in {"queued", "sent", "no_changes"}
    ]
    if not pending:
        return
    pick_ids = [result.pick_id for result in pending if result.pick_id is not None]
    item_ids = set(
        db.scalars(select(PickLine.item_id).where(PickLine.pick_id.in_(pick_ids))).all()
    ) if pick_ids else set()
    job = None
    job_sync_status = None
    queue_error = None
    try:
        if not getattr(settings, "woocommerce_stock_sync_jobs_enabled", True):
            raise ValueError("The durable WooCommerce stock-sync worker is disabled.")
        if not stock_writeback_enabled(settings):
            raise ValueError("WooCommerce stock writeback is not enabled.")
        if getattr(settings, "woocommerce_writeback_dry_run", True):
            raise ValueError("WooCommerce stock writeback is still in dry-run mode.")
        if not item_ids:
            raise ValueError("No picked inventory items were available for stock sync.")
        job = create_stock_sync_job(
            db,
            WooStockSyncRequest(
                force=False,
                requested_by=f"completed-record-picked:{actor}"[:120],
                idempotency_key=completed_pick_stock_job_key(batch_key, item_ids),
                chunk_size=50,
                item_ids=sorted(item_ids),
            ),
        )
        if job.status in {"paused", "completed_with_errors"}:
            job = resume_stock_sync_job(db, job.id)
        if job is None or job.status not in {"queued", "running", "completed"}:
            raise ValueError(
                f"The durable WooCommerce stock-sync job is {getattr(job, 'status', 'unavailable')}."
            )
        job_sync_status = "sent" if job.status == "completed" else "queued"
    except Exception as error:
        db.rollback()
        job = None
        job_sync_status = None
        queue_error = (
            "Pongo stock was recorded, but its durable WooCommerce stock-sync job could not be queued. "
            f"Retry this action safely. {str(error)[:500]}"
        )
    keys_by_order_id = {
        result.order_id: completed_pick_idempotency_key(batch_key, result.order_id)
        for result in pending
    }
    mutations = {
        row.idempotency_key: row
        for row in db.scalars(
            select(StockMutationRequest).where(
                StockMutationRequest.operation == "record_completed_order_picked",
                StockMutationRequest.idempotency_key.in_(list(keys_by_order_id.values())),
            )
        ).all()
    }
    for response in pending:
        if job is not None:
            response.status = "completed"
            response.woo_stock_sync_status = job_sync_status
            response.woo_stock_sync_error = None
            response.woo_stock_sync_job_id = job.id
        else:
            response.status = "pending_stock_sync"
            response.woo_stock_sync_status = "queue_failed"
            response.woo_stock_sync_error = queue_error
            response.woo_stock_sync_job_id = None
        mutation = mutations.get(keys_by_order_id[response.order_id])
        complete_stock_mutation(mutation, response.model_copy(update={"replayed": False}))
    db.commit()


def prefetch_live_orders_for_record_picked(
    db: Session,
    client: WooCommerceClient,
    order_ids: list[int],
    batch_key: str,
) -> dict[int, Any]:
    keys_by_order_id = {
        order_id: completed_pick_idempotency_key(batch_key, order_id)
        for order_id in order_ids
    }
    completed_keys = set(
        db.scalars(
            select(StockMutationRequest.idempotency_key).where(
                StockMutationRequest.operation == "record_completed_order_picked",
                StockMutationRequest.status == "completed",
                StockMutationRequest.idempotency_key.in_(list(keys_by_order_id.values())),
            )
        ).all()
    )
    pending_ids = [
        order_id
        for order_id in order_ids
        if keys_by_order_id[order_id] not in completed_keys
    ]
    local_rows = db.execute(
        select(Order.id, Order.woo_order_id).where(
            Order.id.in_(pending_ids),
            Order.woo_order_id.is_not(None),
        )
    ).all()
    local_by_woo_id = {woo_order_id: order_id for order_id, woo_order_id in local_rows}
    get_orders = getattr(client, "get_orders", None)
    if not local_by_woo_id:
        return {}
    if not callable(get_orders):
        return {order_id: _REMOTE_ORDER_VALIDATION_FAILED for order_id in pending_ids}
    try:
        remote_orders = get_orders(list(local_by_woo_id))
    except Exception:
        return {order_id: _REMOTE_ORDER_VALIDATION_FAILED for order_id in pending_ids}
    remote_by_woo_id = {
        remote.get("id"): remote
        for remote in remote_orders
        if isinstance(remote, dict) and isinstance(remote.get("id"), int)
    }
    return {
        order_id: remote_by_woo_id.get(woo_order_id, _REMOTE_ORDER_MISSING)
        for woo_order_id, order_id in local_by_woo_id.items()
    }


def completed_pick_idempotency_key(batch_key: str, order_id: int) -> str:
    digest = sha256(f"{batch_key}:{order_id}".encode("utf-8")).hexdigest()
    return f"record-picked:{digest}"


def completed_pick_step_key(order_key: str) -> str:
    digest = sha256(f"pick:{order_key}".encode("utf-8")).hexdigest()
    return f"record-picked-step:{digest}"


def completed_pick_stock_job_key(batch_key: str, item_ids: set[int]) -> str:
    targets = ",".join(str(item_id) for item_id in sorted(item_ids))
    digest = sha256(f"stock-job:{batch_key}:{targets}".encode("utf-8")).hexdigest()
    return f"record-picked-stock:{digest}"


def sync_order_inventory_stock(
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


def item_invoice_unit_price(item: InventoryItem, fallback: Decimal | None = None) -> Decimal | None:
    if item.sales_price is not None:
        return item.sales_price
    if item.recommended_retail_price is not None:
        return item.recommended_retail_price
    return fallback


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
        return f"{sync.failed_count} order stock update(s) failed to reach WooCommerce."
    if sync.dry_run_count:
        return "WooCommerce stock writeback ran in dry-run mode; remote stock was not changed."
    if sync.skipped_unmapped_count:
        return f"{sync.skipped_unmapped_count} order stock target(s) were not mapped to WooCommerce."
    if sync.status not in {"sent", "no_changes"}:
        details = "; ".join(sync.errors) if sync.errors else f"Stock sync status is {sync.status}."
        return f"Order stock was not fully synchronized to WooCommerce. {details}"
    return None
