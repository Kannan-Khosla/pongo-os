from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.orders import Order
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
def woocommerce_open_orders(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = getattr(request.state, "user", None)
    if getattr(user, "access_level", None) == "demo":
        cached = get_cached_business_metric(db, "open-orders")
        demo_rows = cached.get("rows", [])
        count = len(demo_rows)
        start = (page - 1) * page_size
        page_rows = demo_rows[start : start + page_size]
        local_ids = local_order_ids(db, [row.get("woo_order_id") for row in page_rows])
        return {
            "source": "demo",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "statuses": {},
            "summary": {"open_orders_count": count},
            "total": count,
            "page": page,
            "page_size": page_size,
            "total_pages": (count + page_size - 1) // page_size if count else 0,
            "orders": [sanitize_demo_order(row, local_ids) for row in page_rows],
        }

    try:
        client = WooCommerceClient(effective_woocommerce_settings(db))
        client.timeout_seconds = min(client.timeout_seconds, 5)
        remote_orders = client.list_orders(page=page, per_page=page_size, status="processing")
        processing_pages, processing_total = woo_pagination(client.last_response_headers)
        if processing_total is None or processing_pages is None:
            raise WooCommerceClientError("WooCommerce response omitted pagination totals.")
        sanitized_orders = sanitize_live_orders(db, remote_orders)
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
        "total": processing_total,
        "page": page,
        "page_size": page_size,
        "total_pages": processing_pages,
        "orders": sanitized_orders,
    }


def sanitize_live_orders(db: Session, remote_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not all(isinstance(row, dict) for row in remote_orders):
        raise WooCommerceClientError("WooCommerce returned an invalid order row.")
    if any(str(row.get("status") or "").casefold() != "processing" for row in remote_orders):
        raise WooCommerceClientError("WooCommerce returned a non-processing row for the processing-order query.")
    if any(not isinstance(row.get("id"), int) or row["id"] <= 0 for row in remote_orders):
        raise WooCommerceClientError("WooCommerce returned an invalid order identifier.")
    rows = remote_orders
    ids = local_order_ids(db, [row.get("id") for row in rows])
    return [
        {
            "woo_order_id": int(row["id"]),
            "local_order_id": ids.get(int(row["id"])),
            "order_number": str(row.get("number") or row["id"]),
            "status": "processing",
            "customer_name": " ".join(
                part.strip()
                for part in [
                    str((row.get("billing") or {}).get("first_name") or ""),
                    str((row.get("billing") or {}).get("last_name") or ""),
                ]
                if part.strip()
            ),
            "customer_email": str((row.get("billing") or {}).get("email") or ""),
            "currency": str(row.get("currency") or ""),
            "total": str(row.get("total") or "0"),
            "date_created": row.get("date_created_gmt") or row.get("date_created"),
            "date_modified": row.get("date_modified_gmt") or row.get("date_modified"),
            "line_count": len(row.get("line_items") or []),
        }
        for row in rows
    ]


def sanitize_demo_order(row: dict[str, Any], ids: dict[int, int]) -> dict[str, Any]:
    woo_order_id = row.get("woo_order_id")
    return {
        "woo_order_id": woo_order_id,
        "local_order_id": ids.get(woo_order_id) if woo_order_id is not None else None,
        "order_number": str(row.get("order_number") or woo_order_id or ""),
        "status": "processing",
        "customer_name": str(row.get("customer_name") or "Demo customer"),
        "customer_email": str(row.get("customer_email") or ""),
        "currency": "CAD",
        "total": str(row.get("order_total") or "0"),
        "date_created": row.get("placed_on"),
        "date_modified": None,
        "line_count": int(row.get("item_count") or 0),
    }


def local_order_ids(db: Session, woo_order_ids: list[Any]) -> dict[int, int]:
    selected = {int(value) for value in woo_order_ids if value not in (None, "")}
    if not selected:
        return {}
    return {
        woo_id: local_id
        for woo_id, local_id in db.execute(
            select(Order.woo_order_id, Order.id).where(
                Order.woo_order_id.in_(selected),
                Order.is_historical_snapshot.is_(False),
            )
        ).all()
        if woo_id is not None
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
