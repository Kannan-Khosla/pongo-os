import csv
from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.inventory import InventoryItem, InventoryItemLocation, StockAdjustment, StockAdjustmentLine, StockMovement
from app.models.orders import OrderItem
from app.models.receipts import Receipt, ReceiptItem
from app.schemas.reports import FulfillmentReportRow, FulfillmentSummaryResponse, ReceivedInventoryReportRow, ReceivedInventorySummaryResponse, SkuOrdersReportRow, SkuOrdersSummaryResponse
from app.services.fulfillment_report import (
    FULFILLMENT_REPORT_CSV_COLUMNS,
    FulfillmentReportFilters,
    build_fulfillment_summary,
    fulfillment_report_row_to_csv,
    get_fulfillment_report_rows,
)
from app.services.received_inventory_report import (
    RECEIVED_INVENTORY_CSV_COLUMNS,
    ReceivedInventoryFilters,
    build_received_inventory_summary,
    get_received_inventory_rows,
    received_inventory_row_to_csv,
)
from app.services.sku_orders_report import SkuOrdersFilters, build_sku_orders_summary, export_sku_orders_csv, get_sku_order_rows

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports_placeholder() -> dict[str, str]:
    return {"module": "reports", "status": "placeholder"}


@router.get("/received-inventory", response_model=list[ReceivedInventoryReportRow])
def received_inventory_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    receipt_number: str | None = None,
    reference_number: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> list[ReceivedInventoryReportRow]:
    return get_received_inventory_rows(db, build_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, receipt_number, reference_number, created_by))


@router.get("/received-inventory/summary", response_model=ReceivedInventorySummaryResponse)
def received_inventory_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    receipt_number: str | None = None,
    reference_number: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    filters = build_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, receipt_number, reference_number, created_by)
    rows = get_received_inventory_rows(db, filters)
    return build_received_inventory_summary(rows, filters)


@router.get("/received-inventory/export")
def export_received_inventory_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    receipt_number: str | None = None,
    reference_number: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    filters = build_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, receipt_number, reference_number, created_by)
    rows = get_received_inventory_rows(db, filters)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RECEIVED_INVENTORY_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(received_inventory_row_to_csv(row))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-received-inventory-report.csv"'},
    )


@router.get("/fulfillments", response_model=list[FulfillmentReportRow])
def fulfillment_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    fulfillment_number: str | None = None,
    woo_order_number: str | None = None,
    woo_order_id: int | None = None,
    customer_email: str | None = None,
    local_status: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> list[FulfillmentReportRow]:
    return get_fulfillment_report_rows(db, build_fulfillment_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, fulfillment_number, woo_order_number, woo_order_id, customer_email, local_status, created_by))


@router.get("/fulfillments/summary", response_model=FulfillmentSummaryResponse)
def fulfillment_summary(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    fulfillment_number: str | None = None,
    woo_order_number: str | None = None,
    woo_order_id: int | None = None,
    customer_email: str | None = None,
    local_status: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    filters = build_fulfillment_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, fulfillment_number, woo_order_number, woo_order_id, customer_email, local_status, created_by)
    rows = get_fulfillment_report_rows(db, filters)
    return build_fulfillment_summary(rows, filters)


@router.get("/fulfillments/export")
def export_fulfillment_report(
    date_from: date | None = None,
    date_to: date | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    fulfillment_number: str | None = None,
    woo_order_number: str | None = None,
    woo_order_id: int | None = None,
    customer_email: str | None = None,
    local_status: str | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    filters = build_fulfillment_filters(date_from, date_to, warehouse, inventory_location, sku, barcode, category, brand, fulfillment_number, woo_order_number, woo_order_id, customer_email, local_status, created_by)
    rows = get_fulfillment_report_rows(db, filters)
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FULFILLMENT_REPORT_CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(fulfillment_report_row_to_csv(row))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-fulfillment-report.csv"'},
    )


@router.get("/sku-orders", response_model=list[SkuOrdersReportRow])
def sku_orders_report(
    start_date: date | None = None,
    end_date: date | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    order_status: str | None = None,
    woo_status: str | None = None,
    include_unmatched: bool = True,
    group_by: str = "sku",
    limit: int | None = None,
    offset: int | None = None,
    db: Session = Depends(get_db),
) -> list[SkuOrdersReportRow]:
    return get_sku_order_rows(db, build_sku_order_filters(start_date, end_date, sku, brand, category, order_status, woo_status, include_unmatched, group_by, limit, offset))


@router.get("/sku-orders/summary", response_model=SkuOrdersSummaryResponse)
def sku_orders_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    order_status: str | None = None,
    woo_status: str | None = None,
    include_unmatched: bool = True,
    group_by: str = "sku",
    db: Session = Depends(get_db),
) -> dict[str, object]:
    rows = get_sku_order_rows(db, build_sku_order_filters(start_date, end_date, sku, brand, category, order_status, woo_status, include_unmatched, group_by, None, None))
    return build_sku_orders_summary(rows)


@router.get("/sku-orders/export")
def export_sku_orders_report(
    start_date: date | None = None,
    end_date: date | None = None,
    sku: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    order_status: str | None = None,
    woo_status: str | None = None,
    include_unmatched: bool = True,
    group_by: str = "sku",
    db: Session = Depends(get_db),
) -> Response:
    rows = get_sku_order_rows(db, build_sku_order_filters(start_date, end_date, sku, brand, category, order_status, woo_status, include_unmatched, group_by, None, None))
    return Response(content=export_sku_orders_csv(rows), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="pongo-sku-orders-report.csv"'})


@router.get("/inventory-valuation")
def inventory_valuation_report(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    return inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, limit, offset)


@router.get("/inventory-valuation/summary")
def inventory_valuation_summary(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, None, 0)
    return summarize_inventory_rows(rows)


@router.get("/inventory-valuation/export")
def inventory_valuation_export(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> Response:
    rows = inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, None, 0)
    return csv_response("pongo-inventory-valuation-report.csv", rows)


@router.get("/low-stock")
def low_stock_report(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    return [row for row in inventory_valuation_rows(db, warehouse, inventory_location, sku, barcode, brand, category, limit, offset) if row["under_par"] or row["sellable"] < 0]


@router.get("/low-stock/summary")
def low_stock_summary(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = low_stock_report(warehouse, inventory_location, sku, barcode, brand, category, None, 0, db)
    return {"total_rows": len(rows), "under_par_count": sum(1 for row in rows if row["under_par"]), "negative_sellable_count": sum(1 for row in rows if row["sellable"] < 0), "suggested_order_qty": sum(row.get("suggested_order_qty", 0) for row in rows)}


@router.get("/low-stock/export")
def low_stock_export(warehouse: str | None = None, inventory_location: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-low-stock-report.csv", low_stock_report(warehouse, inventory_location, sku, barcode, brand, category, None, 0, db))


@router.get("/stock-movement-ledger")
def stock_movement_ledger_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, movement_type: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    rows = movement_ledger_rows(db, start_date, end_date, sku, barcode, warehouse, inventory_location, movement_type)
    return rows[offset : offset + limit] if limit else rows[offset:]


@router.get("/stock-movement-ledger/summary")
def stock_movement_ledger_summary(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, movement_type: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = movement_ledger_rows(db, start_date, end_date, sku, barcode, warehouse, inventory_location, movement_type)
    return {"total_rows": len(rows), "total_quantity_change": sum(row["quantity_change"] for row in rows), "movement_types": sorted({row["movement_type"] for row in rows})}


@router.get("/stock-movement-ledger/export")
def stock_movement_ledger_export(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, movement_type: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-stock-movement-ledger-report.csv", movement_ledger_rows(db, start_date, end_date, sku, barcode, warehouse, inventory_location, movement_type))


@router.get("/item-activity")
def item_activity_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, movement_type: str | None = None, limit: int | None = None, offset: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    return stock_movement_ledger_report(start_date, end_date, sku, barcode, None, None, movement_type, limit, offset, db)


@router.get("/item-activity/summary")
def item_activity_summary(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = movement_ledger_rows(db, start_date, end_date, sku, barcode, None, None, None)
    return {"total_rows": len(rows), "stock_increase": sum(row["quantity_change"] for row in rows if row["quantity_change"] > 0), "stock_decrease": sum(row["quantity_change"] for row in rows if row["quantity_change"] < 0)}


@router.get("/item-activity/export")
def item_activity_export(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, barcode: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-item-activity-report.csv", movement_ledger_rows(db, start_date, end_date, sku, barcode, None, None, None))


@router.get("/location-utilization")
def location_utilization_report(warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    rows = inventory_valuation_rows(db, warehouse, inventory_location, None, None, None, None, None, 0)
    grouped: dict[tuple, dict] = {}
    for row in rows:
        key = (row["warehouse"], row["inventory_location"], row.get("location_code"), row.get("location_name"))
        group = grouped.setdefault(key, {"warehouse": row["warehouse"], "inventory_location": row["inventory_location"], "location_code": row.get("location_code"), "location_name": row.get("location_name"), "sku_count": 0, "total_units": 0, "allocated_units": 0, "sellable_units": 0, "inventory_value": 0, "under_par_skus": 0})
        group["sku_count"] += 1
        group["total_units"] += row["in_stock"]
        group["allocated_units"] += row["allocated"]
        group["sellable_units"] += row["sellable"]
        group["inventory_value"] += row["inventory_value"]
        group["under_par_skus"] += 1 if row["under_par"] else 0
    return list(grouped.values())


@router.get("/location-utilization/summary")
def location_utilization_summary(warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> dict:
    rows = location_utilization_report(warehouse, inventory_location, db)
    return {"locations_count": len(rows), "total_skus": sum(row["sku_count"] for row in rows), "total_units": sum(row["total_units"] for row in rows), "inventory_value": sum(row["inventory_value"] for row in rows)}


@router.get("/location-utilization/export")
def location_utilization_export(warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-location-utilization-report.csv", location_utilization_report(warehouse, inventory_location, db))


@router.get("/margin-by-sku")
def margin_by_sku_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, brand: str | None = None, category: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(OrderItem, InventoryItem).join(InventoryItem, OrderItem.inventory_item_id == InventoryItem.id, isouter=True)
    if sku:
        statement = statement.where(OrderItem.sku == sku)
    rows = {}
    for order_item, item in db.execute(statement).all():
        if start_date and order_item.created_at.date() < start_date:
            continue
        if end_date and order_item.created_at.date() > end_date:
            continue
        if brand and (item.brand if item else order_item.brand) != brand:
            continue
        if category and (item.category if item else None) != category:
            continue
        key = order_item.sku or (item.sku if item else f"line-{order_item.id}")
        unit_cost = order_item.unit_cost or (item.unit_cost if item else 0) or 0
        revenue = order_item.line_total or order_item.total_price or 0
        quantity = order_item.quantity_ordered or order_item.ordered_qty or 0
        row = rows.setdefault(key, {"sku": key, "description": order_item.description or (item.description if item else None), "brand": item.brand if item else order_item.brand, "quantity_ordered": 0, "quantity_fulfilled": 0, "revenue": 0, "estimated_cost": 0, "estimated_margin": 0, "estimated_margin_percent": 0, "order_count": 0, "first_order_date": order_item.created_at, "last_order_date": order_item.created_at})
        row["quantity_ordered"] += float(quantity)
        row["quantity_fulfilled"] += float(order_item.quantity_fulfilled or order_item.fulfilled_qty or 0)
        row["revenue"] += float(revenue)
        row["estimated_cost"] += float(quantity * unit_cost)
        row["order_count"] += 1
        row["first_order_date"] = min(row["first_order_date"], order_item.created_at)
        row["last_order_date"] = max(row["last_order_date"], order_item.created_at)
    for row in rows.values():
        row["estimated_margin"] = row["revenue"] - row["estimated_cost"]
        row["estimated_margin_percent"] = (row["estimated_margin"] / row["revenue"] * 100) if row["revenue"] else 0
    return list(rows.values())


@router.get("/margin-by-sku/summary")
def margin_by_sku_summary(db: Session = Depends(get_db)) -> dict:
    rows = margin_by_sku_report(db=db)
    return {"total_skus": len(rows), "revenue": sum(row["revenue"] for row in rows), "estimated_cost": sum(row["estimated_cost"] for row in rows), "estimated_margin": sum(row["estimated_margin"] for row in rows)}


@router.get("/margin-by-sku/export")
def margin_by_sku_export(db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-margin-by-sku-report.csv", margin_by_sku_report(db=db))


@router.get("/receiving-cost")
def receiving_cost_report(start_date: date | None = None, end_date: date | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(ReceiptItem, Receipt).join(Receipt, ReceiptItem.receipt_id == Receipt.id)
    rows = []
    for line, receipt in db.execute(statement).all():
        if start_date and line.created_at.date() < start_date:
            continue
        if end_date and line.created_at.date() > end_date:
            continue
        if sku and line.sku != sku:
            continue
        if warehouse and line.warehouse != warehouse:
            continue
        if inventory_location and line.inventory_location_name != inventory_location:
            continue
        rows.append({"receipt_number": receipt.receipt_number, "received_date": str(line.received_date or receipt.received_date or ""), "sku": line.sku, "description": line.description, "warehouse": line.warehouse, "inventory_location": line.inventory_location_name, "quantity": float(line.quantity_received or line.quantity or 0), "unit_cost": float(line.unit_cost or 0), "total_cost": float(line.unit_cost_total or 0), "brand": line.brand, "category": line.category})
    return rows


@router.get("/receiving-cost/summary")
def receiving_cost_summary(db: Session = Depends(get_db)) -> dict:
    rows = receiving_cost_report(db=db)
    return {"total_rows": len(rows), "total_quantity": sum(row["quantity"] for row in rows), "total_cost": sum(row["total_cost"] for row in rows)}


@router.get("/receiving-cost/export")
def receiving_cost_export(db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-receiving-cost-report.csv", receiving_cost_report(db=db))


@router.get("/adjustments")
def adjustments_report(adjustment_type: str | None = None, sku: str | None = None, warehouse: str | None = None, inventory_location: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(StockAdjustmentLine, StockAdjustment).join(StockAdjustment, StockAdjustmentLine.adjustment_id == StockAdjustment.id)
    rows = []
    for line, adjustment in db.execute(statement).all():
        if adjustment_type and adjustment.adjustment_type != adjustment_type:
            continue
        if sku and line.sku != sku:
            continue
        if warehouse and line.warehouse != warehouse:
            continue
        if inventory_location and line.inventory_location != inventory_location:
            continue
        value_impact = (line.quantity_change or 0) * (line.unit_cost or 0)
        rows.append({"adjustment_number": adjustment.adjustment_number, "date": line.created_at, "adjustment_type": adjustment.adjustment_type, "reason": adjustment.reason, "sku": line.sku, "description": line.description, "warehouse": line.warehouse, "inventory_location": line.inventory_location, "old_qty": float(line.old_quantity or 0), "new_qty": float(line.new_quantity or 0), "quantity_change": float(line.quantity_change or 0), "unit_cost": float(line.unit_cost or 0), "estimated_value_impact": float(value_impact)})
    return rows


@router.get("/adjustments/summary")
def adjustments_summary(db: Session = Depends(get_db)) -> dict:
    rows = adjustments_report(db=db)
    return {"total_rows": len(rows), "total_quantity_change": sum(row["quantity_change"] for row in rows), "estimated_value_impact": sum(row["estimated_value_impact"] for row in rows)}


@router.get("/adjustments/export")
def adjustments_export(db: Session = Depends(get_db)) -> Response:
    return csv_response("pongo-adjustments-report.csv", adjustments_report(db=db))


def inventory_valuation_rows(db: Session, warehouse: str | None, inventory_location: str | None, sku: str | None, barcode: str | None, brand: str | None, category: str | None, limit: int | None, offset: int) -> list[dict]:
    statement = select(InventoryItemLocation, InventoryItem).join(InventoryItem, InventoryItemLocation.inventory_item_id == InventoryItem.id)
    if warehouse:
        statement = statement.where(InventoryItemLocation.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(InventoryItemLocation.inventory_location == inventory_location)
    if sku:
        statement = statement.where(InventoryItem.sku == sku)
    if barcode:
        statement = statement.where(InventoryItem.barcode == barcode)
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if category:
        statement = statement.where(InventoryItem.category == category)
    statement = statement.order_by(InventoryItem.sku.asc().nullslast(), InventoryItemLocation.warehouse.asc().nullslast(), InventoryItemLocation.inventory_location.asc().nullslast())
    if offset:
        statement = statement.offset(offset)
    if limit:
        statement = statement.limit(limit)
    rows = []
    for location, item in db.execute(statement).all():
        unit_cost = float(item.unit_cost or 0)
        sales_price = float(item.sales_price or 0)
        in_stock = float(location.in_stock or 0)
        allocated = float(location.allocated or 0)
        sellable = float(location.sellable or (location.in_stock or 0) - (location.allocated or 0))
        par_level = float(location.par_level if location.par_level is not None else item.par_level or 0)
        rows.append({"sku": item.sku, "barcode": item.barcode, "description": item.description, "brand": item.brand, "category": item.category, "warehouse": location.warehouse, "inventory_location": location.inventory_location, "location_code": location.location_code, "location_name": location.location_name, "in_stock": in_stock, "allocated": allocated, "sellable": sellable, "unit_cost": unit_cost, "inventory_value": in_stock * unit_cost, "sales_price": sales_price, "retail_value": in_stock * sales_price, "margin_estimate": sales_price - unit_cost, "par_level": par_level, "under_par": bool(location.under_par), "reorder_enabled": bool(item.reorder), "default_econ_order": float(item.default_econ_order or 0), "suggested_order_qty": max(0, par_level - in_stock)})
    return rows


def summarize_inventory_rows(rows: list[dict]) -> dict:
    return {"total_skus": len({row["sku"] for row in rows}), "total_units": sum(row["in_stock"] for row in rows), "total_inventory_value": sum(row["inventory_value"] for row in rows), "total_retail_value": sum(row["retail_value"] for row in rows), "locations_count": len({(row["warehouse"], row["inventory_location"]) for row in rows}), "under_par_count": sum(1 for row in rows if row["under_par"])}


def movement_ledger_rows(db: Session, start_date: date | None, end_date: date | None, sku: str | None, barcode: str | None, warehouse: str | None, inventory_location: str | None, movement_type: str | None) -> list[dict]:
    statement = select(StockMovement).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    if sku:
        statement = statement.where(StockMovement.sku == sku)
    if barcode:
        statement = statement.where(StockMovement.barcode == barcode)
    if warehouse:
        statement = statement.where(StockMovement.warehouse == warehouse)
    if inventory_location:
        statement = statement.where(StockMovement.inventory_location_name == inventory_location)
    rows = []
    for movement in db.scalars(statement).all():
        value = movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type)
        if movement_type and value != movement_type:
            continue
        if start_date and movement.created_at.date() < start_date:
            continue
        if end_date and movement.created_at.date() > end_date:
            continue
        rows.append({"date": movement.created_at, "movement_type": value, "reference_number": movement.reference_number, "sku": movement.sku, "barcode": movement.barcode, "description": movement.inventory_item.description if movement.inventory_item else None, "warehouse": movement.warehouse, "inventory_location": movement.inventory_location_name, "from_location": movement.from_inventory_location, "to_location": movement.to_inventory_location, "quantity_change": float(movement.quantity_change or 0), "old_location_stock": float(movement.old_location_stock or movement.old_stock or 0), "new_location_stock": float(movement.new_location_stock or movement.new_stock or 0), "reason": movement.reason, "notes": movement.notes})
    return rows


def csv_response(filename: str, rows: list[dict]) -> Response:
    buffer = StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def build_filters(
    date_from: date | None,
    date_to: date | None,
    warehouse: str | None,
    inventory_location: str | None,
    sku: str | None,
    barcode: str | None,
    category: str | None,
    brand: str | None,
    receipt_number: str | None,
    reference_number: str | None,
    created_by: str | None,
) -> ReceivedInventoryFilters:
    return ReceivedInventoryFilters(
        date_from=date_from,
        date_to=date_to,
        warehouse=warehouse,
        inventory_location=inventory_location,
        sku=sku,
        barcode=barcode,
        category=category,
        brand=brand,
        receipt_number=receipt_number,
        reference_number=reference_number,
        created_by=created_by,
    )


def build_fulfillment_filters(
    date_from: date | None,
    date_to: date | None,
    warehouse: str | None,
    inventory_location: str | None,
    sku: str | None,
    barcode: str | None,
    category: str | None,
    brand: str | None,
    fulfillment_number: str | None,
    woo_order_number: str | None,
    woo_order_id: int | None,
    customer_email: str | None,
    local_status: str | None,
    created_by: str | None,
) -> FulfillmentReportFilters:
    return FulfillmentReportFilters(
        date_from=date_from,
        date_to=date_to,
        warehouse=warehouse,
        inventory_location=inventory_location,
        sku=sku,
        barcode=barcode,
        category=category,
        brand=brand,
        fulfillment_number=fulfillment_number,
        woo_order_number=woo_order_number,
        woo_order_id=woo_order_id,
        customer_email=customer_email,
        local_status=local_status,
        created_by=created_by,
    )


def build_sku_order_filters(
    start_date: date | None,
    end_date: date | None,
    sku: str | None,
    brand: str | None,
    category: str | None,
    order_status: str | None,
    woo_status: str | None,
    include_unmatched: bool,
    group_by: str,
    limit: int | None,
    offset: int | None,
) -> SkuOrdersFilters:
    safe_group_by = group_by if group_by in {"sku", "brand", "category", "location"} else "sku"
    return SkuOrdersFilters(
        start_date=start_date,
        end_date=end_date,
        sku=sku,
        brand=brand,
        category=category,
        order_status=order_status,
        woo_status=woo_status,
        include_unmatched=include_unmatched,
        group_by=safe_group_by,
        limit=limit,
        offset=offset,
    )
