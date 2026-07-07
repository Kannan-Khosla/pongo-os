from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.models.woocommerce import WooCommerceSyncError, WooCommerceSyncRun
from app.schemas.orders import OpenOrderDetail, OpenOrderLineRead, OpenOrderListResponse, OpenOrderRead
from app.schemas.woocommerce import (
    WooCommerceOrderPreviewLine,
    WooCommerceOrderPreviewOrder,
    WooCommerceOrderPreviewResponse,
    WooCommerceOrderSyncRequest,
)
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError

OPEN_WOO_STATUSES = {"processing", "on-hold"}
BARCODE_META_KEYS = {"barcode", "_barcode", "_ywbc_barcode", "upc", "gtin"}


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
    started_at = datetime.now(timezone.utc)
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
        return None, WooCommerceOrderPreviewResponse(
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
    normalized_orders = [normalize_order(order) for order in remote_orders]
    preview_rows = [build_order_preview(db, order, order_statuses(payload)) for order in normalized_orders]
    preview = build_order_preview_response(True, preview_rows)
    sync_run = WooCommerceSyncRun(sync_type="orders", status="completed", started_at=started_at, created_by=payload.created_by or "system", total_remote_records=preview.total_remote_records)
    db.add(sync_run)
    db.flush()
    created_count = updated_count = matched_count = skipped_count = conflict_count = error_count = 0
    now = datetime.now(timezone.utc)

    for record, preview_order in zip(normalized_orders, preview_rows, strict=False):
        if preview_order.action == "skip":
            skipped_count += 1
            store_order_sync_error(db, sync_run.id, preview_order, None, preview_order.warnings or preview_order.errors or ["Order status is not open for this sync."])
            continue
        try:
            order = db.scalars(select(Order).where(Order.woo_order_id == record.woo_order_id).options(selectinload(Order.items))).one_or_none()
            if order is None:
                order = Order(woo_order_id=record.woo_order_id)
                db.add(order)
                created_count += 1
            else:
                updated_count += 1
            update_local_order(order, record, preview_order, now)
            db.flush()
            matched_count += sum(1 for line in preview_order.lines if line.matched_status == "matched")
            conflict_count += sum(1 for line in preview_order.lines if line.matched_status == "conflict")
            error_count += sum(1 for line in preview_order.lines if line.matched_status in {"unmatched", "conflict"})
            upsert_order_lines(db, order, record, preview_order)
            for line in preview_order.lines:
                if line.matched_status in {"unmatched", "conflict"}:
                    store_order_sync_error(db, sync_run.id, preview_order, line, line.errors or line.warnings or [f"Order line is {line.matched_status}."])
        except Exception as exc:
            error_count += 1
            store_order_sync_error(db, sync_run.id, preview_order, None, [str(exc)])

    sync_run.created_count = created_count
    sync_run.updated_count = updated_count
    sync_run.matched_count = matched_count
    sync_run.skipped_count = skipped_count
    sync_run.conflict_count = conflict_count
    sync_run.error_count = error_count
    sync_run.completed_at = datetime.now(timezone.utc)
    sync_run.status = "completed_with_errors" if conflict_count or error_count else "completed"
    db.commit()
    db.refresh(sync_run)
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
        warnings=preview.warnings,
        errors=preview.errors,
        preview_orders=[],
    )
    return sync_run, response


def build_order_preview(db: Session, record: NormalizedWooOrder, requested_statuses: list[str]) -> WooCommerceOrderPreviewOrder:
    local_order = db.scalars(select(Order).where(Order.woo_order_id == record.woo_order_id)).one_or_none()
    action = "update" if local_order else "create"
    warnings: list[str] = []
    errors: list[str] = []
    if record.woo_status not in requested_statuses or record.woo_status not in OPEN_WOO_STATUSES:
        action = "skip"
        warnings.append(f"WooCommerce status {record.woo_status or 'unknown'} is not treated as an open order.")
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
    return NormalizedWooOrder(
        woo_order_id=int(order.get("id")),
        woo_order_number=str(order.get("number") or order.get("id") or ""),
        woo_status=woo_status,
        local_status="open" if woo_status in OPEN_WOO_STATUSES else "skipped",
        currency=str(order.get("currency") or ""),
        customer_id=to_int_or_none(order.get("customer_id")),
        customer_email=str(billing.get("email") or order.get("billing_email") or ""),
        customer_first_name=str(billing.get("first_name") or ""),
        customer_last_name=str(billing.get("last_name") or ""),
        customer_phone=str(billing.get("phone") or shipping.get("phone") or ""),
        billing_summary=address_summary(billing),
        shipping_summary=address_summary(shipping),
        payment_method=str(order.get("payment_method") or ""),
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
    woo_match = None
    if line.woo_product_id:
        statement = select(InventoryItem).where(InventoryItem.woo_product_id == line.woo_product_id)
        if line.woo_variation_id:
            statement = statement.where(InventoryItem.woo_variation_id == line.woo_variation_id)
        else:
            statement = statement.where(InventoryItem.woo_variation_id.is_(None))
        woo_match = db.scalars(statement).first()
    sku_match = db.scalars(select(InventoryItem).where(InventoryItem.sku == line.sku)).first() if line.sku else None
    barcode_match = db.scalars(select(InventoryItem).where(InventoryItem.barcode == line.barcode)).first() if line.barcode else None
    candidates.extend(candidate for candidate in [woo_match, sku_match, barcode_match] if candidate is not None)
    if len({candidate.id for candidate in candidates}) > 1:
        errors.append("WooCommerce IDs, SKU, or Barcode match different local items.")
        return None
    return candidates[0] if candidates else None


def update_local_order(order: Order, record: NormalizedWooOrder, preview: WooCommerceOrderPreviewOrder, synced_at: datetime) -> None:
    order.woo_order_number = record.woo_order_number
    order.woo_status = record.woo_status
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
    order.allocation_status = preview.availability_status
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


def upsert_order_lines(db: Session, order: Order, record: NormalizedWooOrder, preview: WooCommerceOrderPreviewOrder) -> None:
    existing_by_line_id = {line.woo_order_item_id: line for line in order.items if line.woo_order_item_id is not None}
    preview_by_line_id = {line.woo_line_item_id: line for line in preview.lines}
    for index, record_line in enumerate(record.lines, start=1):
        preview_line = preview_by_line_id.get(record_line.woo_line_item_id)
        local_line = existing_by_line_id.get(record_line.woo_line_item_id)
        if local_line is None:
            local_line = OrderItem(order=order, woo_order_item_id=record_line.woo_line_item_id)
            db.add(local_line)
        local_line.woo_product_id = record_line.woo_product_id
        local_line.woo_variation_id = record_line.woo_variation_id
        local_line.inventory_item_id = preview_line.item_id if preview_line else None
        local_line.line_number = index
        local_line.sku = record_line.sku
        local_line.barcode = record_line.barcode
        local_line.description = record_line.name
        local_line.name = record_line.name
        existing_allocated = local_line.quantity_allocated or Decimal("0")
        existing_picked = local_line.quantity_picked or Decimal("0")
        existing_fulfilled = local_line.quantity_fulfilled or Decimal("0")
        local_line.quantity_ordered = record_line.quantity_ordered
        local_line.quantity_allocated = existing_allocated
        local_line.quantity_picked = existing_picked
        local_line.quantity_fulfilled = existing_fulfilled
        local_line.ordered_qty = record_line.quantity_ordered
        local_line.allocated_qty = existing_allocated
        local_line.picked_qty = existing_picked
        local_line.fulfilled_qty = existing_fulfilled
        local_line.unit_price = record_line.unit_price
        local_line.line_subtotal = record_line.line_subtotal
        local_line.line_total = record_line.line_total
        local_line.line_tax = record_line.line_tax
        local_line.total_price = record_line.line_total
        local_line.matched_status = preview_line.matched_status if preview_line else "unknown"
        local_line.availability_status = "allocated" if existing_allocated >= record_line.quantity_ordered else (preview_line.availability_status if preview_line else "unknown")
        local_line.sellable_snapshot = Decimal(str(preview_line.sellable_snapshot)) if preview_line else Decimal("0")
        remaining_after_allocation = max(record_line.quantity_ordered - existing_allocated, Decimal("0"))
        local_line.shortage_quantity = max(remaining_after_allocation - local_line.sellable_snapshot, Decimal("0")) if preview_line else remaining_after_allocation
        local_line.sync_status = "synced" if preview_line and preview_line.matched_status == "matched" else "needs_review"
        local_line.sync_error = " ".join((preview_line.errors or preview_line.warnings) if preview_line else ["Preview line missing."])
        local_line.status = "open"


def list_open_orders(
    db: Session,
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
) -> OpenOrderListResponse:
    orders = list(db.scalars(select(Order).where(Order.local_status.in_(["open", "partially_allocated", "allocated", "partially_picked", "picked", "partially_fulfilled", "fulfilled"])).options(selectinload(Order.items).selectinload(OrderItem.inventory_item)).order_by(Order.date_created.desc().nullslast(), Order.id.desc())).all())
    rows = [order_to_read(order) for order in orders]
    if search:
        needle = search.casefold()
        rows = [
            row
            for row in rows
            if needle in " ".join(str(value or "") for value in [row.woo_order_number, row.customer_name, row.customer_email]).casefold()
            or any(needle in " ".join(str(value or "") for value in [line.sku, line.barcode, line.name]).casefold() for line in order_line_reads(db, row.id))
        ]
    if woo_status:
        rows = [row for row in rows if row.woo_status == woo_status]
    if availability_status:
        rows = [row for row in rows if row.availability_status == availability_status]
    if matched_status:
        rows = [row for row in rows if row.matched_status == matched_status]
    return OpenOrderListResponse(
        orders=rows,
        total=len(rows),
        available_count=sum(1 for row in rows if row.availability_status == "available"),
        partial_count=sum(1 for row in rows if row.availability_status == "partial"),
        unavailable_count=sum(1 for row in rows if row.availability_status == "unavailable"),
        unknown_count=sum(1 for row in rows if row.availability_status == "unknown"),
    )


def get_open_order_detail(db: Session, order_id: int) -> OpenOrderDetail | None:
    order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.inventory_item))).one_or_none()
    if order is None:
        return None
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
            "lines": [line_to_read(line) for line in sorted(order.items, key=lambda item: item.line_number or item.id)],
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


def order_to_read(order: Order) -> OpenOrderRead:
    line_reads = [line_to_read(line) for line in order.items]
    return OpenOrderRead(
        id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        woo_status=order.woo_status,
        local_status=order.local_status,
        currency=order.currency,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        customer_phone=order.customer_phone,
        total=decimal_to_float(order.total),
        date_created=order.date_created,
        date_modified=order.date_modified,
        line_count=len(line_reads),
        availability_status=aggregate_availability_status(line_reads),
        matched_status=aggregate_matched_status(line_reads),
        last_synced_at=order.last_synced_at,
    )


def order_line_reads(db: Session, order_id: int) -> list[OpenOrderLineRead]:
    order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.inventory_item))).one_or_none()
    return [line_to_read(line) for line in order.items] if order else []


def line_to_read(line: OrderItem) -> OpenOrderLineRead:
    quantity_ordered = line.quantity_ordered or Decimal("0")
    quantity_allocated = line.quantity_allocated or Decimal("0")
    quantity_picked = line.quantity_picked or Decimal("0")
    quantity_fulfilled = line.quantity_fulfilled or Decimal("0")
    item_sellable = ((line.inventory_item.in_stock or Decimal("0")) - (line.inventory_item.allocated or Decimal("0"))) if line.inventory_item else Decimal("0")
    return OpenOrderLineRead(
        id=line.id,
        woo_line_item_id=line.woo_order_item_id,
        woo_product_id=line.woo_product_id,
        woo_variation_id=line.woo_variation_id,
        item_id=line.inventory_item_id,
        sku=line.sku,
        barcode=line.barcode,
        name=line.name or line.description,
        quantity_ordered=decimal_to_float(quantity_ordered) or 0,
        quantity_allocated=decimal_to_float(quantity_allocated) or 0,
        quantity_picked=decimal_to_float(quantity_picked) or 0,
        quantity_fulfilled=decimal_to_float(quantity_fulfilled) or 0,
        remaining_to_allocate=decimal_to_float(max(quantity_ordered - quantity_allocated, Decimal("0"))) or 0,
        remaining_to_pick=decimal_to_float(max(quantity_allocated - quantity_picked, Decimal("0"))) or 0,
        remaining_to_fulfill=decimal_to_float(max(quantity_picked - quantity_fulfilled, Decimal("0"))) or 0,
        picking_status="picked" if quantity_allocated > 0 and quantity_picked >= quantity_allocated else ("partial" if quantity_picked > 0 else "unpicked"),
        fulfillment_status="fulfilled" if quantity_picked > 0 and quantity_fulfilled >= quantity_picked else ("partial" if quantity_fulfilled > 0 else "unfulfilled"),
        unit_price=decimal_to_float(line.unit_price),
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
    db.add(
        WooCommerceSyncError(
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
