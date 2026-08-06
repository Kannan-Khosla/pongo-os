from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.performance import MetricCache
from app.services.business_dashboard import admin_today, get_cached_business_metric
from app.services.insights import get_cached_insight
from app.services.metric_cache import current_metric_version, metric_cache_key


logger = logging.getLogger(__name__)

INSIGHT_DASHBOARDS = (
    "overview",
    "orders-revenue",
    "customer-metrics",
    "customer-segmentation",
    "product-sku",
    "subscriptions",
    "subscription-products",
    "inventory-forecasting",
    "coupons",
    "payment-health",
    "geography",
    "product-affinity",
    "reorder-forecast",
)
DATE_DASHBOARDS = {
    "overview",
    "orders-revenue",
    "customer-metrics",
    "customer-segmentation",
    "product-sku",
    "inventory-forecasting",
    "coupons",
    "payment-health",
    "geography",
    "product-affinity",
    "reorder-forecast",
}
LONG_RANGE_DASHBOARDS = ("overview", "orders-revenue")


def warm_next_standard_metric(settings: Settings) -> bool:
    """Warm at most one stale screen per idle worker cycle."""
    today = admin_today(settings=settings)
    with SessionLocal() as db:
        version = current_metric_version(db)
        for label, namespace, params, builder in standard_metric_targets(db, today):
            cached = db.get(MetricCache, metric_cache_key(namespace, params))
            if cached is not None and cached.source_version == version:
                continue
            return _warm(db, label, builder)
    return False


def warm_next_requested_metric() -> bool:
    """Refresh one stale metric a user has already viewed."""
    with SessionLocal() as db:
        version = current_metric_version(db)
        cached = db.scalar(
            select(MetricCache)
            .where(
                MetricCache.source_version < version,
                MetricCache.refresh_requested_at.is_not(None),
            )
            .order_by(MetricCache.refresh_requested_at, MetricCache.cache_key)
        )
        if cached is None:
            return False
        namespace = cached.namespace
        params = cached.params
        if namespace.startswith("insight:"):
            dashboard = namespace.removeprefix("insight:")
            return _warm(
                db,
                namespace,
                lambda: get_cached_insight(db, dashboard, params, force_refresh=True),
            )
        if namespace.startswith("business-dashboard:"):
            section = namespace.removeprefix("business-dashboard:")
            target_date = date.fromisoformat(params["date"]) if params.get("date") else None
            return _warm(
                db,
                namespace,
                lambda: get_cached_business_metric(
                    db,
                    section,
                    target_date,
                    mode=params.get("mode"),
                    force_refresh=True,
                ),
            )
        cached.refresh_requested_at = None
        db.commit()
        logger.warning("Discarded unsupported metric refresh request for %s", namespace)
        return True


def standard_metric_targets(db: Session, today: date):
    dashboard_params = {"date": today.isoformat(), "mode": None}
    yield (
        "business dashboard",
        "business-dashboard:dashboard",
        dashboard_params,
        lambda: get_cached_business_metric(db, "dashboard", today, force_refresh=True),
    )

    default_start, default_end = completed_month_range(today, 1)
    for dashboard in INSIGHT_DASHBOARDS:
        params = insight_params(
            default_start if dashboard in DATE_DASHBOARDS else None,
            default_end if dashboard in DATE_DASHBOARDS else None,
        )
        yield dashboard, f"insight:{dashboard}", params, lambda dashboard=dashboard, params=params: get_cached_insight(
            db, dashboard, params, force_refresh=True
        )

    for months in (2, 3, 12):
        start, end = completed_month_range(today, months)
        for dashboard in LONG_RANGE_DASHBOARDS:
            params = insight_params(start, end)
            yield (
                f"{dashboard}:{months}-months",
                f"insight:{dashboard}",
                params,
                lambda dashboard=dashboard, params=params: get_cached_insight(
                    db, dashboard, params, force_refresh=True
                ),
            )

    compare_start, compare_end = completed_month_range(default_start, 1)
    for dashboard in LONG_RANGE_DASHBOARDS:
        params = insight_params(default_start, default_end)
        params.update(compare_start_date=compare_start.isoformat(), compare_end_date=compare_end.isoformat())
        yield (
            f"{dashboard}:month-comparison",
            f"insight:{dashboard}",
            params,
            lambda dashboard=dashboard, params=params: get_cached_insight(
                db, dashboard, params, force_refresh=True
            ),
        )


def insight_params(start: date | None, end: date | None) -> dict[str, Any]:
    return {
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "compare_start_date": None,
        "compare_end_date": None,
        "granularity": "day",
        "brand": None,
        "category": None,
        "sku": None,
        "customer_email": None,
        "city": None,
        "postal_code": None,
        "payment_method": None,
        "order_status": None,
        "limit": 100,
        "offset": 0,
    }


def completed_month_range(today: date, months: int) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)
    month_index = (end.year * 12 + end.month - 1) - (months - 1)
    start = date(month_index // 12, month_index % 12 + 1, 1)
    return start, end


def _warm(db: Session, label: str, builder) -> bool:
    try:
        builder()
        db.expunge_all()
        return True
    except Exception:
        db.rollback()
        logger.exception("Unable to warm metric cache for %s", label)
        return False
