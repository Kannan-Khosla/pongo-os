from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.fulfillments import Fulfillment, FulfillmentLine
from app.schemas.reports import FulfillmentReportRow

FULFILLMENT_REPORT_CSV_COLUMNS = [
    "Fulfillment Number",
    "Status",
    "Posted At",
    "Created At",
    "Woo Order Number",
    "Woo Order ID",
    "Local Status",
    "Customer Name",
    "Customer Email",
    "Warehouse",
    "Inventory Location",
    "SKU",
    "Barcode",
    "Description",
    "Category",
    "Brand",
    "Quantity Ordered",
    "Quantity Allocated",
    "Quantity Picked",
    "Quantity Fulfilled",
    "Previously Fulfilled",
    "Remaining To Fulfill",
    "Unit Cost",
    "Fulfilled Value",
    "In Stock Before",
    "Allocated Before",
    "Sellable Before",
    "In Stock After",
    "Allocated After",
    "Sellable After",
    "Created By",
    "Line Notes",
    "Fulfillment Notes",
]


@dataclass(frozen=True)
class FulfillmentReportFilters:
    date_from: date | None = None
    date_to: date | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    sku: str | None = None
    barcode: str | None = None
    category: str | None = None
    brand: str | None = None
    fulfillment_number: str | None = None
    woo_order_number: str | None = None
    woo_order_id: int | None = None
    customer_email: str | None = None
    local_status: str | None = None
    created_by: str | None = None


def get_fulfillment_report_rows(db: Session, filters: FulfillmentReportFilters) -> list[FulfillmentReportRow]:
    statement = (
        select(FulfillmentLine)
        .join(Fulfillment)
        .options(
            selectinload(FulfillmentLine.fulfillment),
            selectinload(FulfillmentLine.order),
            selectinload(FulfillmentLine.order_line),
            selectinload(FulfillmentLine.inventory_item),
        )
        .order_by(Fulfillment.posted_at.desc().nullslast(), Fulfillment.created_at.desc(), FulfillmentLine.id.asc())
    )
    lines = list(db.scalars(statement).all())
    rows = [fulfillment_line_to_report_row(line) for line in lines]
    return [row for row in rows if row_matches_filters(row, filters)]


def fulfillment_line_to_report_row(line: FulfillmentLine) -> FulfillmentReportRow:
    fulfillment = line.fulfillment
    order = line.order
    item = line.inventory_item
    unit_cost = item.unit_cost if item and item.unit_cost is not None else Decimal("0")
    quantity_fulfilled = line.quantity_to_fulfill or Decimal("0")
    fulfilled_value = quantity_fulfilled * unit_cost
    return FulfillmentReportRow(
        fulfillment_id=fulfillment.id,
        fulfillment_number=fulfillment.fulfillment_number,
        status=fulfillment.status,
        posted_at=fulfillment.posted_at,
        created_at=fulfillment.created_at,
        order_id=line.order_id,
        woo_order_id=order.woo_order_id if order else fulfillment.woo_order_id,
        woo_order_number=order.woo_order_number if order else fulfillment.woo_order_number,
        local_status=order.local_status if order else None,
        customer_name=order.customer_name if order else None,
        customer_email=order.customer_email if order else None,
        warehouse=line.warehouse,
        inventory_location=line.inventory_location,
        sku=line.sku,
        barcode=line.barcode,
        description=line.description,
        category=item.category if item else None,
        brand=item.brand if item else None,
        quantity_ordered=decimal_to_float(line.quantity_ordered),
        quantity_allocated=decimal_to_float(line.quantity_allocated),
        quantity_picked=decimal_to_float(line.quantity_picked),
        quantity_fulfilled=decimal_to_float(quantity_fulfilled),
        quantity_previously_fulfilled=decimal_to_float(line.quantity_previously_fulfilled),
        remaining_to_fulfill=decimal_to_float(line.remaining_to_fulfill),
        unit_cost=decimal_to_float(unit_cost),
        fulfilled_value=decimal_to_float(fulfilled_value),
        in_stock_before=decimal_to_float(line.in_stock_before),
        allocated_before=decimal_to_float(line.allocated_before),
        sellable_before=decimal_to_float(line.sellable_before),
        in_stock_after=decimal_to_float(line.in_stock_after),
        allocated_after=decimal_to_float(line.allocated_after),
        sellable_after=decimal_to_float(line.sellable_after),
        created_by=fulfillment.created_by,
        line_notes=line.notes,
        fulfillment_notes=fulfillment.notes,
    )


def build_fulfillment_summary(rows: list[FulfillmentReportRow], filters: FulfillmentReportFilters) -> dict[str, object]:
    fulfillment_ids = {row.fulfillment_id for row in rows}
    order_ids = {row.order_id for row in rows}
    skus = {row.sku for row in rows if row.sku}
    locations = {(row.warehouse or "", row.inventory_location or "") for row in rows if row.warehouse or row.inventory_location}
    return {
        "total_fulfillments": len(fulfillment_ids),
        "total_orders": len(order_ids),
        "total_lines": len(rows),
        "total_quantity_fulfilled": sum_decimal(row.quantity_fulfilled for row in rows),
        "total_fulfilled_value": sum_decimal(row.fulfilled_value for row in rows),
        "unique_skus": len(skus),
        "unique_locations": len(locations),
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "by_warehouse": build_warehouse_groups(rows),
        "by_location": build_location_groups(rows),
        "by_sku": build_sku_groups(rows),
        "by_order": build_order_groups(rows),
    }


def build_warehouse_groups(rows: list[FulfillmentReportRow]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        warehouse = row.warehouse or ""
        group = groups.setdefault(warehouse, {"warehouse": warehouse, "total_lines": 0, "total_quantity_fulfilled": Decimal("0"), "total_fulfilled_value": Decimal("0")})
        add_group_totals(group, row)
    return sorted(groups.values(), key=lambda group: str(group["warehouse"]))


def build_location_groups(rows: list[FulfillmentReportRow]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        warehouse = row.warehouse or ""
        inventory_location = row.inventory_location or ""
        group = groups.setdefault(
            (warehouse, inventory_location),
            {"warehouse": warehouse, "inventory_location": inventory_location, "total_lines": 0, "total_quantity_fulfilled": Decimal("0"), "total_fulfilled_value": Decimal("0")},
        )
        add_group_totals(group, row)
    return sorted(groups.values(), key=lambda group: (str(group["warehouse"]), str(group["inventory_location"])))


def build_sku_groups(rows: list[FulfillmentReportRow]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    fulfillment_ids_by_sku: dict[str, set[int]] = {}
    order_ids_by_sku: dict[str, set[int]] = {}
    for row in rows:
        sku = row.sku or ""
        group = groups.setdefault(
            sku,
            {
                "sku": sku,
                "barcode": row.barcode,
                "description": row.description,
                "brand": row.brand,
                "category": row.category,
                "total_quantity_fulfilled": Decimal("0"),
                "total_fulfilled_value": Decimal("0"),
                "fulfillment_count": 0,
                "order_count": 0,
            },
        )
        group["total_quantity_fulfilled"] += Decimal(str(row.quantity_fulfilled))
        group["total_fulfilled_value"] += Decimal(str(row.fulfilled_value))
        fulfillment_ids_by_sku.setdefault(sku, set()).add(row.fulfillment_id)
        order_ids_by_sku.setdefault(sku, set()).add(row.order_id)
    for sku, group in groups.items():
        group["fulfillment_count"] = len(fulfillment_ids_by_sku.get(sku, set()))
        group["order_count"] = len(order_ids_by_sku.get(sku, set()))
    return sorted(groups.values(), key=lambda group: str(group["sku"]))


def build_order_groups(rows: list[FulfillmentReportRow]) -> list[dict[str, object]]:
    groups: dict[int, dict[str, object]] = {}
    for row in rows:
        group = groups.setdefault(
            row.order_id,
            {
                "woo_order_number": row.woo_order_number,
                "woo_order_id": row.woo_order_id,
                "customer_email": row.customer_email,
                "local_status": row.local_status,
                "total_lines": 0,
                "total_quantity_fulfilled": Decimal("0"),
                "total_fulfilled_value": Decimal("0"),
            },
        )
        add_group_totals(group, row)
    return sorted(groups.values(), key=lambda group: str(group["woo_order_number"] or ""))


def fulfillment_report_row_to_csv(row: FulfillmentReportRow) -> dict[str, object]:
    return {
        "Fulfillment Number": row.fulfillment_number,
        "Status": row.status or "",
        "Posted At": row.posted_at.isoformat() if row.posted_at else "",
        "Created At": row.created_at.isoformat() if row.created_at else "",
        "Woo Order Number": row.woo_order_number or "",
        "Woo Order ID": row.woo_order_id or "",
        "Local Status": row.local_status or "",
        "Customer Name": row.customer_name or "",
        "Customer Email": row.customer_email or "",
        "Warehouse": row.warehouse or "",
        "Inventory Location": row.inventory_location or "",
        "SKU": row.sku or "",
        "Barcode": row.barcode or "",
        "Description": row.description or "",
        "Category": row.category or "",
        "Brand": row.brand or "",
        "Quantity Ordered": row.quantity_ordered,
        "Quantity Allocated": row.quantity_allocated,
        "Quantity Picked": row.quantity_picked,
        "Quantity Fulfilled": row.quantity_fulfilled,
        "Previously Fulfilled": row.quantity_previously_fulfilled,
        "Remaining To Fulfill": row.remaining_to_fulfill,
        "Unit Cost": row.unit_cost,
        "Fulfilled Value": row.fulfilled_value,
        "In Stock Before": row.in_stock_before,
        "Allocated Before": row.allocated_before,
        "Sellable Before": row.sellable_before,
        "In Stock After": row.in_stock_after,
        "Allocated After": row.allocated_after,
        "Sellable After": row.sellable_after,
        "Created By": row.created_by or "",
        "Line Notes": row.line_notes or "",
        "Fulfillment Notes": row.fulfillment_notes or "",
    }


def row_matches_filters(row: FulfillmentReportRow, filters: FulfillmentReportFilters) -> bool:
    report_date = (row.posted_at or row.created_at).date()
    if filters.date_from and report_date < filters.date_from:
        return False
    if filters.date_to and report_date > filters.date_to:
        return False
    if filters.woo_order_id is not None and row.woo_order_id != filters.woo_order_id:
        return False
    return all(
        [
            text_matches(row.warehouse, filters.warehouse),
            text_matches(row.inventory_location, filters.inventory_location),
            text_matches(row.sku, filters.sku),
            text_matches(row.barcode, filters.barcode),
            text_matches(row.category, filters.category),
            text_matches(row.brand, filters.brand),
            text_matches(row.fulfillment_number, filters.fulfillment_number),
            text_matches(row.woo_order_number, filters.woo_order_number),
            text_matches(row.customer_email, filters.customer_email),
            text_matches(row.local_status, filters.local_status),
            text_matches(row.created_by, filters.created_by),
        ]
    )


def text_matches(value: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    return expected.casefold() in (value or "").casefold()


def add_group_totals(group: dict[str, object], row: FulfillmentReportRow) -> None:
    group["total_lines"] += 1
    group["total_quantity_fulfilled"] += Decimal(str(row.quantity_fulfilled))
    group["total_fulfilled_value"] += Decimal(str(row.fulfilled_value))


def sum_decimal(values) -> Decimal:
    return sum((Decimal(str(value)) for value in values), Decimal("0"))


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)
