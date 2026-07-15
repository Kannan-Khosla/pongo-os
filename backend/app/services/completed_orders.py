from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.orders import Order, OrderItem
from app.schemas.orders import CompletedOrderListResponse, CompletedOrderRead

COMPLETED_ORDER_STATUSES = {"completed", "closed", "fulfilled", "partially_fulfilled"}
COMPLETED_ORDERS_CSV_COLUMNS = [
    "Woo Order Number",
    "Woo Order ID",
    "Woo Status",
    "Local Status",
    "Customer Name",
    "Customer Email",
    "Order Total",
    "Line SKU",
    "Line Barcode",
    "Line Name",
    "Quantity Ordered",
    "Quantity Allocated",
    "Quantity Picked",
    "Quantity Fulfilled",
    "Remaining To Fulfill",
    "Fulfillment Status",
    "Fulfilled Value",
    "Date Created",
    "Date Modified",
]


@dataclass(frozen=True)
class CompletedOrderFilters:
    local_status: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    customer_email: str | None = None
    woo_order_number: str | None = None
    sku: str | None = None
    barcode: str | None = None
    search: str | None = None


def list_completed_orders(db: Session, filters: CompletedOrderFilters) -> CompletedOrderListResponse:
    statement = select(Order).where((Order.local_status.in_(COMPLETED_ORDER_STATUSES)) | (Order.completion_status.in_(["completed", "completed_without_picking"]))).options(selectinload(Order.items).selectinload(OrderItem.inventory_item)).order_by(Order.closed_at.desc().nullslast(), Order.completed_at.desc().nullslast(), Order.date_modified.desc().nullslast(), Order.date_created.desc().nullslast(), Order.id.desc())
    orders = list(db.scalars(statement).all())
    rows = [completed_order_to_read(order) for order in orders if order_matches_filters(order, filters)]
    return CompletedOrderListResponse(orders=rows, total=len(rows))


def export_completed_orders_csv(db: Session, filters: CompletedOrderFilters) -> str:
    statement = select(Order).where((Order.local_status.in_(COMPLETED_ORDER_STATUSES)) | (Order.completion_status.in_(["completed", "completed_without_picking"]))).options(selectinload(Order.items).selectinload(OrderItem.inventory_item)).order_by(Order.closed_at.desc().nullslast(), Order.completed_at.desc().nullslast(), Order.date_modified.desc().nullslast(), Order.date_created.desc().nullslast(), Order.id.desc())
    orders = [order for order in db.scalars(statement).all() if order_matches_filters(order, filters)]
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(COMPLETED_ORDERS_CSV_COLUMNS)
    for order in orders:
        for line in sorted(order.items, key=lambda item: item.line_number or item.id):
            if line.quantity_fulfilled and line.quantity_fulfilled > 0:
                writer.writerow(completed_order_line_to_csv(order, line))
    return output.getvalue()


def completed_order_to_read(order: Order) -> CompletedOrderRead:
    lines = list(order.items)
    return CompletedOrderRead(
        id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        woo_status=order.woo_status,
        local_status=order.local_status,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        total=decimal_to_float(order.total),
        date_created=order.date_created,
        date_modified=order.date_modified,
        line_count=len(lines),
        fulfilled_line_count=sum(1 for line in lines if (line.quantity_fulfilled or Decimal("0")) > 0),
        total_quantity_ordered=decimal_to_float(sum((line.quantity_ordered or Decimal("0")) for line in lines)),
        total_quantity_allocated=decimal_to_float(sum((line.quantity_allocated or Decimal("0")) for line in lines)),
        total_quantity_picked=decimal_to_float(sum((line.quantity_picked or Decimal("0")) for line in lines)),
        total_quantity_fulfilled=decimal_to_float(sum((line.quantity_fulfilled or Decimal("0")) for line in lines)),
        total_quantity_stock_reduced=decimal_to_float(sum((line.quantity_stock_reduced or Decimal("0")) for line in lines)),
        total_remaining_to_fulfill=decimal_to_float(sum(remaining_to_fulfill(line) for line in lines)),
        total_fulfilled_value=decimal_to_float(sum(fulfilled_value(line) for line in lines)),
        completed_without_picking=bool(order.completed_without_picking),
        completion_status=order.completion_status,
        pick_status=order.pick_status,
        completed_at=order.completed_at,
        closed_at=order.closed_at,
    )


def completed_order_line_to_csv(order: Order, line: OrderItem) -> list[object]:
    quantity_fulfilled = line.quantity_fulfilled or Decimal("0")
    return [
        order.woo_order_number or "",
        order.woo_order_id or "",
        order.woo_status or "",
        order.local_status or "",
        order.customer_name or "",
        order.customer_email or "",
        decimal_to_float(order.total),
        line.sku or "",
        line.barcode or "",
        line.name or line.description or "",
        decimal_to_float(line.quantity_ordered),
        decimal_to_float(line.quantity_allocated),
        decimal_to_float(line.quantity_picked),
        decimal_to_float(quantity_fulfilled),
        decimal_to_float(remaining_to_fulfill(line)),
        fulfillment_status(line),
        decimal_to_float(fulfilled_value(line)),
        order.date_created.isoformat() if order.date_created else "",
        order.date_modified.isoformat() if order.date_modified else "",
    ]


def order_matches_filters(order: Order, filters: CompletedOrderFilters) -> bool:
    if filters.local_status and order.local_status != filters.local_status:
        return False
    order_date = (order.date_modified or order.date_created)
    if filters.date_from and order_date and order_date.date() < filters.date_from:
        return False
    if filters.date_to and order_date and order_date.date() > filters.date_to:
        return False
    if filters.customer_email and filters.customer_email.casefold() not in (order.customer_email or "").casefold():
        return False
    if filters.woo_order_number and filters.woo_order_number.casefold() not in (order.woo_order_number or "").casefold():
        return False
    if filters.sku and not any(filters.sku.casefold() in (line.sku or "").casefold() for line in order.items):
        return False
    if filters.barcode and not any(filters.barcode.casefold() in (line.barcode or "").casefold() for line in order.items):
        return False
    if filters.search:
        needle = filters.search.casefold()
        haystack = " ".join(str(value or "") for value in [order.woo_order_number, order.customer_name, order.customer_email]).casefold()
        line_haystack = " ".join(" ".join(str(value or "") for value in [line.sku, line.barcode, line.name, line.description]) for line in order.items).casefold()
        if needle not in haystack and needle not in line_haystack:
            return False
    return True


def remaining_to_fulfill(line: OrderItem) -> Decimal:
    return max((line.quantity_picked or Decimal("0")) - (line.quantity_fulfilled or Decimal("0")), Decimal("0"))


def fulfillment_status(line: OrderItem) -> str:
    picked = line.quantity_picked or Decimal("0")
    fulfilled = line.quantity_fulfilled or Decimal("0")
    if picked > 0 and fulfilled >= picked:
        return "fulfilled"
    if fulfilled > 0:
        return "partial"
    return "unfulfilled"


def fulfilled_value(line: OrderItem) -> Decimal:
    unit_cost = line.inventory_item.unit_cost if line.inventory_item and line.inventory_item.unit_cost is not None else Decimal("0")
    return (line.quantity_fulfilled or Decimal("0")) * unit_cost


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)
