from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.business_dashboard import get_cached_business_metric

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


@router.get("/subscriptions")
def subscriptions(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "subscriptions", date)


@router.get("/revenue-comparison")
def revenue_comparison(date: date | None = None, mode: str = "month_to_date", db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "revenue-comparison", date, mode=mode)


@router.get("/order-map")
def order_map(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return get_cached_business_metric(db, "order-map", date)
