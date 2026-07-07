from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.orders import OpenOrderDetail, OpenOrderListResponse
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


@router.get("/{order_id}", response_model=OpenOrderDetail)
def get_order(order_id: int, db: Session = Depends(get_db)) -> OpenOrderDetail:
    order = get_open_order_detail(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
