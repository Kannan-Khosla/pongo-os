from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.orders import CompletedOrderListResponse, OpenOrderDetail, OpenOrderListResponse
from app.services.completed_orders import CompletedOrderFilters, export_completed_orders_csv, list_completed_orders
from app.services.woocommerce_orders import export_open_orders_csv, get_open_order_detail, list_open_orders

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/open", response_model=OpenOrderListResponse)
def list_open_order_queue(
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    db: Session = Depends(get_db),
) -> OpenOrderListResponse:
    return list_open_orders(db, search=search, woo_status=woo_status, availability_status=availability_status, matched_status=matched_status)


@router.get("/open/export")
def export_open_order_queue(
    search: str | None = None,
    woo_status: str | None = None,
    availability_status: str | None = None,
    matched_status: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_text = export_open_orders_csv(db, search=search, woo_status=woo_status, availability_status=availability_status, matched_status=matched_status)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-open-orders-export.csv"'},
    )


@router.get("/completed", response_model=CompletedOrderListResponse)
def list_completed_order_queue(
    local_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> CompletedOrderListResponse:
    return list_completed_orders(db, CompletedOrderFilters(local_status=local_status, date_from=date_from, date_to=date_to, customer_email=customer_email, woo_order_number=woo_order_number, sku=sku, barcode=barcode, search=search))


@router.get("/completed/export")
def export_completed_order_queue(
    local_status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    sku: str | None = None,
    barcode: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    csv_text = export_completed_orders_csv(db, CompletedOrderFilters(local_status=local_status, date_from=date_from, date_to=date_to, customer_email=customer_email, woo_order_number=woo_order_number, sku=sku, barcode=barcode, search=search))
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-completed-orders-export.csv"'},
    )


@router.get("/{order_id}", response_model=OpenOrderDetail)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OpenOrderDetail:
    order = get_open_order_detail(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
