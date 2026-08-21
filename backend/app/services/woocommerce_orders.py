from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any

from sqlalchemy import String, and_, case, cast, exists, false, func, or_, select, text
from sqlalchemy.orm import Session, defer, selectinload

from app.core.config import get_settings
from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.models.woocommerce import WooCommerceSyncRun
from app.schemas.orders import OpenOrderDetail, OpenOrderLineRead, OpenOrderListResponse, OpenOrderRead
from app.schemas.woocommerce import (
    WooCommerceOrderPreviewLine,
    WooCommerceOrderPreviewOrder,
    WooCommerceOrderPreviewResponse,
    WooCommerceOrderSyncRequest,
)
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_sync_errors import prune_sync_errors, store_sync_error_once
from app.services.location_inventory import lock_inventory_stock
from app.services.order_workflow import (
    BLOCKING_ALLOCATION_EXCEPTION_REASONS,
    BLOCKING_MATCH_STATUSES,
    COMPLETED_LOCAL_STATUSES,
    actionable_order_line_clause,
    append_note,
    auto_allocate_processing_orders_fifo,
    operational_order_clause,
    release_line_allocations,
    release_unpicked_allocations,
    sync_order_workflow_statuses,
    workflow_flags,
)

OPEN_WOO_STATUSES = {"processing", "on-hold", "pending"}
BARCODE_META_KEYS = {"barcode", "_barcode", "_ywbc_barcode", "upc", "gtin"}
WOO_QUANTITY_BELOW_ALLOCATED_REASON = "woo_quantity_below_allocated"
RETIRED_WOO_LINE_STATUS = "removed_from_woocommerce"
POSTGRES_ORDER_IMPORT_LOCK_KEY = int.from_bytes(b"PONGOORD", byteorder="big")
PICK_READY_STATUSES = ("ready_to_pick", "partially_picked", "picked")
SHIPPING_LINES_UNSET = object()


@dataclass
class NormalizedWooOrderLine:
    woo_line_item_id: int | None
    woo_product_id: int | None
    woo_variation_id: int | None
    sku: str
    barcode: str
    name: str
    quantity_ordered: Decimal
    unit_price: Decimal | None
    line_subtotal: Decimal | None
    line_total: Decimal | None
    line_tax: Decimal | None
    raw_payload: dict[str, Any]


@dataclass
class NormalizedWooOrder:
    woo_order_id: int
    woo_order_number: str
    woo_status: str
    local_status: str
    currency: str
    customer_id: int | None
    customer_email: str
    customer_first_name: str
    customer_last_name: str
    customer_phone: str
    billing_summary: dict[str, Any]
    shipping_summary: dict[str, Any]
    payment_method: str
    payment_method_title: str
    subtotal: Decimal | None
    discount_total: Decimal | None
    shipping_total: Decimal | None
    tax_total: Decimal | None
    total: Decimal | None
    date_created: datetime | None
    date_modified: datetime | None
    date_paid: datetime | None
    date_completed: datetime | None
    lines: list[NormalizedWooOrderLine]
    raw_payload: dict[str, Any]

    @property
    def customer_name(self) -> str:
        return " ".join(part for part in [self.customer_first_name, self.customer_last_name] if part).strip()


@dataclass
class OrderLineSyncIssue:
    preview_line: WooCommerceOrderPreviewLine | None
    message: str


def preview_order_sync(db: Session, client: WooCommerceClient, payload: WooCommerceOrderSyncRequest) -> WooCommerceOrderPreviewResponse:
    if not client.configured:
        return WooCommerceOrderPreviewResponse(
            configured=False,
            total_remote_records=0,
            create_count=0,
            update_count=0,
            matched_count=0,
            skipped_count=0,
            conflict_count=0,
            error_count=0,
            available_count=0,
            partial_count=0,
            unavailable_count=0,
            unknown_count=0,
            errors=["WooCommerce credentials are not configured."],
        )
    try:
        remote_orders = client.fetch_all_orders(
            statuses=order_statuses(payload),
            limit=payload.limit,
            after=payload.after,
            before=payload.before,
            modified_after=payload.modified_after,
            modified_before=payload.modified_before,
        )
    except WooCommerceClientError as error:
        return WooCommerceOrderPreviewResponse(
            configured=True,
            total_remote_records=0,
            create_count=0,
            update_count=0,
            matched_count=0,
            skipped_count=0,
            conflict_count=0,
            error_count=1,
            available_count=0,
            partial_count=0,
            unavailable_count=0,
            unknown_count=0,
            errors=[error.message],
        )
    rows = [build_order_preview(db, normalize_order(order), order_statuses(payload)) for order in remote_orders]
    return build_order_preview_response(True, rows)


def commit_order_sync(db: Session, client: WooCommerceClient, payload: WooCommerceOrderSyncRequest) -> tuple[WooCommerceSyncRun | None, WooCommerceOrderPreviewResponse]:
    if not client.configured:
        return None, preview_order_sync(db, client, payload)
    try:
        remote_orders = client.fetch_all_orders(
            statuses=order_statuses(payload),
            limit=payload.limit,
            after=payload.after,
            before=payload.before,
            modified_after=payload.modified_after,
            modified_before=payload.modified_before,
        )
    except WooCommerceClientError as error:
        return None, order_sync_error_response(error.message)
    return commit_remote_order_records(db, remote_orders, order_statuses(payload), payload.created_by or "system")


def commit_recent_order_sync(db: Session, client: WooCommerceClient, payload: WooCommerceOrderSyncRequest, per_status_limit: int = 10) -> tuple[WooCommerceSyncRun | None, WooCommerceOrderPreviewResponse]:
    if not client.configured:
        return None, preview_order_sync(db, client, payload)
    statuses = order_statuses(payload)
    seen: set[int] = set()
    remote_orders: list[dict[str, Any]] = []
    try:
        for status in statuses:
            for order in client.list_orders(page=1, per_page=per_status_limit, status=status, after=payload.after, before=payload.before, modified_after=payload.modified_after, modified_before=payload.modified_before):
                order_id = to_int_or_none(order.get("id"))
                if order_id is None or order_id in seen:
                    continue
                seen.add(order_id)
                remote_orders.append(order)
    except WooCommerceClientError as error:
        return None, order_sync_error_response(error.message)
    remote_orders.sort(key=order_recency_sort_key, reverse=True)
    if payload.limit:
        remote_orders = remote_orders[: payload.limit]
    return commit_remote_order_records(db, remote_orders, statuses, payload.created_by or "auto-order-poll")


def count_pick_ready_operational_orders(db: Session) -> int:
    """Count the current pick-ready queue without hydrating orders or lines."""
    return int(
        db.scalar(
            select(func.count(Order.id)).where(
                operational_order_clause(),
                Order.pick_status.in_(PICK_READY_STATUSES),
            )
        )
        or 0
    )


def commit_remote_order_records(
    db: Session,
    remote_orders: list[dict[str, Any]],
    requested_statuses: list[str],
    created_by: str,
    *,
    commit: bool = True,
    snapshot_only: bool = False,
) -> tuple[WooCommerceSyncRun, WooCommerceOrderPreviewResponse]:
    acquire_order_import_transaction_lock(db)
    prune_sync_errors(db)
    started_at = datetime.now(timezone.utc)
    normalized_orders = [normalize_order(order) for order in remote_orders]
    if snapshot_only:
        for order in normalized_orders:
            order.local_status = order.woo_status or "synced"
    preview_rows = [build_order_preview(db, order, requested_statuses) for order in normalized_orders]
    preview = build_order_preview_response(True, preview_rows)
    if not snapshot_only:
        lock_inventory_stock(
            db,
            {
                line.item_id
                for preview_order in preview_rows
                for line in preview_order.lines
                if line.item_id is not None
            },
        )
    sync_run = WooCommerceSyncRun(sync_type="orders", status="completed", started_at=started_at, created_by=created_by, total_remote_records=preview.total_remote_records)
    db.add(sync_run)
    db.flush()
    created_count = updated_count = matched_count = skipped_count = conflict_count = error_count = 0
    auto_allocated_count = allocation_exception_count = pick_ready_count = 0
    commit_errors: list[str] = []
    now = datetime.now(timezone.utc)

    for record, preview_order in zip(normalized_orders, preview_rows, strict=False):
        if preview_order.action == "skip":
            skipped_count += 1
            store_order_sync_error(db, sync_run.id, preview_order, None, preview_order.warnings or preview_order.errors or ["Order status was not requested for this sync."])
            continue
        try:
            issue_messages: list[str] = []
            with db.begin_nested():
                # Load the prior payload in the existing lookup so assigning an
                # identical Woo snapshot remains a true no-op for metric caches.
                order = db.scalars(select(Order).where(Order.woo_order_id == record.woo_order_id).options(selectinload(Order.items))).one_or_none()
                is_new_order = order is None
                if snapshot_only and order is not None and not order.is_historical_snapshot:
                    updated_count += 1
                    matched_count += sum(1 for line in preview_order.lines if line.matched_status == "matched")
                    conflict_count += sum(1 for line in preview_order.lines if line.matched_status == "conflict")
                    error_count += sum(1 for line in preview_order.lines if line.matched_status in {"unmatched", "conflict"})
                    continue
                if order is not None and order.is_historical_snapshot:
                    order.historical_source_present = True
                if not snapshot_only and order is not None and order.is_historical_snapshot and is_operational_record(record):
                    order.is_historical_snapshot = False
                preserve_local_workflow = order is not None and (snapshot_only or is_locally_terminal_order(order))
                previous_woo_status = order.woo_status if order is not None else None
                if order is None:
                    order = Order(woo_order_id=record.woo_order_id)
                    db.add(order)
                update_local_order(order, record, preview_order, now, preserve_local_workflow=preserve_local_workflow)
                if snapshot_only and is_new_order:
                    order.is_historical_snapshot = True
                db.flush()
                line_sync_issues, reconciliation_notes = upsert_order_lines(db, order, record, preview_order)
                if not snapshot_only and previous_woo_status and previous_woo_status != record.woo_status:
                    reconciliation_notes.append(
                        f"WooCommerce status changed from {previous_woo_status} to {record.woo_status}."
                    )
                for note in reconciliation_notes:
                    order.workflow_notes = append_note(order.workflow_notes, f"Woo reconciliation: {note}")
                if line_sync_issues:
                    issue_messages = [issue.message for issue in line_sync_issues]
                    order.sync_status = "needs_review"
                    order.sync_error = " ".join(issue_messages)
                    if not snapshot_only:
                        order.allocation_status = "exception"
                        order.allocation_exception_reason = WOO_QUANTITY_BELOW_ALLOCATED_REASON
                    for issue in line_sync_issues:
                        store_order_sync_error(db, sync_run.id, preview_order, issue.preview_line, [issue.message])
                elif order.allocation_exception_reason == WOO_QUANTITY_BELOW_ALLOCATED_REASON:
                    order.allocation_exception_reason = None
                db.flush()
                db.expire(order, ["items"])
                if snapshot_only and is_new_order:
                    order.allocation_status = "unallocated"
                    order.pick_status = "not_ready"
                    order.completion_status = record.local_status
                    for line in order.items:
                        line.quantity_allocated = Decimal("0")
                        line.quantity_picked = Decimal("0")
                        line.quantity_fulfilled = Decimal("0")
                        line.quantity_stock_reduced = Decimal("0")
                        line.allocated_qty = Decimal("0")
                        line.picked_qty = Decimal("0")
                        line.fulfilled_qty = Decimal("0")
                        line.allocation_status = "unallocated"
                        line.pick_status = "not_ready"
                        line.status = record.local_status
                elif (
                    not snapshot_only
                    and not is_operational_record(record)
                    and not (
                        order.completion_status == "picking_recovery"
                        and record.woo_status == "completed"
                    )
                ):
                    released_quantity = release_unpicked_allocations(
                        db,
                        order,
                        f"WooCommerce status changed to {record.woo_status}; released unpicked allocation.",
                        "woocommerce_status_change",
                    )
                    if released_quantity > 0:
                        order.workflow_notes = append_note(
                            order.workflow_notes,
                            f"Woo reconciliation: released {released_quantity} unpicked units after status changed to {record.woo_status}.",
                        )
                    order.local_status = record.local_status
                    if order.completion_status == "cancellation_pending":
                        # A processing snapshot must not clear the local guard while
                        # Woo cancellation is in flight. Once Woo reaches a terminal
                        # status, however, that remote source of truth resolves it.
                        order.completion_status = record.local_status
                    elif not preserve_local_workflow:
                        order.completion_status = record.local_status
                if not snapshot_only:
                    sync_order_workflow_statuses(order)
                for line in preview_order.lines:
                    if line.matched_status in {"unmatched", "conflict"}:
                        store_order_sync_error(db, sync_run.id, preview_order, line, line.errors or line.warnings or [f"Order line is {line.matched_status}."])
            created_count += int(is_new_order)
            updated_count += int(not is_new_order)
            matched_count += sum(1 for line in preview_order.lines if line.matched_status == "matched")
            conflict_count += sum(1 for line in preview_order.lines if line.matched_status == "conflict")
            error_count += sum(1 for line in preview_order.lines if line.matched_status in {"unmatched", "conflict"})
            error_count += len(issue_messages)
            if not snapshot_only:
                allocation_exception_count += int(bool(issue_messages))
            commit_errors.extend(issue_messages)
        except Exception as exc:
            if not commit:
                raise
            error_count += 1
            commit_errors.append(str(exc))
            store_order_sync_error(db, sync_run.id, preview_order, None, [str(exc)])

    if not snapshot_only:
        fifo_summary = auto_allocate_processing_orders_fifo(db, source=created_by or "order-sync")
        auto_allocated_count = fifo_summary["allocated_orders"]
        allocation_exception_count = max(
            allocation_exception_count,
            fifo_summary["partially_allocated_orders"] + fifo_summary["exception_orders"],
        )
        pick_ready_count = count_pick_ready_operational_orders(db)
        if fifo_summary["errors"]:
            error_count += len(fifo_summary["errors"])
            commit_errors.extend(fifo_summary["errors"])

    sync_run.created_count = created_count
    sync_run.updated_count = updated_count
    sync_run.matched_count = matched_count
    sync_run.skipped_count = skipped_count
    sync_run.conflict_count = conflict_count
    sync_run.error_count = error_count
    sync_run.completed_at = datetime.now(timezone.utc)
    sync_run.status = "completed_with_errors" if conflict_count or error_count else "completed"
    if commit:
        db.commit()
        db.refresh(sync_run)
    else:
        db.flush()
    response = WooCommerceOrderPreviewResponse(
        configured=True,
        total_remote_records=preview.total_remote_records,
        create_count=created_count,
        update_count=updated_count,
        matched_count=matched_count,
        skipped_count=skipped_count,
        conflict_count=conflict_count,
        error_count=error_count,
        available_count=preview.available_count,
        partial_count=preview.partial_count,
        unavailable_count=preview.unavailable_count,
        unknown_count=preview.unknown_count,
        auto_allocated_count=auto_allocated_count,
        allocation_exception_count=allocation_exception_count,
        unmatched_line_count=sum(1 for row in preview_rows for line in row.lines if line.matched_status == "unmatched"),
        conflict_line_count=conflict_count,
        pick_ready_count=pick_ready_count,
        warnings=preview.warnings,
        errors=[*preview.errors, *commit_errors],
        preview_orders=[],
    )
    return sync_run, response


def order_sync_error_response(message: str) -> WooCommerceOrderPreviewResponse:
    return WooCommerceOrderPreviewResponse(
        configured=True,
        total_remote_records=0,
        create_count=0,
        update_count=0,
        matched_count=0,
        skipped_count=0,
        conflict_count=0,
        error_count=1,
        available_count=0,
        partial_count=0,
        unavailable_count=0,
        unknown_count=0,
        errors=[message],
    )


def acquire_order_import_transaction_lock(db: Session) -> None:
    """Serialize order imports on PostgreSQL for the life of the current transaction."""
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": POSTGRES_ORDER_IMPORT_LOCK_KEY})


def is_locally_terminal_order(order: Order) -> bool:
    return bool(
        order.completed_at
        or order.closed_at
        or order.completed_without_picking
        or order.completion_status == "cancellation_pending"
    )


def is_operational_record(record: NormalizedWooOrder) -> bool:
    return record.woo_status == "processing" or (
        record.woo_status == "completed" and record.payment_method.strip().casefold().startswith("foosales")
    )


def order_recency_sort_key(order: dict[str, Any]) -> datetime:
    return parse_datetime(order.get("date_modified_gmt") or order.get("date_created_gmt")) or datetime.min.replace(tzinfo=timezone.utc)


def build_order_preview(db: Session, record: NormalizedWooOrder, requested_statuses: list[str]) -> WooCommerceOrderPreviewOrder:
    local_order = db.scalars(select(Order).where(Order.woo_order_id == record.woo_order_id)).one_or_none()
    action = "update" if local_order else "create"
    warnings: list[str] = []
    errors: list[str] = []
    if record.woo_status not in requested_statuses:
        action = "skip"
        warnings.append(f"WooCommerce status {record.woo_status or 'unknown'} was not requested for this sync.")
    elif record.woo_status not in OPEN_WOO_STATUSES and not is_operational_record(record):
        warnings.append(f"WooCommerce status {record.woo_status or 'unknown'} will be stored as a read-only local snapshot, not an open operational order.")
    lines = [build_line_preview(db, line) for line in record.lines]
    matched_status = aggregate_matched_status(lines)
    availability_status = aggregate_availability_status(lines)
    if matched_status == "conflict":
        errors.append("One or more order lines match conflicting local items.")
    return WooCommerceOrderPreviewOrder(
        woo_order_id=record.woo_order_id,
        woo_order_number=record.woo_order_number,
        woo_status=record.woo_status,
        local_order_id=local_order.id if local_order else None,
        action=action,
        local_status=record.local_status,
        customer_name=record.customer_name,
        customer_email=record.customer_email,
        currency=record.currency,
        total=float(record.total) if record.total is not None else None,
        date_created=record.date_created,
        date_modified=record.date_modified,
        matched_status=matched_status,
        availability_status=availability_status,
        line_count=len(lines),
        warnings=warnings,
        errors=errors,
        lines=lines,
    )


def build_line_preview(db: Session, line: NormalizedWooOrderLine) -> WooCommerceOrderPreviewLine:
    warnings: list[str] = []
    errors: list[str] = []
    item = find_matching_item_for_line(db, line, errors)
    matched_status = "matched" if item else "unmatched"
    if errors:
        matched_status = "conflict"
    sellable_snapshot = Decimal("0")
    shortage_quantity = line.quantity_ordered
    availability_status = "unknown"
    if item and not errors:
        sellable_snapshot = (item.in_stock or Decimal("0")) - (item.allocated or Decimal("0"))
        shortage_quantity = max(line.quantity_ordered - sellable_snapshot, Decimal("0"))
        if sellable_snapshot >= line.quantity_ordered:
            availability_status = "available"
        elif sellable_snapshot > 0:
            availability_status = "partial"
        else:
            availability_status = "unavailable"
    elif not item:
        warnings.append("Order line could not be matched to a local inventory item.")
    return WooCommerceOrderPreviewLine(
        woo_line_item_id=line.woo_line_item_id,
        woo_product_id=line.woo_product_id,
        woo_variation_id=line.woo_variation_id,
        item_id=item.id if item and not errors else None,
        sku=line.sku,
        barcode=line.barcode,
        name=line.name,
        quantity_ordered=float(line.quantity_ordered),
        matched_status=matched_status,
        availability_status=availability_status,
        sellable_snapshot=float(sellable_snapshot),
        shortage_quantity=float(shortage_quantity),
        warnings=warnings,
        errors=errors,
    )


def build_order_preview_response(configured: bool, rows: list[WooCommerceOrderPreviewOrder]) -> WooCommerceOrderPreviewResponse:
    return WooCommerceOrderPreviewResponse(
        configured=configured,
        total_remote_records=len(rows),
        create_count=sum(1 for row in rows if row.action == "create"),
        update_count=sum(1 for row in rows if row.action == "update"),
        matched_count=sum(1 for row in rows for line in row.lines if line.matched_status == "matched"),
        skipped_count=sum(1 for row in rows if row.action == "skip"),
        conflict_count=sum(1 for row in rows for line in row.lines if line.matched_status == "conflict"),
        error_count=sum(1 for row in rows for line in row.lines if line.matched_status in {"unmatched", "conflict"}),
        available_count=sum(1 for row in rows if row.availability_status == "available"),
        partial_count=sum(1 for row in rows if row.availability_status == "partial"),
        unavailable_count=sum(1 for row in rows if row.availability_status == "unavailable"),
        unknown_count=sum(1 for row in rows if row.availability_status == "unknown"),
        warnings=[warning for row in rows for warning in row.warnings] + [warning for row in rows for line in row.lines for warning in line.warnings],
        errors=[error for row in rows for error in row.errors] + [error for row in rows for line in row.lines for error in line.errors],
        preview_orders=rows,
    )


def order_statuses(payload: WooCommerceOrderSyncRequest) -> list[str]:
    statuses = payload.include_statuses or get_settings().default_order_sync_statuses
    return [status.strip() for status in statuses if status.strip()]


def normalize_order(order: dict[str, Any]) -> NormalizedWooOrder:
    billing = order.get("billing") or {}
    shipping = order.get("shipping") or {}
    woo_status = str(order.get("status") or "")
    payment_method = str(order.get("payment_method") or "")
    operational = woo_status == "processing" or (
        woo_status == "completed" and payment_method.strip().casefold().startswith("foosales")
    )
    return NormalizedWooOrder(
        woo_order_id=int(order.get("id")),
        woo_order_number=str(order.get("number") or order.get("id") or ""),
        woo_status=woo_status,
        local_status="open" if woo_status in OPEN_WOO_STATUSES or operational else (woo_status or "synced"),
        currency=str(order.get("currency") or ""),
        customer_id=to_int_or_none(order.get("customer_id")),
        customer_email=str(billing.get("email") or order.get("billing_email") or ""),
        customer_first_name=str(billing.get("first_name") or ""),
        customer_last_name=str(billing.get("last_name") or ""),
        customer_phone=str(billing.get("phone") or shipping.get("phone") or ""),
        billing_summary=address_summary(billing),
        shipping_summary=address_summary(shipping),
        payment_method=payment_method,
        payment_method_title=str(order.get("payment_method_title") or ""),
        subtotal=calculate_subtotal(order),
        discount_total=to_decimal_or_none(order.get("discount_total")),
        shipping_total=to_decimal_or_none(order.get("shipping_total")),
        tax_total=to_decimal_or_none(order.get("total_tax")),
        total=to_decimal_or_none(order.get("total")),
        date_created=parse_datetime(order.get("date_created_gmt") or order.get("date_created")),
        date_modified=parse_datetime(order.get("date_modified_gmt") or order.get("date_modified")),
        date_paid=parse_datetime(order.get("date_paid_gmt") or order.get("date_paid")),
        date_completed=parse_datetime(order.get("date_completed_gmt") or order.get("date_completed")),
        lines=[normalize_line(line) for line in order.get("line_items") or []],
        raw_payload=order,
    )


def normalize_line(line: dict[str, Any]) -> NormalizedWooOrderLine:
    quantity = to_decimal(line.get("quantity"))
    total = to_decimal_or_none(line.get("total"))
    unit_price = (total / quantity) if total is not None and quantity else to_decimal_or_none(line.get("price"))
    return NormalizedWooOrderLine(
        woo_line_item_id=to_int_or_none(line.get("id")),
        woo_product_id=to_int_or_none(line.get("product_id")),
        woo_variation_id=to_int_or_none(line.get("variation_id")),
        sku=str(line.get("sku") or "").strip(),
        barcode=extract_line_barcode(line),
        name=str(line.get("name") or ""),
        quantity_ordered=quantity,
        unit_price=unit_price,
        line_subtotal=to_decimal_or_none(line.get("subtotal")),
        line_total=total,
        line_tax=to_decimal_or_none(line.get("total_tax") or line.get("subtotal_tax")),
        raw_payload=line,
    )


def find_matching_item_for_line(db: Session, line: NormalizedWooOrderLine, errors: list[str]) -> InventoryItem | None:
    candidates: list[InventoryItem] = []
    matches: list[tuple[str, list[InventoryItem]]] = []
    if line.woo_product_id:
        statement = select(InventoryItem).where(InventoryItem.woo_product_id == line.woo_product_id)
        if line.woo_variation_id:
            statement = statement.where(InventoryItem.woo_variation_id == line.woo_variation_id)
        else:
            statement = statement.where(InventoryItem.woo_variation_id.is_(None))
        matches.append(("WooCommerce identity", list(db.scalars(statement.limit(2)).all())))
    if line.sku:
        matches.append(("SKU", list(db.scalars(select(InventoryItem).where(InventoryItem.sku == line.sku).limit(2)).all())))
    if line.barcode:
        matches.append(("Barcode", list(db.scalars(select(InventoryItem).where(InventoryItem.barcode == line.barcode).limit(2)).all())))
    for label, key_matches in matches:
        if len(key_matches) > 1:
            errors.append(f"Duplicate {label} matches multiple local items; allocation was blocked.")
            return None
        candidates.extend(key_matches)
    if len({candidate.id for candidate in candidates}) > 1:
        errors.append("WooCommerce IDs, SKU, or Barcode match different local items.")
        return None
    return candidates[0] if candidates else None


def update_local_order(
    order: Order,
    record: NormalizedWooOrder,
    preview: WooCommerceOrderPreviewOrder,
    synced_at: datetime,
    *,
    preserve_local_workflow: bool = False,
) -> None:
    order.woo_order_number = record.woo_order_number
    order.woo_status = record.woo_status
    if not preserve_local_workflow:
        order.local_status = record.local_status
    order.currency = record.currency
    order.customer_id = record.customer_id
    order.customer_email = record.customer_email
    order.customer_first_name = record.customer_first_name
    order.customer_last_name = record.customer_last_name
    order.customer_phone = record.customer_phone
    order.billing_summary = record.billing_summary
    order.shipping_summary = record.shipping_summary
    order.payment_method = record.payment_method
    order.payment_method_title = record.payment_method_title
    order.subtotal = record.subtotal
    order.discount_total = record.discount_total
    order.shipping_total = record.shipping_total
    order.tax_total = record.tax_total
    order.total = record.total
    order.date_created = record.date_created
    order.date_modified = record.date_modified
    order.date_paid = record.date_paid
    order.date_completed = record.date_completed
    order.sync_status = "synced" if preview.matched_status != "conflict" else "conflict"
    order.sync_error = " ".join(preview.errors) if preview.errors else None
    order.last_synced_at = synced_at
    order.order_number = record.woo_order_number
    order.customer_name = record.customer_name
    order.placed_on = record.date_created
    order.completed_on = record.date_completed
    order.status = record.woo_status
    if not preserve_local_workflow:
        order.allocation_status = preview.availability_status
        order.pick_status = order.pick_status or "not_ready"
        order.completion_status = "open" if record.local_status == "open" else record.local_status
    order.shipping_address_1 = record.shipping_summary.get("address_1")
    order.shipping_address_2 = record.shipping_summary.get("address_2")
    order.shipping_city = record.shipping_summary.get("city")
    order.shipping_state = record.shipping_summary.get("state")
    order.shipping_country = record.shipping_summary.get("country")
    order.shipping_zip = record.shipping_summary.get("postcode")
    order.shipping_phone = record.shipping_summary.get("phone")
    order.billing_address_1 = record.billing_summary.get("address_1")
    order.billing_address_2 = record.billing_summary.get("address_2")
    order.billing_city = record.billing_summary.get("city")
    order.billing_state = record.billing_summary.get("state")
    order.billing_country = record.billing_summary.get("country")
    order.billing_zip = record.billing_summary.get("postcode")
    order.billing_phone = record.billing_summary.get("phone")
    order.company = record.billing_summary.get("company") or record.shipping_summary.get("company")
    order.raw_woo_payload = record.raw_payload


def upsert_order_lines(
    db: Session,
    order: Order,
    record: NormalizedWooOrder,
    preview: WooCommerceOrderPreviewOrder,
) -> tuple[list[OrderLineSyncIssue], list[str]]:
    existing_by_line_id = {line.woo_order_item_id: line for line in order.items if line.woo_order_item_id is not None}
    preview_by_line_id = {line.woo_line_item_id: line for line in preview.lines}
    remote_line_ids = {line.woo_line_item_id for line in record.lines}
    issues: list[OrderLineSyncIssue] = []
    reconciliation_notes: list[str] = []
    for index, record_line in enumerate(record.lines, start=1):
        preview_line = preview_by_line_id.get(record_line.woo_line_item_id)
        local_line = existing_by_line_id.get(record_line.woo_line_item_id)
        if local_line is not None and local_line.sync_status == "local_removed":
            continue
        if local_line is None:
            local_line = OrderItem(order=order, woo_order_item_id=record_line.woo_line_item_id)
            db.add(local_line)
        previous_ordered = local_line.quantity_ordered or Decimal("0")
        previous_allocated = local_line.quantity_allocated or Decimal("0")
        previous_picked = local_line.quantity_picked or Decimal("0")
        previous_fulfilled = local_line.quantity_fulfilled or Decimal("0")
        previous_stock_reduced = local_line.quantity_stock_reduced or Decimal("0")
        protected_quantity = max(previous_picked, previous_fulfilled, previous_stock_reduced)
        incoming_item_id = preview_line.item_id if preview_line else None
        active_substitution = local_line.substituted_from_inventory_item_id is not None
        prior_woo_identity = (local_line.woo_product_id, local_line.woo_variation_id)
        incoming_woo_identity = (record_line.woo_product_id, record_line.woo_variation_id)
        substituted_woo_identity_changed = active_substitution and prior_woo_identity != incoming_woo_identity
        substituted_quantity_changed = active_substitution and previous_ordered != record_line.quantity_ordered
        substitution_requires_review = substituted_woo_identity_changed or substituted_quantity_changed
        mapping_changed = substitution_requires_review or (
            not active_substitution
            and local_line.inventory_item_id is not None
            and incoming_item_id is not None
            and local_line.inventory_item_id != incoming_item_id
        )
        allocation_floor = protected_quantity if mapping_changed else max(record_line.quantity_ordered, protected_quantity)
        release_requested = max(previous_allocated - allocation_floor, Decimal("0"))
        released = Decimal("0")
        if release_requested > 0:
            released = release_line_allocations(
                db,
                order,
                local_line,
                release_requested,
                (
                    f"WooCommerce order line {record_line.woo_line_item_id} changed; "
                    "released its unpicked excess allocation."
                ),
                "woocommerce_line_change",
            )
            if released > 0:
                if substituted_quantity_changed:
                    reconciliation_notes.append(
                        f"Line {record_line.woo_line_item_id} quantity changed after local substitution; "
                        f"released {released} unpicked units and requires review."
                    )
                elif mapping_changed:
                    reconciliation_notes.append(
                        f"Line {record_line.woo_line_item_id} changed inventory item from "
                        f"{local_line.inventory_item_id} to {incoming_item_id}; released {released} unpicked units."
                    )
                else:
                    reconciliation_notes.append(
                        f"Line {record_line.woo_line_item_id} quantity changed from {previous_ordered} to "
                        f"{record_line.quantity_ordered}; released {released} unpicked units."
                    )
        elif previous_ordered != record_line.quantity_ordered:
            reconciliation_notes.append(
                f"Line {record_line.woo_line_item_id} quantity changed from {previous_ordered} to "
                f"{record_line.quantity_ordered}; FIFO allocation will reconcile any additional requirement."
            )
        if mapping_changed and released == 0:
            if substituted_quantity_changed:
                reconciliation_notes.append(
                    f"Line {record_line.woo_line_item_id} quantity changed after local substitution; "
                    "no unpicked allocation was released and review is required."
                )
            else:
                reconciliation_notes.append(
                    f"Line {record_line.woo_line_item_id} changed inventory item from "
                    f"{local_line.inventory_item_id} to {incoming_item_id}; no unpicked allocation was released."
                )
        local_line.woo_product_id = record_line.woo_product_id
        local_line.woo_variation_id = record_line.woo_variation_id
        mapping_change_requires_review = substitution_requires_review or (
            mapping_changed
            and (protected_quantity > 0 or (local_line.quantity_allocated or Decimal("0")) > protected_quantity)
        )
        local_line.inventory_item_id = (
            local_line.inventory_item_id
            if active_substitution or mapping_change_requires_review
            else incoming_item_id
        )
        local_line.line_number = index
        local_line.sku = record_line.sku
        local_line.barcode = record_line.barcode
        local_line.description = record_line.name
        local_line.name = record_line.name
        existing_allocated = local_line.quantity_allocated or Decimal("0")
        existing_picked = local_line.quantity_picked or Decimal("0")
        existing_fulfilled = local_line.quantity_fulfilled or Decimal("0")
        existing_stock_reduced = local_line.quantity_stock_reduced or Decimal("0")
        protected_quantity = max(existing_picked, existing_fulfilled, existing_stock_reduced)
        quantity_below_processed = protected_quantity > record_line.quantity_ordered
        allocation_still_exceeds_order = existing_allocated > max(record_line.quantity_ordered, protected_quantity)
        local_line.quantity_ordered = record_line.quantity_ordered
        local_line.quantity_allocated = existing_allocated
        local_line.quantity_picked = existing_picked
        local_line.quantity_fulfilled = existing_fulfilled
        local_line.quantity_stock_reduced = existing_stock_reduced
        local_line.ordered_qty = record_line.quantity_ordered
        local_line.allocated_qty = existing_allocated
        local_line.picked_qty = existing_picked
        local_line.fulfilled_qty = existing_fulfilled
        local_line.unit_price = record_line.unit_price
        local_line.line_subtotal = record_line.line_subtotal
        local_line.line_total = record_line.line_total
        local_line.line_tax = record_line.line_tax
        local_line.total_price = record_line.line_total
        effective_item = db.get(InventoryItem, local_line.inventory_item_id) if local_line.inventory_item_id else None
        effective_matched_status = (
            "matched"
            if active_substitution and not substitution_requires_review and effective_item is not None
            else (preview_line.matched_status if preview_line else "unknown")
        )
        effective_availability_status = (
            "available"
            if active_substitution and not substitution_requires_review and effective_item is not None
            and (effective_item.sellable or Decimal("0")) >= max(record_line.quantity_ordered - existing_allocated, Decimal("0"))
            else (
                "partial"
                if active_substitution and not substitution_requires_review and effective_item is not None
                and (effective_item.sellable or Decimal("0")) > 0
                else (preview_line.availability_status if preview_line else "unknown")
            )
        )
        local_line.matched_status = effective_matched_status
        local_line.availability_status = "allocated" if existing_allocated >= record_line.quantity_ordered else effective_availability_status
        local_line.allocation_status = "allocated" if existing_allocated >= record_line.quantity_ordered else effective_availability_status
        local_line.pick_status = "picked" if existing_allocated > 0 and existing_picked >= existing_allocated else ("partially_picked" if existing_picked > 0 else "not_ready")
        local_line.sellable_snapshot = (
            effective_item.sellable or Decimal("0")
            if active_substitution and not substitution_requires_review and effective_item is not None
            else (Decimal(str(preview_line.sellable_snapshot)) if preview_line else Decimal("0"))
        )
        remaining_after_allocation = max(record_line.quantity_ordered - existing_allocated, Decimal("0"))
        local_line.shortage_quantity = max(remaining_after_allocation - local_line.sellable_snapshot, Decimal("0")) if preview_line else remaining_after_allocation
        local_line.sync_status = (
            "substituted"
            if active_substitution and not substitution_requires_review
            else ("synced" if preview_line and preview_line.matched_status == "matched" else "needs_review")
        )
        local_line.sync_error = (
            None
            if active_substitution and not substitution_requires_review
            else " ".join((preview_line.errors or preview_line.warnings) if preview_line else ["Preview line missing."])
        )
        if quantity_below_processed or allocation_still_exceeds_order or mapping_change_requires_review:
            if mapping_change_requires_review:
                if substituted_quantity_changed:
                    message = (
                        f"WooCommerce changed line {record_line.woo_line_item_id} quantity from {previous_ordered} "
                        f"to {record_line.quantity_ordered} after a local product substitution; the substitution "
                        "was preserved but picking is blocked pending review."
                    )
                elif substituted_woo_identity_changed:
                    message = (
                        f"WooCommerce changed line {record_line.woo_line_item_id} product or variation after a "
                        "local product substitution; the effective replacement was preserved but picking is "
                        "blocked pending review."
                    )
                elif protected_quantity > 0:
                    message = (
                        f"WooCommerce changed line {record_line.woo_line_item_id} to another inventory item after "
                        f"{protected_quantity} units were picked, fulfilled, or stock-reduced; the original item "
                        "history was preserved and requires review."
                    )
                else:
                    message = (
                        f"WooCommerce changed line {record_line.woo_line_item_id} to another inventory item, but its "
                        "old allocation could not be fully released; the original item mapping was preserved for review."
                    )
            elif quantity_below_processed:
                message = (
                    f"WooCommerce quantity decreased to {record_line.quantity_ordered} after {protected_quantity} "
                    "was already picked, fulfilled, or stock-reduced; history was preserved and requires review."
                )
            else:
                message = (
                    f"WooCommerce quantity decreased to {record_line.quantity_ordered}, but "
                    f"{existing_allocated} units remain allocated because the allocation could not be fully released."
                )
            local_line.allocation_status = "exception"
            local_line.allocation_exception_reason = WOO_QUANTITY_BELOW_ALLOCATED_REASON
            local_line.sync_status = "needs_review"
            local_line.sync_error = message
            issues.append(OrderLineSyncIssue(preview_line=preview_line, message=message))
        elif local_line.allocation_exception_reason == WOO_QUANTITY_BELOW_ALLOCATED_REASON:
            local_line.allocation_exception_reason = None
        local_line.status = record.local_status

    for local_line in order.items:
        if local_line.sync_status == "local_removed":
            continue
        if local_line.woo_order_item_id is None or local_line.woo_order_item_id in remote_line_ids:
            continue
        previous_ordered = local_line.quantity_ordered or Decimal("0")
        previous_allocated = local_line.quantity_allocated or Decimal("0")
        protected_quantity = max(
            local_line.quantity_picked or Decimal("0"),
            local_line.quantity_fulfilled or Decimal("0"),
            local_line.quantity_stock_reduced or Decimal("0"),
        )
        released = release_line_allocations(
            db,
            order,
            local_line,
            max(previous_allocated - protected_quantity, Decimal("0")),
            f"WooCommerce removed order line {local_line.woo_order_item_id}; released its unpicked allocation.",
            "woocommerce_line_removed",
        )
        local_line.quantity_ordered = Decimal("0")
        local_line.ordered_qty = Decimal("0")
        local_line.shortage_quantity = Decimal("0")
        local_line.matched_status = "removed"
        local_line.availability_status = "removed"
        local_line.allocation_status = "removed" if protected_quantity == 0 and local_line.quantity_allocated == 0 else "exception"
        local_line.pick_status = "picked" if protected_quantity > 0 else "not_ready"
        local_line.status = RETIRED_WOO_LINE_STATUS
        local_line.sync_status = "needs_review" if protected_quantity > 0 or local_line.quantity_allocated > 0 else "synced"
        local_line.sync_error = (
            f"WooCommerce removed this line after {protected_quantity} units were already picked, fulfilled, or "
            "stock-reduced; history was preserved and requires review."
            if protected_quantity > 0
            else "WooCommerce removed this line; its unpicked allocation was released and the local history was retained."
        )
        reconciliation_notes.append(
            f"Line {local_line.woo_order_item_id} was removed from WooCommerce; retained local history and released "
            f"{released} of {previous_allocated} allocated units."
        )
        if protected_quantity > 0 or local_line.quantity_allocated > 0:
            local_line.allocation_exception_reason = WOO_QUANTITY_BELOW_ALLOCATED_REASON
            issues.append(OrderLineSyncIssue(preview_line=None, message=local_line.sync_error))
        else:
            local_line.allocation_exception_reason = None
    return issues, reconciliation_notes


def _active_order_clause(*, normalize_operational: bool = False):
    if normalize_operational:
        # Woo operational status plus final local completion is the source of
        # truth. Older cached local statuses are normalized after ingestion.
        return ~func.coalesce(Order.completion_status, "").in_(("completed", "completed_without_picking"))
    closed_local_statuses = COMPLETED_LOCAL_STATUSES
    closed_local_statuses = closed_local_statuses | {"cancelled", "canceled", "failed", "refunded"}
    return and_(
        ~func.coalesce(Order.completion_status, "").in_(("completed", "completed_without_picking")),
        ~func.coalesce(Order.local_status, "").in_(tuple(closed_local_statuses)),
    )


def _order_line_exists(*predicates, include_inventory: bool = False):
    statement = select(1).select_from(OrderItem)
    if include_inventory:
        statement = statement.outerjoin(InventoryItem, InventoryItem.id == OrderItem.inventory_item_id)
    return exists(statement.where(OrderItem.order_id == Order.id, *predicates))


def _aggregate_availability_expression():
    has_lines = _order_line_exists()
    status = func.coalesce(OrderItem.availability_status, "")
    return case(
        (~has_lines, "unknown"),
        (_order_line_exists(status == "unknown"), "unknown"),
        (and_(has_lines, ~_order_line_exists(status != "allocated")), "allocated"),
        (_order_line_exists(status == "unavailable"), "unavailable"),
        (_order_line_exists(status == "partial"), "partial"),
        (and_(has_lines, ~_order_line_exists(status != "available")), "available"),
        else_="unknown",
    )


def _aggregate_matched_expression():
    has_lines = _order_line_exists()
    status = func.coalesce(OrderItem.matched_status, "")
    return case(
        (_order_line_exists(status == "conflict"), "conflict"),
        (_order_line_exists(status == "unmatched"), "unmatched"),
        (and_(has_lines, ~_order_line_exists(status != "matched")), "matched"),
        else_="unknown",
    )


def _workflow_view_clause(workflow_view: str):
    if workflow_view == "completed":
        return and_(Order.is_historical_snapshot.is_(False), ~_active_order_clause())

    operational = and_(operational_order_clause(), _active_order_clause(normalize_operational=True))
    required_line = and_(
        actionable_order_line_clause(),
        or_(InventoryItem.id.is_(None), InventoryItem.non_inventory.is_(False)),
    )
    blocking_line = _order_line_exists(or_(
        OrderItem.matched_status.in_(tuple(BLOCKING_MATCH_STATUSES)),
        OrderItem.allocation_exception_reason.in_(tuple(BLOCKING_ALLOCATION_EXCEPTION_REASONS)),
    ))
    if workflow_view == "allocate":
        line_needs_attention = _order_line_exists(
            OrderItem.matched_status == "matched",
            required_line,
            func.coalesce(OrderItem.quantity_allocated, 0) < func.coalesce(OrderItem.quantity_ordered, 0),
            include_inventory=True,
        )
        return and_(operational, or_(blocking_line, line_needs_attention))
    if workflow_view == "pick":
        invalid_required_line = _order_line_exists(
            required_line,
            or_(
                func.coalesce(OrderItem.matched_status, "") != "matched",
                func.coalesce(OrderItem.quantity_allocated, 0) < func.coalesce(OrderItem.quantity_ordered, 0),
            ),
            include_inventory=True,
        )
        return and_(
            operational,
            _order_line_exists(required_line, include_inventory=True),
            ~blocking_line,
            ~invalid_required_line,
            _order_line_exists(required_line, func.coalesce(OrderItem.quantity_allocated, 0) > func.coalesce(OrderItem.quantity_picked, 0), include_inventory=True),
        )
    return operational


def _order_text_predicate(value: str, *columns):
    escaped_value = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped_value}%"
    return or_(*(column.ilike(pattern, escape="\\") for column in columns))


def _order_item_text_predicate(value: str):
    return _order_line_exists(
        _order_text_predicate(
            value,
            OrderItem.sku,
            OrderItem.barcode,
            OrderItem.name,
            OrderItem.description,
            InventoryItem.sku,
            InventoryItem.barcode,
            InventoryItem.description,
        ),
        include_inventory=True,
    )


def list_open_orders(
    db: Session,
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    workflow_view: str = "open",
    order_number: str | None = None,
    customer: str | None = None,
    containing_item: str | None = None,
    warehouse: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> OpenOrderListResponse:
    availability_expression = _aggregate_availability_expression()
    matched_expression = _aggregate_matched_expression()
    predicates = [_workflow_view_clause(workflow_view)]
    if search and search.strip():
        predicates.append(or_(
            _order_text_predicate(
                search,
                Order.woo_order_number,
                cast(Order.woo_order_id, String),
                Order.customer_name,
                Order.customer_email,
                Order.customer_phone,
            ),
            _order_item_text_predicate(search),
        ))
    if order_number and order_number.strip():
        predicates.append(_order_text_predicate(order_number, Order.woo_order_number, cast(Order.woo_order_id, String)))
    if customer and customer.strip():
        predicates.append(_order_text_predicate(customer, Order.customer_name))
    if containing_item and containing_item.strip():
        predicates.append(_order_item_text_predicate(containing_item))
    if warehouse and warehouse.strip().casefold() != "main warehouse":
        predicates.append(false())
    if woo_status:
        predicates.append(Order.woo_status == woo_status)
    if availability_status:
        predicates.append(availability_expression == availability_status)
    if matched_status:
        predicates.append(matched_expression == matched_status)

    summary_rows = select(
        Order.id.label("order_id"),
        availability_expression.label("availability_status"),
    ).where(*predicates).subquery()
    total, available_count, partial_count, unavailable_count, unknown_count = db.execute(
        select(
            func.count(summary_rows.c.order_id),
            func.coalesce(func.sum(case((summary_rows.c.availability_status == "available", 1), else_=0)), 0),
            func.coalesce(func.sum(case((summary_rows.c.availability_status == "partial", 1), else_=0)), 0),
            func.coalesce(func.sum(case((summary_rows.c.availability_status == "unavailable", 1), else_=0)), 0),
            func.coalesce(func.sum(case((summary_rows.c.availability_status == "unknown", 1), else_=0)), 0),
        )
    ).one()
    total = int(total or 0)
    pagination_requested = page is not None or page_size is not None
    effective_page_size = page_size or 20
    total_pages = (total + effective_page_size - 1) // effective_page_size if effective_page_size else 0
    effective_page = min(page or 1, max(total_pages, 1)) if pagination_requested else 1
    order_ids_statement = (
        select(Order.id, Order.raw_woo_payload["shipping_lines"].label("shipping_lines"))
        .where(*predicates)
        .order_by(Order.date_created.desc().nullslast(), Order.id.desc())
    )
    if pagination_requested:
        order_ids_statement = order_ids_statement.offset((effective_page - 1) * effective_page_size).limit(effective_page_size)
    order_page = db.execute(order_ids_statement).all()
    order_ids = [row.id for row in order_page]
    shipping_lines_by_order_id = {row.id: row.shipping_lines for row in order_page}
    loaded_orders = list(db.scalars(
        select(Order)
        .where(Order.id.in_(order_ids))
        .options(
            defer(Order.raw_woo_payload, raiseload=True),
            selectinload(Order.items).selectinload(OrderItem.inventory_item),
        )
    ).all()) if order_ids else []
    orders_by_id = {order.id: order for order in loaded_orders}
    orders = [orders_by_id[order_id] for order_id in order_ids]
    for order in orders:
        sync_order_workflow_statuses(order)
    rows = [order_to_read(order, shipping_lines=shipping_lines_by_order_id.get(order.id)) for order in orders]
    if not pagination_requested:
        effective_page_size = len(rows)
        total_pages = 1 if rows else 0
    return OpenOrderListResponse(
        orders=rows,
        total=total,
        available_count=int(available_count or 0),
        partial_count=int(partial_count or 0),
        unavailable_count=int(unavailable_count or 0),
        unknown_count=int(unknown_count or 0),
        page=effective_page,
        page_size=effective_page_size,
        total_pages=total_pages,
        returned_count=len(rows),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


def get_open_order_detail(db: Session, order_id: int) -> OpenOrderDetail | None:
    order = db.scalars(
        select(Order)
        .where(Order.id == order_id, Order.is_historical_snapshot.is_(False))
        .options(
            selectinload(Order.items).selectinload(OrderItem.inventory_item),
            selectinload(Order.items).selectinload(OrderItem.substituted_from_item),
        )
    ).one_or_none()
    if order is None:
        return None
    sync_order_workflow_statuses(order)
    base = order_to_read(order).model_dump()
    base.update(
        {
            "customer_id": order.customer_id,
            "billing_summary": order.billing_summary,
            "shipping_summary": order.shipping_summary,
            "payment_method": order.payment_method,
            "payment_method_title": order.payment_method_title,
            "subtotal": decimal_to_float(order.subtotal),
            "discount_total": decimal_to_float(order.discount_total),
            "shipping_total": decimal_to_float(order.shipping_total),
            "tax_total": decimal_to_float(order.tax_total),
            "customer_note": str((order.raw_woo_payload or {}).get("customer_note") or "").strip() or None,
            "workflow_notes": order.workflow_notes,
            "lines": [
                line_to_read(line)
                for line in sorted(order.items, key=lambda item: item.line_number or item.id)
                if line.sync_status != "local_removed"
            ],
        }
    )
    return OpenOrderDetail.model_validate(base)


def export_open_orders_csv(db: Session, **filters) -> str:
    rows = list_open_orders(db, **filters).orders
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Order ID", "Woo Order ID", "Order Number", "Woo Status", "Local Status", "Customer", "Email", "Total", "Availability", "Matched", "Line Count", "Date Created"])
    for row in rows:
        writer.writerow([row.id, row.woo_order_id, row.woo_order_number, row.woo_status, row.local_status, row.customer_name, row.customer_email, row.total, row.availability_status, row.matched_status, row.line_count, row.date_created.isoformat() if row.date_created else ""])
    return output.getvalue()


def order_to_read(order: Order, *, shipping_lines=SHIPPING_LINES_UNSET) -> OpenOrderRead:
    line_reads = [line_to_read(line) for line in order.items if line.sync_status != "local_removed"]
    flags = workflow_flags(order)
    raw_shipping_lines = (
        (order.raw_woo_payload or {}).get("shipping_lines")
        if shipping_lines is SHIPPING_LINES_UNSET
        else shipping_lines
    ) or []
    shipping_methods = [
        str(line.get("method_title") or line.get("method_id") or "").strip()
        for line in raw_shipping_lines
        if isinstance(line, dict)
    ]
    return OpenOrderRead(
        id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        woo_status=order.woo_status,
        local_status=order.local_status,
        allocation_status=order.allocation_status,
        pick_status=order.pick_status,
        completion_status=order.completion_status,
        auto_allocation_status=order.auto_allocation_status,
        completed_without_picking=bool(order.completed_without_picking),
        completed_at=order.completed_at,
        closed_at=order.closed_at,
        picked_at=order.picked_at,
        allocation_exception_reason=order.allocation_exception_reason,
        currency=order.currency,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        customer_phone=order.customer_phone,
        order_source="WooCommerce",
        shipping_city=order.shipping_city or (order.shipping_summary or {}).get("city"),
        shipping_state=order.shipping_state or (order.shipping_summary or {}).get("state"),
        shipping_zip=order.shipping_zip or (order.shipping_summary or {}).get("postcode"),
        shipping_via=", ".join(method for method in shipping_methods if method) or None,
        company=order.company or (order.shipping_summary or {}).get("company") or (order.billing_summary or {}).get("company"),
        ship_from="Main Warehouse",
        skus=list(dict.fromkeys(line.sku for line in line_reads if line.sku)),
        item_names=list(dict.fromkeys(line.name for line in line_reads if line.name)),
        total_quantity_ordered=sum(line.quantity_ordered for line in line_reads),
        total_quantity_allocated=sum(line.quantity_allocated for line in line_reads),
        total_quantity_picked=sum(line.quantity_picked for line in line_reads),
        total_quantity_fulfilled=sum(line.quantity_fulfilled for line in line_reads),
        total=decimal_to_float(order.total),
        date_created=order.date_created,
        date_modified=order.date_modified,
        line_count=len(line_reads),
        availability_status=aggregate_availability_status(line_reads),
        matched_status=aggregate_matched_status(line_reads),
        can_pick=flags["can_pick"],
        can_complete=flags["can_complete"],
        shows_in_open_orders=flags["shows_in_open_orders"],
        shows_in_allocate=flags["shows_in_allocate"],
        shows_in_pick_orders=flags["shows_in_pick_orders"],
        shows_in_completed_orders=flags["shows_in_completed_orders"],
        last_synced_at=order.last_synced_at,
    )


def order_line_reads(db: Session, order_id: int) -> list[OpenOrderLineRead]:
    order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.inventory_item))).one_or_none()
    return [line_to_read(line) for line in order.items] if order else []


def order_matches_search(order: Order, needle: str) -> bool:
    order_values = [
        order.woo_order_number,
        order.woo_order_id,
        order.customer_name,
        order.customer_email,
        order.customer_phone,
    ]
    if needle in " ".join(str(value or "") for value in order_values).casefold():
        return True
    for line in order.items:
        item = line.inventory_item
        line_values = [
            line.sku,
            line.barcode,
            line.name,
            line.description,
            item.sku if item else None,
            item.barcode if item else None,
            item.description if item else None,
        ]
        if needle in " ".join(str(value or "") for value in line_values).casefold():
            return True
    return False


def line_to_read(line: OrderItem) -> OpenOrderLineRead:
    quantity_ordered = line.quantity_ordered or Decimal("0")
    quantity_allocated = line.quantity_allocated or Decimal("0")
    quantity_picked = line.quantity_picked or Decimal("0")
    quantity_fulfilled = line.quantity_fulfilled or Decimal("0")
    quantity_stock_reduced = line.quantity_stock_reduced or Decimal("0")
    item_sellable = ((line.inventory_item.in_stock or Decimal("0")) - (line.inventory_item.allocated or Decimal("0"))) if line.inventory_item else Decimal("0")
    return OpenOrderLineRead(
        id=line.id,
        woo_line_item_id=line.woo_order_item_id,
        woo_product_id=line.woo_product_id,
        woo_variation_id=line.woo_variation_id,
        item_id=line.inventory_item_id,
        substituted_from_item_id=line.substituted_from_inventory_item_id,
        substituted_from_sku=(line.substituted_from_item.sku if line.substituted_from_item else None),
        substituted_from_name=(line.substituted_from_item.description if line.substituted_from_item else None),
        substitution_reason=line.substitution_reason,
        substituted_by=line.substituted_by,
        substituted_at=line.substituted_at,
        sku=line.sku or (line.inventory_item.sku if line.inventory_item else None),
        barcode=line.barcode or (line.inventory_item.barcode if line.inventory_item else None),
        name=line.name or line.description or (line.inventory_item.description if line.inventory_item else None),
        effective_sku=(line.inventory_item.sku if line.inventory_item else None),
        effective_barcode=(line.inventory_item.barcode if line.inventory_item else None),
        effective_name=(line.inventory_item.description if line.inventory_item else None),
        quantity_ordered=decimal_to_float(quantity_ordered) or 0,
        quantity_allocated=decimal_to_float(quantity_allocated) or 0,
        quantity_picked=decimal_to_float(quantity_picked) or 0,
        quantity_fulfilled=decimal_to_float(quantity_fulfilled) or 0,
        quantity_stock_reduced=decimal_to_float(quantity_stock_reduced) or 0,
        remaining_to_allocate=decimal_to_float(max(quantity_ordered - quantity_allocated, Decimal("0"))) or 0,
        remaining_to_pick=decimal_to_float(max(quantity_allocated - quantity_picked, Decimal("0"))) or 0,
        remaining_to_fulfill=decimal_to_float(max(quantity_picked - quantity_fulfilled, Decimal("0"))) or 0,
        stock_reduced_at=line.stock_reduced_at,
        allocation_status=line.allocation_status,
        pick_status=line.pick_status,
        allocation_exception_reason=line.allocation_exception_reason,
        picking_status="picked" if quantity_allocated > 0 and quantity_picked >= quantity_allocated else ("partial" if quantity_picked > 0 else "unpicked"),
        fulfillment_status="fulfilled" if quantity_picked > 0 and quantity_fulfilled >= quantity_picked else ("partial" if quantity_fulfilled > 0 else "unfulfilled"),
        unit_price=decimal_to_float(line.unit_price),
        line_tax=decimal_to_float(line.line_tax),
        line_total=decimal_to_float(line.line_total),
        matched_status=line.matched_status,
        availability_status=line.availability_status,
        local_sellable=decimal_to_float(item_sellable) or 0,
        sellable_snapshot=decimal_to_float(line.sellable_snapshot) or 0,
        shortage_quantity=decimal_to_float(line.shortage_quantity) or 0,
        sync_status=line.sync_status,
        sync_error=line.sync_error,
    )


def store_order_sync_error(db: Session, sync_run_id: int, order: WooCommerceOrderPreviewOrder, line: WooCommerceOrderPreviewLine | None, messages: list[str]) -> None:
    store_sync_error_once(
        db,
        sync_run_id=sync_run_id,
        remote_order_id=order.woo_order_id,
        remote_line_item_id=line.woo_line_item_id if line else None,
        remote_product_id=line.woo_product_id if line else None,
        remote_variation_id=line.woo_variation_id if line else None,
        sku=line.sku if line else None,
        barcode=line.barcode if line else None,
        error_message=" ".join(messages) if messages else "WooCommerce order sync row was not committed cleanly.",
        raw_payload={"order": order.model_dump(mode="json"), "line": line.model_dump(mode="json") if line else None},
    )


def aggregate_matched_status(lines) -> str:
    statuses = [line.matched_status for line in lines]
    if not statuses:
        return "unknown"
    if "conflict" in statuses:
        return "conflict"
    if "unmatched" in statuses:
        return "unmatched"
    if all(status == "matched" for status in statuses):
        return "matched"
    return "unknown"


def aggregate_availability_status(lines) -> str:
    statuses = [line.availability_status for line in lines]
    if not statuses:
        return "unknown"
    if "unknown" in statuses:
        return "unknown"
    if all(status == "allocated" for status in statuses):
        return "allocated"
    if "unavailable" in statuses:
        return "unavailable"
    if "partial" in statuses:
        return "partial"
    if all(status == "available" for status in statuses):
        return "available"
    return "unknown"


def calculate_subtotal(order: dict[str, Any]) -> Decimal | None:
    subtotal = sum((to_decimal(line.get("subtotal")) for line in order.get("line_items") or []), Decimal("0"))
    return subtotal if subtotal else None


def address_summary(address: dict[str, Any]) -> dict[str, Any]:
    keys = ["first_name", "last_name", "company", "address_1", "address_2", "city", "state", "postcode", "country", "email", "phone"]
    return {key: address.get(key) for key in keys if address.get(key)}


def extract_line_barcode(line: dict[str, Any]) -> str:
    for meta in line.get("meta_data") or []:
        key = str(meta.get("key") or "").casefold()
        if key in BARCODE_META_KEYS:
            return str(meta.get("value") or "").strip()
    return ""


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def to_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def to_decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return to_decimal(value)


def to_int_or_none(value: Any) -> int | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
