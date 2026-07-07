from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.orders import OrderItem
from app.schemas.reports import SkuOrdersReportRow

SKU_ORDERS_CSV_COLUMNS = [
    "SKU",
    "Item ID",
    "Description",
    "Brand",
    "Category",
    "Location",
    "Total Orders",
    "Quantity Ordered",
    "Quantity Allocated",
    "Quantity Picked",
    "Quantity Fulfilled",
    "Unfulfilled Quantity",
    "Unmatched Lines",
    "First Order Date",
    "Last Order Date",
    "Current In Stock",
    "Current Allocated",
    "Current Sellable",
    "Woo Stock Snapshot",
]


@dataclass(frozen=True)
class SkuOrdersFilters:
    start_date: date | None = None
    end_date: date | None = None
    sku: str | None = None
    brand: str | None = None
    category: str | None = None
    order_status: str | None = None
    woo_status: str | None = None
    include_unmatched: bool = True
    group_by: str = "sku"
    limit: int | None = None
    offset: int | None = None


def get_sku_order_rows(db: Session, filters: SkuOrdersFilters) -> list[SkuOrdersReportRow]:
    lines = list(db.scalars(select(OrderItem).options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))).all())
    lines = [line for line in lines if line_matches_filters(line, filters)]
    grouped: dict[str, dict[str, object]] = {}
    order_ids_by_key: dict[str, set[int]] = {}
    for line in lines:
        item = line.inventory_item
        key = group_key(line, filters.group_by)
        group = grouped.setdefault(
            key,
            {
                "sku": key,
                "item_id": item.id if item else line.inventory_item_id,
                "description": line.name or line.description or (item.description if item else None),
                "brand": item.brand if item else line.brand,
                "category": item.category if item else None,
                "location": item.inventory_location if item else None,
                "total_quantity_ordered": Decimal("0"),
                "total_quantity_allocated": Decimal("0"),
                "total_quantity_picked": Decimal("0"),
                "total_quantity_fulfilled": Decimal("0"),
                "unmatched_order_line_count": 0,
                "first_order_date": None,
                "last_order_date": None,
                "current_in_stock": item.in_stock if item else None,
                "current_allocated": item.allocated if item else None,
                "current_sellable": item.sellable if item else None,
                "woo_stock_snapshot": item.woo_stock_quantity_snapshot if item else None,
            },
        )
        group["total_quantity_ordered"] += line.quantity_ordered or Decimal("0")
        group["total_quantity_allocated"] += line.quantity_allocated or Decimal("0")
        group["total_quantity_picked"] += line.quantity_picked or Decimal("0")
        group["total_quantity_fulfilled"] += line.quantity_fulfilled or Decimal("0")
        if line.matched_status != "matched":
            group["unmatched_order_line_count"] += 1
        if line.order and line.order.date_created:
            first = group["first_order_date"]
            last = group["last_order_date"]
            group["first_order_date"] = line.order.date_created if first is None or line.order.date_created < first else first
            group["last_order_date"] = line.order.date_created if last is None or line.order.date_created > last else last
        order_ids_by_key.setdefault(key, set()).add(line.order_id)
    rows = []
    for key, group in grouped.items():
        ordered = group["total_quantity_ordered"]
        fulfilled = group["total_quantity_fulfilled"]
        rows.append(
            SkuOrdersReportRow(
                sku=str(group["sku"] or ""),
                item_id=group["item_id"],
                description=group["description"],
                brand=group["brand"],
                category=group["category"],
                location=group["location"],
                total_orders_count=len(order_ids_by_key.get(key, set())),
                total_quantity_ordered=decimal_to_float(ordered),
                total_quantity_allocated=decimal_to_float(group["total_quantity_allocated"]),
                total_quantity_picked=decimal_to_float(group["total_quantity_picked"]),
                total_quantity_fulfilled=decimal_to_float(fulfilled),
                unfulfilled_quantity=decimal_to_float(max(ordered - fulfilled, Decimal("0"))),
                unmatched_order_line_count=group["unmatched_order_line_count"],
                first_order_date=group["first_order_date"],
                last_order_date=group["last_order_date"],
                current_in_stock=decimal_to_optional_float(group["current_in_stock"]),
                current_allocated=decimal_to_optional_float(group["current_allocated"]),
                current_sellable=decimal_to_optional_float(group["current_sellable"]),
                woo_stock_snapshot=decimal_to_optional_float(group["woo_stock_snapshot"]),
            )
        )
    rows.sort(key=lambda row: row.total_quantity_ordered, reverse=True)
    offset = filters.offset or 0
    if filters.limit is not None:
        return rows[offset : offset + filters.limit]
    return rows[offset:]


def build_sku_orders_summary(rows: list[SkuOrdersReportRow]) -> dict[str, object]:
    top = max(rows, key=lambda row: row.total_quantity_ordered).sku if rows else None
    return {
        "total_skus": len(rows),
        "total_quantity_ordered": sum(row.total_quantity_ordered for row in rows),
        "total_quantity_fulfilled": sum(row.total_quantity_fulfilled for row in rows),
        "total_unfulfilled_quantity": sum(row.unfulfilled_quantity for row in rows),
        "unmatched_lines_count": sum(row.unmatched_order_line_count for row in rows),
        "top_sku_by_quantity": top,
    }


def export_sku_orders_csv(rows: list[SkuOrdersReportRow]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=SKU_ORDERS_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(sku_order_row_to_csv(row))
    return output.getvalue()


def line_matches_filters(line: OrderItem, filters: SkuOrdersFilters) -> bool:
    order = line.order
    item = line.inventory_item
    if not filters.include_unmatched and line.matched_status != "matched":
        return False
    if filters.start_date and order and order.date_created and order.date_created.date() < filters.start_date:
        return False
    if filters.end_date and order and order.date_created and order.date_created.date() > filters.end_date:
        return False
    sku_value = line.sku or (item.sku if item else "") or ""
    brand_value = (item.brand if item else line.brand) or ""
    category_value = (item.category if item else "") or ""
    if filters.sku and filters.sku.casefold() not in sku_value.casefold():
        return False
    if filters.brand and filters.brand.casefold() not in brand_value.casefold():
        return False
    if filters.category and filters.category.casefold() not in category_value.casefold():
        return False
    if filters.order_status and order and order.local_status != filters.order_status:
        return False
    if filters.woo_status and order and order.woo_status != filters.woo_status:
        return False
    return True


def group_key(line: OrderItem, group_by: str) -> str:
    item = line.inventory_item
    if group_by == "brand":
        return item.brand if item and item.brand else line.brand or "Unbranded"
    if group_by == "category":
        return item.category if item and item.category else "Uncategorized"
    if group_by == "location":
        return item.inventory_location if item and item.inventory_location else "Unassigned"
    return line.sku or (item.sku if item else None) or "Unmatched"


def sku_order_row_to_csv(row: SkuOrdersReportRow) -> dict[str, object]:
    return {
        "SKU": row.sku,
        "Item ID": row.item_id or "",
        "Description": row.description or "",
        "Brand": row.brand or "",
        "Category": row.category or "",
        "Location": row.location or "",
        "Total Orders": row.total_orders_count,
        "Quantity Ordered": row.total_quantity_ordered,
        "Quantity Allocated": row.total_quantity_allocated,
        "Quantity Picked": row.total_quantity_picked,
        "Quantity Fulfilled": row.total_quantity_fulfilled,
        "Unfulfilled Quantity": row.unfulfilled_quantity,
        "Unmatched Lines": row.unmatched_order_line_count,
        "First Order Date": row.first_order_date.isoformat() if row.first_order_date else "",
        "Last Order Date": row.last_order_date.isoformat() if row.last_order_date else "",
        "Current In Stock": "" if row.current_in_stock is None else row.current_in_stock,
        "Current Allocated": "" if row.current_allocated is None else row.current_allocated,
        "Current Sellable": "" if row.current_sellable is None else row.current_sellable,
        "Woo Stock Snapshot": "" if row.woo_stock_snapshot is None else row.woo_stock_snapshot,
    }


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)


def decimal_to_optional_float(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)
