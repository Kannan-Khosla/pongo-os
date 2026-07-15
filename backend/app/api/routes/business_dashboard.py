from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.business_dashboard import build_business_dashboard, build_open_orders, build_order_map, build_revenue_comparison, build_subscriptions, build_today

router = APIRouter(prefix="/business-dashboard", tags=["business-dashboard"])


@router.get("")
def business_dashboard(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_business_dashboard(db, date)


@router.get("/today")
def today(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_today(db, date)


@router.get("/open-orders")
def open_orders(db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_open_orders(db)


@router.get("/subscriptions")
def subscriptions(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_subscriptions(db, date)


@router.get("/revenue-comparison")
def revenue_comparison(date: date | None = None, mode: str = "month_to_date", db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_revenue_comparison(db, date, mode)


@router.get("/order-map")
def order_map(date: date | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    return build_order_map(db, date)
