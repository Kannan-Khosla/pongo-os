import csv
from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
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
