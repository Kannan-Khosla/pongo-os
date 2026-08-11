from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.business_dashboard import get_cached_business_metric
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_order_reconciliation import woo_pagination

router = APIRouter(prefix="/business-dashboard", tags=["business-dashboard"])


@router.get("")
def business_dashboard(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "dashboard", date)


@router.get("/today")
def today(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "today", date)


@router.get("/open-orders")
def open_orders(db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "open-orders")


@router.get("/woocommerce-open-orders")
def woocommerce_open_orders(request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if getattr(user, "access_level", None) == "demo":
        count = get_cached_business_metric(db, "open-orders")["summary"]["open_orders_count"]
        return {
            "source": "demo",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "statuses": {},
            "summary": {"open_orders_count": count},
        }

    try:
        client = WooCommerceClient(effective_woocommerce_settings(db))
        client.timeout_seconds = min(client.timeout_seconds, 5)
        client.list_orders(page=1, per_page=1, status="processing")
        _, processing_total = woo_pagination(client.last_response_headers)
        if processing_total is None:
            raise WooCommerceClientError("WooCommerce response omitted pagination totals.")
    except (ValueError, WooCommerceClientError) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "woocommerce_open_orders_unavailable",
                "message": "Live WooCommerce open-order count is temporarily unavailable.",
            },
        ) from exc
    return {
        "source": "woocommerce",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "statuses": {"processing": processing_total},
        "summary": {"open_orders_count": processing_total},
    }


@router.get("/subscriptions")
def subscriptions(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "subscriptions", date)


@router.get("/revenue-comparison")
def revenue_comparison(date: date | None = None, mode: str = "month_to_date", db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "revenue-comparison", date, mode=mode)


@router.get("/order-map")
def order_map(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "order-map", date)
