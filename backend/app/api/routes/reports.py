import csv
from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.reports import ReceivedInventoryReportRow, ReceivedInventorySummaryResponse
from app.services.received_inventory_report import (
    RECEIVED_INVENTORY_CSV_COLUMNS,
    ReceivedInventoryFilters,
    build_received_inventory_summary,
    get_received_inventory_rows,
    received_inventory_row_to_csv,
)

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
