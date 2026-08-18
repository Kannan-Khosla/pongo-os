from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.insights import InsightResponse
from app.services.insights_sql import build_insight
from app.services.metric_cache import cached_metric_payload
from app.services.woocommerce_subscriptions import overlay_subscription_freshness


EXPORT_COLUMNS = {
    "orders-revenue": ["date", "order_count", "gross_sales", "net_sales", "units_sold"],
    "customer-metrics": ["customer_key", "customer_name", "email", "order_count", "lifetime_spend", "first_order_date", "last_order_date"],
    "product-sku": ["sku", "description", "brand", "category", "units_sold", "order_count", "customer_count", "revenue", "current_sellable"],
    "reorder-forecast": ["customer_email", "customer_name", "last_order_date", "most_repeated_sku", "average_reorder_interval_days", "expected_next_order_date", "days_overdue", "churn_risk_score", "recommended_action"],
    "geography": ["city", "postal_code", "order_count", "customer_count", "revenue", "average_order_value", "repeat_customer_rate", "last_order_date"],
}


def get_cached_insight(
    db: Session,
    dashboard: str,
    params: dict[str, Any] | None = None,
    *,
    force_refresh: bool = False,
) -> InsightResponse:
    params = params or {}
    payload = cached_metric_payload(
        db,
        f"insight:{dashboard}",
        params,
        lambda: build_insight(db, dashboard, params).model_dump(mode="json"),
        force_refresh=force_refresh,
    )
    if dashboard in {"subscriptions", "subscription-products"}:
        payload = overlay_subscription_freshness(db, payload)
    return InsightResponse.model_validate(payload)


def export_insight_csv(db: Session, dashboard: str, params: dict[str, Any] | None = None) -> str:
    # Exports preserve the pre-existing full-result behavior; the interactive
    # JSON endpoints are the surfaces that use bounded drill-down pages.
    result = build_insight(db, dashboard, {**(params or {}), "_export": True, "limit": 100_000, "offset": 0})
    columns = EXPORT_COLUMNS[dashboard]
    rows = result.rows or result.trends.get("daily_revenue", [])
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()
