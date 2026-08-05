from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from itertools import combinations
from numbers import Number
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.core.config import get_settings
from app.schemas.insights import DataQualityWarning, InsightResponse
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError


SUCCESS_STATUSES = {"completed", "processing", "fulfilled", "partially_fulfilled", "open", "allocated", "picked", "refunded"}
FAILED_STATUSES = {"failed", "cancelled", "canceled"}
EXPORT_COLUMNS = {
    "orders-revenue": ["date", "order_count", "gross_sales", "net_sales", "units_sold"],
    "customer-metrics": ["customer_key", "customer_name", "email", "order_count", "lifetime_spend", "first_order_date", "last_order_date"],
    "product-sku": ["sku", "description", "brand", "category", "units_sold", "order_count", "customer_count", "revenue", "current_sellable"],
    "reorder-forecast": ["customer_email", "customer_name", "last_order_date", "most_repeated_sku", "average_reorder_interval_days", "expected_next_order_date", "days_overdue", "churn_risk_score", "recommended_action"],
    "geography": ["city", "postal_code", "order_count", "customer_count", "revenue", "average_order_value", "repeat_customer_rate", "last_order_date"],
}


def build_insight(db: Session, dashboard: str, params: dict[str, Any] | None = None) -> InsightResponse:
    params = params or {}
    context = build_context(db, params)
    builders = {
        "overview": overview,
        "orders-revenue": orders_revenue,
        "customer-metrics": customer_metrics,
        "customer-segmentation": customer_segmentation,
        "product-sku": product_sku,
        "subscriptions": subscriptions,
        "subscription-products": subscription_products,
        "inventory-forecasting": inventory_forecasting,
        "coupons": coupons,
        "payment-health": payment_health,
        "geography": geography,
        "product-affinity": product_affinity,
        "reorder-forecast": reorder_forecast,
    }
    result = builders[dashboard](context)
    apply_woo_analytics(db, dashboard, params, result)
    if params.get("compare_start_date") and params.get("compare_end_date"):
        comparison_params = {
            **params,
            "start_date": params["compare_start_date"],
            "end_date": params["compare_end_date"],
            "compare_start_date": None,
            "compare_end_date": None,
        }
        previous = builders[dashboard](build_context(db, comparison_params))
        apply_woo_analytics(db, dashboard, comparison_params, previous)
        result.comparison = {
            "start_date": params["compare_start_date"],
            "end_date": params["compare_end_date"],
            "summary": previous.summary,
            "changes": summary_changes(result.summary, previous.summary),
        }
    return result


def apply_woo_analytics(db: Session, dashboard: str, params: dict[str, Any], result: InsightResponse) -> None:
    if dashboard not in {"overview", "orders-revenue"} or not params.get("start_date") or not params.get("end_date"):
        return
    if any(params.get(key) for key in ("brand", "category", "sku", "customer_email", "city", "postal_code", "payment_method", "order_status")):
        return
    settings = get_settings()
    if settings.app_env in {"test", "e2e"}:
        return
    try:
        client = WooCommerceClient(effective_woocommerce_settings(db, settings))
        if not client.configured:
            return
        stats = client.analytics_stats(
            "revenue",
            after=str(params["start_date"]),
            before=str(params["end_date"]),
            interval=str(params.get("granularity") or "day"),
        )
    except (WooCommerceClientError, ValueError) as error:
        result.data_quality.append(DataQualityWarning(code="woo_analytics_unavailable", severity="warning", message=f"WooCommerce Analytics could not be loaded: {error.message if isinstance(error, WooCommerceClientError) else str(error)}"))
        return
    totals = stats["totals"]
    total_orders = int(totals.get("orders_count") or 0)
    exact = {
        "total_orders": total_orders,
        "gross_sales": dec(totals.get("gross_sales")),
        "net_sales": dec(totals.get("net_revenue")),
        "average_order_value": dec(totals.get("avg_order_value")) if total_orders else None,
        "units_sold": dec(totals.get("num_items_sold")),
        "refund_amount": dec(totals.get("refunds")),
        "refund_rate": percent(totals.get("refunds"), totals.get("gross_sales")),
        "discount_amount": dec(totals.get("coupons")),
    }
    if dashboard == "overview":
        exact.update({
            "coupon_discount_total": dec(totals.get("coupons")),
        })
    else:
        exact.update({
            "units_per_order": dec(totals.get("avg_items_per_order")),
            "discount_rate": percent(totals.get("coupons"), totals.get("gross_sales")),
            "shipping_revenue": dec(totals.get("shipping")),
            "tax_total": dec(totals.get("taxes")),
        })
    result.summary.update(exact)
    if result.metrics:
        result.metrics.update(exact)
    trend = []
    for interval in stats.get("intervals") or []:
        subtotal = interval.get("subtotals") or {}
        trend.append({
            "date": str(interval.get("interval") or interval.get("date_start") or "")[:10],
            "order_count": int(subtotal.get("orders_count") or 0),
            "gross_sales": dec(subtotal.get("gross_sales")),
            "net_sales": dec(subtotal.get("net_revenue")),
            "units_sold": dec(subtotal.get("num_items_sold")),
        })
    result.trends["daily_revenue"] = trend
    result.trends["revenue_by_day"] = trend
    result.trends["orders_by_day"] = [{"date": row["date"], "order_count": row["order_count"]} for row in trend]
    if dashboard == "orders-revenue":
        result.rows = trend
    result.data_quality = [entry for entry in result.data_quality if entry.code not in {"missing_refund_data", "limited_order_history"}]
    result.empty_state = None if total_orders else result.empty_state


def export_insight_csv(db: Session, dashboard: str, params: dict[str, Any] | None = None) -> str:
    result = build_insight(db, dashboard, params)
    columns = EXPORT_COLUMNS[dashboard]
    rows = result.rows or result.trends.get("daily_revenue", [])
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def build_context(db: Session, params: dict[str, Any]) -> dict[str, Any]:
    orders = list(db.scalars(
        select(Order)
        .where(or_(Order.is_historical_snapshot.is_(False), Order.historical_source_present.is_(True)))
        .options(selectinload(Order.items).selectinload(OrderItem.inventory_item))
    ).all())
    items = list(db.scalars(select(InventoryItem)).all())
    item_by_id = {item.id: item for item in items}
    item_by_sku = {clean_key(item.sku): item for item in items if clean_key(item.sku)}
    start = parse_date(params.get("start_date"))
    end = parse_date(params.get("end_date"), end_of_day=True)
    filtered_orders = [order for order in orders if order_in_range(order, start, end) and order_matches(order, params, item_by_sku)]
    successful_orders = [order for order in filtered_orders if is_success_order(order)]
    all_successful_orders = [order for order in orders if is_success_order(order)]
    return {
        "orders": filtered_orders,
        "successful_orders": successful_orders,
        "all_orders": orders,
        "all_successful_orders": all_successful_orders,
        "items": items,
        "item_by_id": item_by_id,
        "item_by_sku": item_by_sku,
        "params": params,
        "start": start,
        "end": end,
        "warnings": base_warnings(filtered_orders, items),
    }


def overview(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    order_metrics = revenue_metrics(sales_ctx["orders"], sales_ctx)
    customers, new_customers, returning_customers = identified_customer_groups(sales_ctx)
    product_rows = product_rows_for_orders(sales_ctx)
    inventory_value = sum((money(item.in_stock) * money(item.unit_cost) for item in ctx["items"]), Decimal("0"))
    stockout_rows = forecast_rows(sales_ctx)
    due_rows = reorder_rows(sales_ctx)
    top_units = product_rows[0] if product_rows else None
    top_revenue = sorted(product_rows, key=lambda row: row["revenue"], reverse=True)[0] if product_rows else None
    summary = {
        **order_metrics,
        "total_customers": len(customers),
        "new_customers": len(new_customers),
        "returning_customers": len(returning_customers),
        "anonymous_orders_without_email": sum(1 for order in sales_ctx["orders"] if not normalized_email(order.customer_email)),
        "repeat_customer_rate": percent(len(returning_customers), len(customers)),
        "top_sku_by_units": top_units,
        "top_sku_by_revenue": top_revenue,
        "inventory_value": dec(inventory_value),
        "stockout_risk_count": sum(1 for row in stockout_rows if row["risk_level"] in {"high", "medium"}),
        "customers_due_to_reorder": len(due_rows),
        "coupon_discount_total": coupon_total(sales_ctx["orders"], sales_ctx),
    }
    trends = daily_trends(sales_ctx["orders"], sales_ctx)
    trends.update(
        {
            "new_vs_returning_by_month": new_vs_returning_by_month(sales_ctx["orders"], sales_ctx["all_orders"]),
            "top_brands": top_dimension(product_rows, "brand"),
            "top_categories": top_dimension(product_rows, "category"),
            "top_skus": product_rows[:10],
        }
    )
    warnings = sales_ctx["warnings"] + refund_warning(sales_ctx["orders"], sales_ctx)
    return response(
        "overview",
        summary=summary,
        trends=trends,
        tables={"stockout_risk": stockout_rows[:10], "reorder_risk": due_rows[:10]},
        warnings=warnings,
        empty_state=None if sales_ctx["orders"] else "No matching completed or active sales orders",
    )


def orders_revenue(ctx: dict[str, Any]) -> InsightResponse:
    orders = ctx["successful_orders"]
    metrics = revenue_metrics(orders, ctx)
    totals = [float(order_net_sales(order, ctx)) for order in orders]
    metrics.update(
        {
            "median_order_value": median(totals) if totals else 0,
            "units_per_order": safe_div(metrics["units_sold"], metrics["total_orders"]),
            "revenue_growth_percent": None,
            "order_growth_percent": None,
            "discount_rate": percent(metrics["discount_amount"], metrics["gross_sales"]),
            "shipping_revenue": dec(sum((money(order.shipping_total) for order in orders), Decimal("0"))),
            "tax_total": dec(sum((money(order.tax_total) for order in orders), Decimal("0"))),
        }
    )
    trends = daily_trends(orders, ctx)
    tables = {"status_breakdown": status_breakdown(orders, ctx), "payment_methods": payment_breakdown(orders, ctx)}
    warnings = base_warnings(orders, ctx["items"]) + refund_warning(orders, ctx)
    return response(
        "orders-revenue",
        summary=metrics,
        metrics=metrics,
        trends=trends,
        rows=trends["daily_revenue"],
        tables=tables,
        warnings=warnings,
        empty_state=None if orders else "No matching completed or active sales orders",
    )


def customer_metrics(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    customers, new_customers, returning_customers = identified_customer_groups(sales_ctx)
    rows = customer_rows(customers, sales_ctx)
    returning = [row for row in rows if row["customer_key"] in returning_customers]
    intervals = [row["average_days_between_orders"] for row in rows if row["average_days_between_orders"] is not None]
    summary = {
        "total_customers": len(rows),
        "new_customers": len(new_customers),
        "returning_customers": len(returning),
        "guest_customers": 0,
        "registered_customers": len(rows),
        "anonymous_orders_without_email": sum(1 for order in sales_ctx["orders"] if not normalized_email(order.customer_email)),
        "repeat_customer_rate": percent(len(returning), len(rows)),
        "average_orders_per_customer": safe_div(sum(row["order_count"] for row in rows), len(rows)),
        "average_customer_lifetime_value": safe_div(sum(row["lifetime_spend"] for row in rows), len(rows)),
        "median_customer_lifetime_value": median([row["lifetime_spend"] for row in rows]) if rows else 0,
        "average_days_between_orders": safe_div(sum(intervals), len(intervals)),
        "customers_with_1_order": sum(1 for row in rows if row["order_count"] == 1),
        "customers_with_2_orders": sum(1 for row in rows if row["order_count"] == 2),
        "customers_with_3_plus_orders": sum(1 for row in rows if row["order_count"] >= 3),
        "dormant_customers_60_days": dormant_count(rows, 60),
        "dormant_customers_90_days": dormant_count(rows, 90),
        "customers_due_to_reorder": len(reorder_rows(sales_ctx)),
    }
    return response("customer-metrics", summary=summary, metrics=summary, rows=rows[:100], tables={"top_customers": rows[:25], "customers_due_to_reorder": reorder_rows(sales_ctx)[:25], "dormant_customers": [row for row in rows if row.get("recency_days", 0) >= 60][:25]}, warnings=sales_ctx["warnings"])


def customer_segmentation(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    rows = []
    for row in customer_rows(customer_groups(sales_ctx["orders"]), sales_ctx):
        segment = segment_customer(row)
        rows.append({**row, "segment": segment})
    counts = Counter(row["segment"] for row in rows)
    revenue_by_segment = defaultdict(float)
    repeat_by_segment = defaultdict(lambda: {"repeat": 0, "total": 0})
    for row in rows:
        revenue_by_segment[row["segment"]] += row["lifetime_spend"]
        repeat_by_segment[row["segment"]]["total"] += 1
        repeat_by_segment[row["segment"]]["repeat"] += 1 if row["order_count"] > 1 else 0
    segment_rows = [
        {"segment": segment, "customer_count": count, "revenue": round(revenue_by_segment[segment], 2), "repeat_rate": percent(repeat_by_segment[segment]["repeat"], repeat_by_segment[segment]["total"])}
        for segment, count in counts.most_common()
    ]
    return response("customer-segmentation", summary={"segment_counts": dict(counts), "total_segments": len(counts)}, rows=rows, tables={"segments": segment_rows}, warnings=sales_ctx["warnings"])


def product_sku(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    rows = product_rows_for_orders(sales_ctx)
    costed_rows = [row for row in rows if row["cost_available"]]
    all_costs_available = len(costed_rows) == len(rows)
    summary = {
        "sku_count": len(rows),
        "units_sold": sum(row["units_sold"] for row in rows),
        "revenue": round(sum(row["revenue"] for row in rows), 2),
        "estimated_margin": round(sum(row["estimated_margin"] for row in costed_rows), 2) if all_costs_available else None,
        "cost_data_available": all_costs_available,
        "top_selling_skus": rows[:10],
        "slow_moving_skus": sorted(rows, key=lambda row: row["units_sold"])[:10],
        "dead_stock_skus": [row for row in inventory_sku_base(sales_ctx) if row["units_sold"] == 0][:25],
        "fast_moving_skus": rows[:10],
        "high_revenue_skus": sorted(rows, key=lambda row: row["revenue"], reverse=True)[:10],
        "high_margin_skus": sorted(costed_rows, key=lambda row: row["estimated_margin"], reverse=True)[:10],
        "high_volume_low_margin_skus": [row for row in costed_rows if row["units_sold"] >= 5 and row["margin_percent"] < 20],
    }
    warnings = [entry for entry in sales_ctx["warnings"] if entry["code"] != "missing_unit_cost"]
    if not all_costs_available:
        warnings += warning("missing_unit_cost", "warning", "Some SKU margin estimates are unavailable because unit cost is missing.")
    if any((order_refund_total(order) or Decimal("0")) > 0 for order in sales_ctx["orders"]):
        warnings += warning("sku_refund_allocation_unavailable", "info", "Order-level refunds cannot be assigned to individual SKUs from order summaries alone.")
    return response("product-sku", summary=summary, rows=rows, tables={"skus": rows}, warnings=warnings)


def subscriptions(ctx: dict[str, Any]) -> InsightResponse:
    return response("subscriptions", summary={"data_available": False, "active_subscriptions": None, "subscription_revenue": None, "monthly_recurring_revenue": None, "failed_renewals": None, "upcoming_renewals_7_days": None, "upcoming_renewals_30_days": None}, rows=[], warnings=warning("missing_subscription_data", "info", "No WooCommerce Subscriptions snapshots are synced locally yet."), empty_state="No subscription data synced yet")


def subscription_products(ctx: dict[str, Any]) -> InsightResponse:
    return response("subscription-products", summary={"data_available": False, "products_on_subscription_count": None, "stockout_risk_for_subscription_products": None}, rows=[], warnings=warning("missing_subscription_data", "info", "No subscription product demand data is available locally yet."), empty_state="No subscription data synced yet")


def inventory_forecasting(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    rows = forecast_rows(sales_ctx)
    available_rows = [row for row in rows if row["forecast_available"]]
    forecast_status = "available" if rows and len(available_rows) == len(rows) else ("partial" if available_rows else ("insufficient_history" if rows else "unavailable"))
    summary = {
        "sku_count": len(rows),
        "forecast_available_count": len(available_rows),
        "insufficient_history_count": len(rows) - len(available_rows),
        "forecast_status": forecast_status,
        "stockout_risk": sum(1 for row in rows if row["risk_level"] == "high"),
        "overstock_risk": sum(1 for row in rows if row["risk_level"] == "overstock"),
        "forecasted_30_day_demand": round(sum(row["forecasted_30_day_demand"] for row in available_rows), 2) if available_rows else None,
        "forecasted_60_day_demand": round(sum(row["forecasted_60_day_demand"] for row in available_rows), 2) if available_rows else None,
        "forecasted_90_day_demand": round(sum(row["forecasted_90_day_demand"] for row in available_rows), 2) if available_rows else None,
    }
    warnings = list(sales_ctx["warnings"])
    if len(available_rows) < len(rows):
        warnings += warning("insufficient_sales_history", "info", "Forecasts are unavailable for SKUs without usable sales in the last 30 days.")
    return response("inventory-forecasting", summary=summary, rows=rows, tables={"forecast": rows}, warnings=warnings)


def coupons(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    rows = coupon_rows(sales_ctx["orders"], sales_ctx)
    discount = sum(row["discount_amount"] for row in rows)
    summary = {
        "coupon_orders": sum(row["order_count"] for row in rows),
        "coupon_usage_count": sum(row["usage_count"] for row in rows),
        "coupon_discount_total": round(discount, 2),
        "coupon_revenue": round(sum(row["revenue"] for row in rows), 2),
        "discount_rate": percent(discount, sum(row["revenue"] for row in rows)),
        "top_coupons": rows[:10],
    }
    warnings = [] if rows else warning("missing_coupon_data", "info", "Coupon line snapshots are not synced locally yet.")
    return response("coupons", summary=summary, rows=rows, tables={"coupons": rows}, warnings=sales_ctx["warnings"] + warnings, empty_state=None if rows else "Not enough coupon data yet")


def payment_health(ctx: dict[str, Any]) -> InsightResponse:
    rows = payment_rows(ctx["orders"], ctx)
    failed = sum(row["failed_count"] for row in rows)
    attempts = sum(row["attempt_count"] for row in rows)
    summary = {
        "orders_by_payment_method": {row["payment_method"]: row["attempt_count"] for row in rows},
        "revenue_by_payment_method": {row["payment_method"]: row["revenue"] for row in rows},
        "failed_orders_by_payment_method": {row["payment_method"]: row["failed_count"] for row in rows},
        "failed_order_rate": percent(failed, attempts),
        "successful_payment_rate": percent(attempts - failed, attempts),
        "duplicate_failed_to_success_patterns": sum(row["duplicate_pattern_count"] for row in rows),
    }
    return response("payment-health", summary=summary, rows=rows, tables={"payment_methods": rows, "duplicate_patterns": duplicate_patterns(ctx["orders"])}, warnings=ctx["warnings"])


def geography(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    grouped = defaultdict(lambda: {"orders": [], "customers": set(), "revenue": Decimal("0")})
    for order in sales_ctx["orders"]:
        city = clean(order.shipping_city or order.billing_city or "Unknown")
        postal = clean(order.shipping_zip or order.billing_zip or "Unknown")
        key = (city, postal)
        grouped[key]["orders"].append(order)
        grouped[key]["customers"].add(customer_key(order))
        grouped[key]["revenue"] += order_net_sales(order, sales_ctx)
    rows = []
    for (city, postal), data in grouped.items():
        customers = customer_groups(data["orders"])
        repeat = sum(1 for customer in customers.values() if len(customer["orders"]) > 1)
        rows.append(
            {
                "city": city,
                "postal_code": postal,
                "order_count": len(data["orders"]),
                "customer_count": len(data["customers"]),
                "revenue": dec(data["revenue"]),
                "average_order_value": dec(data["revenue"] / Decimal(len(data["orders"]))) if data["orders"] else 0,
                "repeat_customer_rate": percent(repeat, len(customers)),
                "last_order_date": iso(max((order_date(order) for order in data["orders"] if order_date(order)), default=None)),
            }
        )
    rows.sort(key=lambda row: row["revenue"], reverse=True)
    warnings = sales_ctx["warnings"]
    if any(row["postal_code"] == "Unknown" for row in rows):
        warnings += warning("missing_shipping_postal_code", "info", "Some orders are missing shipping postal codes.")
    return response("geography", summary={"area_count": len(rows), "top_areas": rows[:5]}, rows=rows, tables={"areas": rows}, warnings=warnings)


def product_affinity(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    base_counts = Counter()
    pair_counts = Counter()
    pair_revenue = defaultdict(Decimal)
    descriptions = {}
    for order in sales_ctx["orders"]:
        lines = scoped_order_lines(order, sales_ctx)
        line_skus = sorted({clean_key(line.sku) for line in lines if clean_key(line.sku)})
        if len(line_skus) < 2:
            continue
        for line in lines:
            if clean_key(line.sku):
                descriptions[clean_key(line.sku)] = line.description or line.name
        for sku in line_skus:
            base_counts[sku] += 1
        for base, paired in combinations(line_skus, 2):
            pair_counts[(base, paired)] += 1
            pair_revenue[(base, paired)] += order_net_sales(order, sales_ctx)
    rows = []
    for (base, paired), count in pair_counts.most_common(100):
        rows.append(
            {
                "base_sku": base,
                "base_description": descriptions.get(base),
                "paired_sku": paired,
                "paired_description": descriptions.get(paired),
                "pair_order_count": count,
                "attach_rate": percent(count, base_counts[base]),
                "average_order_value_with_pair": dec(pair_revenue[(base, paired)] / Decimal(count)) if count else 0,
                "suggested_cross_sell_text": f"Customers buying {base} also bought {paired}.",
            }
        )
    return response("product-affinity", summary={"pair_count": len(rows), "frequently_bought_together_skus": rows[:10]}, rows=rows, warnings=sales_ctx["warnings"], empty_state=None if rows else "Not enough multi-line order data yet")


def reorder_forecast(ctx: dict[str, Any]) -> InsightResponse:
    sales_ctx = successful_context(ctx)
    rows = reorder_rows(sales_ctx)
    return response("reorder-forecast", summary={"candidate_count": len(rows), "due_soon": sum(1 for row in rows if row["churn_risk_score"] == "low"), "overdue": sum(1 for row in rows if row["churn_risk_score"] in {"medium", "high"}), "lost": sum(1 for row in rows if row["churn_risk_score"] == "lost")}, rows=rows, warnings=sales_ctx["warnings"], empty_state=None if rows else "Not enough repeat purchase history yet")


def response(dashboard: str, summary=None, metrics=None, trends=None, rows=None, tables=None, warnings=None, empty_state=None) -> InsightResponse:
    return InsightResponse(generated_at=datetime.now(timezone.utc), dashboard=dashboard, summary=summary or {}, metrics=metrics or {}, trends=trends or {}, rows=rows or [], tables=tables or {}, data_quality=warnings or [], empty_state=empty_state)


def successful_context(ctx: dict[str, Any]) -> dict[str, Any]:
    orders = ctx["successful_orders"]
    return {
        **ctx,
        "orders": orders,
        "all_orders": ctx["all_successful_orders"],
        "warnings": base_warnings(orders, ctx["items"]),
    }


def is_success_order(order: Order) -> bool:
    statuses = {clean(order.status).lower(), clean(order.woo_status).lower(), clean(order.local_status).lower()}
    if statuses & FAILED_STATUSES:
        return False
    return bool(statuses & SUCCESS_STATUSES)


def revenue_metrics(orders: list[Order], ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    gross = sum((order_gross(order, ctx) for order in orders), Decimal("0"))
    net = sum((order_net_sales(order, ctx) for order in orders), Decimal("0"))
    units = sum((line_qty(line) for order in orders for line in scoped_order_lines(order, ctx)), Decimal("0"))
    discounts = sum((order_discount(order, ctx) for order in orders), Decimal("0"))
    refund_totals = [order_refund_total(order) for order in orders]
    refunds = (
        sum((value for value in refund_totals if value is not None), Decimal("0"))
        if orders and not has_product_filters(ctx) and all(value is not None for value in refund_totals)
        else None
    )
    return {
        "total_orders": len(orders),
        "gross_sales": dec(gross),
        "net_sales": dec(net),
        "average_order_value": dec(net / Decimal(len(orders))) if orders else None,
        "units_sold": dec(units),
        "refund_amount": dec(refunds) if refunds is not None else None,
        "refund_rate": percent(refunds, gross) if refunds is not None else None,
        "discount_amount": dec(discounts),
    }


def product_rows_for_orders(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = defaultdict(lambda: {"units": Decimal("0"), "revenue": Decimal("0"), "cost": Decimal("0"), "cost_available": True, "orders": set(), "customers": set(), "first": None, "last": None, "product_title": None, "brand": None, "category": None, "barcode": None})
    for order in ctx["orders"]:
        od = order_date(order)
        customer = customer_key(order)
        for line in scoped_order_lines(order, ctx):
            sku = clean_key(line.sku) or f"line-{line.id}"
            item = line.inventory_item or ctx["item_by_sku"].get(sku)
            qty = line_qty(line)
            revenue = line_revenue(line)
            unit_cost = line.unit_cost if line.unit_cost is not None else item.unit_cost if item else None
            grouped[sku]["units"] += qty
            grouped[sku]["revenue"] += revenue
            if unit_cost is None:
                grouped[sku]["cost_available"] = False
            else:
                grouped[sku]["cost"] += money(unit_cost) * qty
            grouped[sku]["orders"].add(order.id)
            grouped[sku]["customers"].add(customer)
            grouped[sku]["first"] = min_date(grouped[sku]["first"], od)
            grouped[sku]["last"] = max_date(grouped[sku]["last"], od)
            grouped[sku]["product_title"] = line.name or (item.woo_name if item else None) or (item.description if item else None) or line.description
            grouped[sku]["brand"] = line.brand or (item.brand if item else None)
            grouped[sku]["category"] = item.category if item else None
            grouped[sku]["barcode"] = line.barcode or (item.barcode if item else None)
    rows = []
    for sku, data in grouped.items():
        item = ctx["item_by_sku"].get(sku)
        margin = data["revenue"] - data["cost"] if data["cost_available"] else None
        rows.append(
            {
                "sku": sku,
                "barcode": data["barcode"],
                "product_title": data["product_title"],
                "description": data["product_title"],
                "brand": data["brand"],
                "category": data["category"],
                "units_sold": dec(data["units"]),
                "order_count": len(data["orders"]),
                "customer_count": len(data["customers"]),
                "revenue": dec(data["revenue"]),
                "cost_available": data["cost_available"],
                "estimated_cost": dec(data["cost"]) if data["cost_available"] else None,
                "estimated_margin": dec(margin) if margin is not None else None,
                "margin_percent": percent(margin, data["revenue"]) if margin is not None else None,
                "current_in_stock": dec(item.in_stock) if item else None,
                "current_allocated": dec(item.allocated) if item else None,
                "current_sellable": dec(item.sellable) if item else None,
                "days_of_stock_left": None,
                "last_sold_at": iso(data["last"]),
                "first_sold_at": iso(data["first"]),
            }
        )
    rows.sort(key=lambda row: row["units_sold"], reverse=True)
    return rows


def inventory_sku_base(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    sold = {row["sku"]: row for row in product_rows_for_orders(ctx)}
    rows = []
    for item in ctx["items"]:
        if not forecast_item_matches(item, ctx.get("params") or {}):
            continue
        sku = clean_key(item.sku)
        if not sku:
            continue
        product_title = item.woo_name or item.description
        rows.append({**sold.get(sku, {}), "sku": sku, "product_title": product_title, "description": product_title, "brand": item.brand, "category": item.category, "units_sold": sold.get(sku, {}).get("units_sold", 0), "current_sellable": dec(item.sellable)})
    return rows


def forecast_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    sales = defaultdict(lambda: {"7": Decimal("0"), "30": Decimal("0"), "60": Decimal("0"), "90": Decimal("0")})
    scoped_items = [item for item in ctx["items"] if forecast_item_matches(item, ctx.get("params") or {})]
    scoped_skus = {clean_key(item.sku) for item in scoped_items if clean_key(item.sku)}
    for order in ctx["orders"]:
        od = order_date(order)
        if not od:
            continue
        days = (now - make_aware(od)).days
        for line in order.items:
            sku = clean_key(line.sku)
            if not sku or sku not in scoped_skus:
                continue
            qty = line_qty(line)
            if 0 <= days <= 7:
                sales[sku]["7"] += qty
            if 0 <= days <= 30:
                sales[sku]["30"] += qty
            if 0 <= days <= 60:
                sales[sku]["60"] += qty
            if 0 <= days <= 90:
                sales[sku]["90"] += qty
    rows = []
    for item in scoped_items:
        sku = clean_key(item.sku)
        product_title = item.woo_name or item.description
        units30 = sales[sku]["30"]
        forecast_available = units30 > 0
        daily_velocity = units30 / Decimal("30") if forecast_available else None
        sellable = money(item.sellable)
        lead_time = item.default_lead_time_days or 7
        days_left = sellable / daily_velocity if daily_velocity else None
        par = money(item.par_level)
        suggested = max(Decimal("0"), (daily_velocity * Decimal(str(lead_time))) + par - sellable) if daily_velocity is not None else None
        risk = "insufficient_history"
        if forecast_available:
            risk = "low"
            if item.under_par or (days_left is not None and days_left < lead_time):
                risk = "high"
            elif days_left is not None and days_left < lead_time * 2:
                risk = "medium"
            elif days_left is not None and days_left > 180:
                risk = "overstock"
        rows.append(
            {
                "sku": item.sku,
                "product_title": product_title,
                "description": product_title,
                "brand": item.brand,
                "category": item.category,
                "current_sellable": dec(sellable),
                "units_sold_7d": dec(sales[sku]["7"]),
                "units_sold_30d": dec(sales[sku]["30"]),
                "units_sold_60d": dec(sales[sku]["60"]),
                "units_sold_90d": dec(sales[sku]["90"]),
                "forecast_available": forecast_available,
                "forecast_status": "available" if forecast_available else "insufficient_history",
                "daily_velocity": dec(daily_velocity) if daily_velocity is not None else None,
                "days_of_stock_left": dec(days_left) if days_left is not None else None,
                "lead_time_days": lead_time,
                "par_level": dec(par),
                "suggested_reorder_qty": dec(suggested) if suggested is not None else None,
                "risk_level": risk,
                "forecasted_30_day_demand": dec(daily_velocity * Decimal("30")) if daily_velocity is not None else None,
                "forecasted_60_day_demand": dec(daily_velocity * Decimal("60")) if daily_velocity is not None else None,
                "forecasted_90_day_demand": dec(daily_velocity * Decimal("90")) if daily_velocity is not None else None,
                "under_par_risk": bool(item.under_par),
            }
        )
    rows.sort(key=lambda row: {"high": 0, "medium": 1, "low": 2, "overstock": 3, "insufficient_history": 4}.get(row["risk_level"], 9))
    return rows


def forecast_item_matches(item: InventoryItem, params: dict[str, Any]) -> bool:
    sku = clean_key(params.get("sku"))
    if sku and clean_key(item.sku) != sku:
        return False
    brand = clean(params.get("brand")).lower()
    if brand and clean(item.brand).lower() != brand:
        return False
    category = clean(params.get("category")).lower()
    return not category or clean(item.category).lower() == category


def customer_groups(orders: list[Order]) -> dict[str, dict[str, Any]]:
    grouped = defaultdict(lambda: {"orders": [], "email": None, "name": None, "phone": None})
    for order in orders:
        key = customer_key(order)
        grouped[key]["orders"].append(order)
        grouped[key]["email"] = normalized_email(order.customer_email) or grouped[key]["email"]
        grouped[key]["name"] = order.customer_name or full_name(order) or grouped[key]["name"]
        grouped[key]["phone"] = order.customer_phone or order.shipping_phone or order.billing_phone or grouped[key]["phone"]
    return grouped


def identified_customer_groups(ctx: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str], set[str]]:
    groups = {key: value for key, value in customer_groups(ctx["orders"]).items() if value["email"]}
    first_orders = first_order_dates_by_email(ctx["all_orders"])
    new_customers = {
        email
        for email in groups
        if email in first_orders
        and (ctx["start"] is None or first_orders[email] >= ctx["start"])
        and (ctx["end"] is None or first_orders[email] <= ctx["end"])
    }
    return groups, new_customers, set(groups) - new_customers


def first_order_dates_by_email(orders: list[Order]) -> dict[str, datetime]:
    first_orders = {}
    for order in orders:
        email = normalized_email(order.customer_email)
        placed_at = make_aware(order_date(order)) if order_date(order) else None
        if email and placed_at and (email not in first_orders or placed_at < first_orders[email]):
            first_orders[email] = placed_at
    return first_orders


def customer_rows(customers: dict[str, dict[str, Any]], ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows = []
    now = datetime.now(timezone.utc)
    for key, data in customers.items():
        dates = sorted([make_aware(order_date(order)) for order in data["orders"] if order_date(order)])
        intervals = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
        spend = sum((order_net_sales(order, ctx) for order in data["orders"]), Decimal("0"))
        rows.append(
            {
                "customer_key": key,
                "customer_name": data["name"],
                "email": data["email"],
                "phone": data["phone"],
                "order_count": len(data["orders"]),
                "lifetime_spend": dec(spend),
                "average_order_value": dec(spend / Decimal(len(data["orders"]))) if data["orders"] else 0,
                "first_order_date": iso(dates[0] if dates else None),
                "last_order_date": iso(dates[-1] if dates else None),
                "average_days_between_orders": round(sum(intervals) / len(intervals), 2) if intervals else None,
                "recency_days": (now - dates[-1]).days if dates else None,
            }
        )
    rows.sort(key=lambda row: row["lifetime_spend"], reverse=True)
    return rows


def reorder_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for order in ctx["orders"]:
        for line in scoped_order_lines(order, ctx):
            sku = clean_key(line.sku)
            if sku:
                grouped[(customer_key(order), sku)].append(order)
    candidates = {}
    now = datetime.now(timezone.utc)
    for (customer, sku), orders in grouped.items():
        dates = sorted([make_aware(order_date(order)) for order in orders if order_date(order)])
        if len(dates) < 2:
            continue
        intervals = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
        average_interval = max(1, round(sum(intervals) / len(intervals), 2))
        expected = dates[-1] + timedelta(days=average_interval)
        days_overdue = (now - expected).days
        risk = "low"
        if days_overdue > average_interval * 2:
            risk = "lost"
        elif days_overdue > 14:
            risk = "high"
        elif days_overdue > 0:
            risk = "medium"
        order = orders[-1]
        current = candidates.get(customer)
        if not current or days_overdue > current["days_overdue"]:
            candidates[customer] = {
                "customer_email": normalized_email(order.customer_email),
                "customer_name": order.customer_name or full_name(order),
                "phone": order.customer_phone or order.shipping_phone or order.billing_phone,
                "last_order_date": iso(dates[-1]),
                "most_repeated_sku": sku,
                "most_repeated_brand": first_line_value(order, sku, "brand"),
                "most_repeated_category": None,
                "average_reorder_interval_days": average_interval,
                "expected_next_order_date": iso(expected),
                "days_overdue": days_overdue,
                "churn_risk_score": risk,
                "expected_order_value": dec(order_net_sales(order, ctx)),
                "recommended_action": recommended_reorder_action(risk),
            }
    rows = list(candidates.values())
    rows.sort(key=lambda row: row["days_overdue"], reverse=True)
    return rows


def daily_trends(orders: list[Order], ctx: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(lambda: {"orders": 0, "gross": Decimal("0"), "net": Decimal("0"), "units": Decimal("0")})
    granularity = (ctx or {}).get("params", {}).get("granularity", "day")
    for order in orders:
        period = (order_date(order) or datetime.now(timezone.utc)).date()
        if granularity == "week":
            period -= timedelta(days=period.weekday())
        key = period.isoformat()
        grouped[key]["orders"] += 1
        grouped[key]["gross"] += order_gross(order, ctx)
        grouped[key]["net"] += order_net_sales(order, ctx)
        grouped[key]["units"] += sum((line_qty(line) for line in scoped_order_lines(order, ctx)), Decimal("0"))
    daily = [{"date": key, "order_count": value["orders"], "gross_sales": dec(value["gross"]), "net_sales": dec(value["net"]), "units_sold": dec(value["units"])} for key, value in sorted(grouped.items())]
    return {"daily_revenue": daily, "revenue_by_day": daily, "orders_by_day": [{"date": row["date"], "order_count": row["order_count"]} for row in daily]}


def status_breakdown(orders: list[Order], ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    grouped = defaultdict(lambda: {"orders": 0, "revenue": Decimal("0")})
    for order in orders:
        status = order.status or order.local_status or order.woo_status or "unknown"
        grouped[status]["orders"] += 1
        grouped[status]["revenue"] += order_net_sales(order, ctx)
    return [{"status": key, "order_count": value["orders"], "revenue": dec(value["revenue"])} for key, value in sorted(grouped.items())]


def payment_breakdown(orders: list[Order], ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return payment_rows(orders, ctx)


def payment_rows(orders: list[Order], ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    grouped = defaultdict(lambda: {"attempts": 0, "success": 0, "failed": 0, "revenue": Decimal("0")})
    duplicates = Counter(row["payment_method"] for row in duplicate_patterns(orders))
    for order in orders:
        method = order.payment_method_title or order.payment_method or "Unknown"
        status = (order.status or order.woo_status or order.local_status or "").lower()
        grouped[method]["attempts"] += 1
        if status in FAILED_STATUSES:
            grouped[method]["failed"] += 1
        else:
            grouped[method]["success"] += 1
            grouped[method]["revenue"] += order_net_sales(order, ctx)
    rows = []
    for method, value in grouped.items():
        rows.append({"payment_method": method, "attempt_count": value["attempts"], "success_count": value["success"], "failed_count": value["failed"], "success_rate": percent(value["success"], value["attempts"]), "revenue": dec(value["revenue"]), "duplicate_pattern_count": duplicates[method]})
    rows.sort(key=lambda row: row["attempt_count"], reverse=True)
    return rows


def duplicate_patterns(orders: list[Order]) -> list[dict[str, Any]]:
    rows = []
    sorted_orders = sorted([order for order in orders if customer_key(order)], key=lambda order: order_date(order) or datetime.min.replace(tzinfo=timezone.utc))
    for failed in sorted_orders:
        failed_status = (failed.status or failed.woo_status or "").lower()
        if failed_status not in FAILED_STATUSES:
            continue
        failed_date = order_date(failed)
        for success in sorted_orders:
            if success.id == failed.id or customer_key(success) != customer_key(failed):
                continue
            success_status = (success.status or success.woo_status or "").lower()
            success_date = order_date(success)
            if success_status in FAILED_STATUSES or not failed_date or not success_date:
                continue
            if abs((make_aware(success_date) - make_aware(failed_date)).total_seconds()) <= 3600:
                rows.append({"customer_key": customer_key(failed), "failed_order_id": failed.id, "success_order_id": success.id, "payment_method": failed.payment_method_title or failed.payment_method or "Unknown"})
                break
    return rows


def coupon_rows(orders: list[Order], ctx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    grouped = defaultdict(lambda: {"usage": 0, "orders": set(), "revenue": Decimal("0"), "discount": Decimal("0"), "customers": set()})
    for order in orders:
        payload = order.raw_woo_payload or {}
        coupon_lines = payload.get("coupon_lines") or []
        for coupon in coupon_lines:
            code = str(coupon.get("code") or coupon.get("coupon_code") or "").strip()
            if not code:
                continue
            discount = order_discount(order, ctx) if has_product_filters(ctx) else money(coupon.get("discount") or coupon.get("discount_amount") or order.discount_total)
            grouped[code]["usage"] += 1
            grouped[code]["orders"].add(order.id)
            grouped[code]["customers"].add(customer_key(order))
            grouped[code]["revenue"] += order_net_sales(order, ctx)
            grouped[code]["discount"] += discount
    rows = []
    for code, value in grouped.items():
        rows.append({"coupon_code": code, "usage_count": value["usage"], "order_count": len(value["orders"]), "revenue": dec(value["revenue"]), "discount_amount": dec(value["discount"]), "average_order_value": dec(value["revenue"] / Decimal(len(value["orders"]))) if value["orders"] else 0, "repeat_customer_count": 0, "repeat_after_coupon_rate": None, "estimated_margin_impact": dec(value["discount"] * Decimal("-1"))})
    rows.sort(key=lambda row: row["usage_count"], reverse=True)
    return rows


def new_vs_returning_by_month(orders: list[Order], historical_orders: list[Order]) -> list[dict[str, Any]]:
    first_orders = first_order_dates_by_email(historical_orders)
    rows = defaultdict(lambda: {"new_customers": set(), "returning_customers": set()})
    for order in orders:
        od = order_date(order)
        email = normalized_email(order.customer_email)
        if not od or not email or email not in first_orders:
            continue
        month = od.strftime("%Y-%m")
        if first_orders[email].strftime("%Y-%m") == month:
            rows[month]["new_customers"].add(email)
        else:
            rows[month]["returning_customers"].add(email)
    return [{"month": month, **{key: len(emails) for key, emails in value.items()}} for month, value in sorted(rows.items())]


def top_dimension(product_rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped = defaultdict(lambda: {"units_sold": 0.0, "revenue": 0.0})
    for row in product_rows:
        key = row.get(field) or "Unknown"
        grouped[key]["units_sold"] += row["units_sold"]
        grouped[key]["revenue"] += row["revenue"]
    return [{field: key, **value} for key, value in sorted(grouped.items(), key=lambda item: item[1]["revenue"], reverse=True)[:10]]


def segment_customer(row: dict[str, Any]) -> str:
    recency = row.get("recency_days") or 9999
    orders = row["order_count"]
    spend = row["lifetime_spend"]
    if orders == 1 and recency <= 30:
        return "New Customers"
    if spend >= 500:
        return "Big Spenders"
    if orders >= 5 and recency <= 45:
        return "Champions"
    if orders >= 3 and recency <= 90:
        return "Loyal Customers"
    if orders >= 2 and recency <= 60:
        return "Potential Loyalists"
    if orders == 1:
        return "One-Time Customers"
    if recency <= 120:
        return "At Risk"
    if recency <= 240:
        return "Dormant"
    return "Lost"


def base_warnings(orders: list[Order], items: list[InventoryItem]) -> list[dict[str, str]]:
    warnings = []
    if not orders:
        warnings += warning("limited_order_history", "info", "No local order snapshots matched the current filters.")
    if any(item.unit_cost is None for item in items):
        warnings += warning("missing_unit_cost", "warning", "Some inventory items are missing unit cost, so margin and value metrics may be incomplete.")
    return warnings


def warning(code: str, severity: str, message: str) -> list[dict[str, str]]:
    return [{"code": code, "severity": severity, "message": message}]


def order_matches(order: Order, params: dict[str, Any], item_by_sku: dict[str, InventoryItem]) -> bool:
    status = clean(params.get("order_status"))
    if status and status.lower() not in {clean(order.status).lower(), clean(order.local_status).lower(), clean(order.woo_status).lower()}:
        return False
    payment = clean(params.get("payment_method"))
    if payment and payment.lower() not in clean(order.payment_method_title or order.payment_method).lower():
        return False
    email = normalized_email(params.get("customer_email"))
    if email and email != normalized_email(order.customer_email):
        return False
    city = clean(params.get("city"))
    if city and city.lower() not in clean(order.shipping_city or order.billing_city).lower():
        return False
    postal = clean(params.get("postal_code"))
    if postal and postal.lower() not in clean(order.shipping_zip or order.billing_zip).lower():
        return False
    if any(clean(params.get(key)) for key in ("sku", "brand", "category")) and not any(
        line_matches_product_filters(line, params, item_by_sku) for line in order.items
    ):
        return False
    return True


def line_matches_product_filters(line: OrderItem, params: dict[str, Any], item_by_sku: dict[str, InventoryItem]) -> bool:
    item = line.inventory_item or item_by_sku.get(clean_key(line.sku))
    sku = clean_key(params.get("sku"))
    if sku and clean_key(line.sku or (item.sku if item else None)) != sku:
        return False
    brand = clean(params.get("brand")).lower()
    if brand and clean(line.brand or (item.brand if item else None)).lower() != brand:
        return False
    category = clean(params.get("category")).lower()
    return not category or clean(item.category if item else None).lower() == category


def has_product_filters(ctx: dict[str, Any] | None) -> bool:
    params = ctx.get("params", {}) if ctx else {}
    return any(clean(params.get(key)) for key in ("sku", "brand", "category"))


def scoped_order_lines(order: Order, ctx: dict[str, Any] | None = None) -> list[OrderItem]:
    if not has_product_filters(ctx):
        return list(order.items)
    return [line for line in order.items if line_matches_product_filters(line, ctx["params"], ctx["item_by_sku"])]


def order_in_range(order: Order, start: datetime | None, end: datetime | None) -> bool:
    od = order_date(order)
    if not od:
        return True
    aware = make_aware(od)
    return (start is None or aware >= start) and (end is None or aware <= end)


def order_date(order: Order) -> datetime | None:
    return order.placed_on or order.date_created or order.completed_on or order.created_at


def order_total(order: Order) -> Decimal:
    if order.total is not None:
        return money(order.total)
    return sum((line_revenue(line) for line in order.items), Decimal("0"))


def order_net_sales(order: Order, ctx: dict[str, Any] | None = None) -> Decimal:
    if order.items:
        net = sum((line_revenue(line) for line in scoped_order_lines(order, ctx)), Decimal("0"))
    else:
        net = order_total(order) - money(order.shipping_total) - money(order.tax_total)
    refund = order_refund_total(order)
    if refund is not None and not has_product_filters(ctx):
        net -= refund
    return max(net, Decimal("0"))


def order_refund_total(order: Order) -> Decimal | None:
    payload = order.raw_woo_payload or {}
    if "refunds" not in payload:
        return None
    return sum((abs(money(row.get("total") or row.get("amount"))) for row in payload.get("refunds") or []), Decimal("0"))


def refund_warning(orders: list[Order], ctx: dict[str, Any] | None = None) -> list[dict[str, str]]:
    if has_product_filters(ctx):
        return warning("sku_refund_allocation_unavailable", "info", "Order-level refunds cannot be assigned to filtered products from order summaries alone.")
    if orders and all(order_refund_total(order) is not None for order in orders):
        return []
    return warning("missing_refund_data", "info", "Refund summaries are missing on some local orders, so refund metrics are unavailable.")


def order_gross(order: Order, ctx: dict[str, Any] | None = None) -> Decimal:
    if has_product_filters(ctx):
        return sum((money(line.line_subtotal) if line.line_subtotal is not None else line_revenue(line) for line in scoped_order_lines(order, ctx)), Decimal("0"))
    if order.subtotal is not None:
        return money(order.subtotal)
    return sum((money(line.line_subtotal) if line.line_subtotal is not None else line_revenue(line) for line in order.items), Decimal("0"))


def order_discount(order: Order, ctx: dict[str, Any] | None = None) -> Decimal:
    if not has_product_filters(ctx):
        return money(order.discount_total)
    return max(Decimal("0"), order_gross(order, ctx) - order_net_sales(order, ctx))


def line_revenue(line: OrderItem) -> Decimal:
    if line.total_price is not None:
        return money(line.total_price)
    if line.line_total is not None:
        return money(line.line_total)
    return money(line.unit_price) * line_qty(line)


def line_qty(line: OrderItem) -> Decimal:
    return money(line.quantity_ordered or line.ordered_qty)


def customer_key(order: Order) -> str:
    email = normalized_email(order.customer_email)
    if email:
        return email
    if order.customer_id:
        return f"customer:{order.customer_id}"
    fallback = "|".join([clean(order.customer_phone or order.shipping_phone or order.billing_phone), clean(order.customer_name or full_name(order)), clean(order.shipping_zip or order.billing_zip)])
    return f"guest:{fallback if fallback != '||' else order.id}"


def summary_changes(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, float | None]:
    changes = {}
    for key, value in current.items():
        old = previous.get(key)
        if isinstance(value, Number) and not isinstance(value, bool) and isinstance(old, Number) and not isinstance(old, bool):
            changes[key] = None if old == 0 else round((float(value) - float(old)) * 100 / abs(float(old)), 1)
    return changes


def first_line_value(order: Order, sku: str, field: str) -> str | None:
    for line in order.items:
        if clean_key(line.sku) == sku:
            return getattr(line, field, None)
    return None


def full_name(order: Order) -> str:
    return clean(f"{order.customer_first_name or ''} {order.customer_last_name or ''}")


def dormant_count(rows: list[dict[str, Any]], days: int) -> int:
    return sum(1 for row in rows if (row.get("recency_days") or 0) >= days)


def coupon_total(orders: list[Order], ctx: dict[str, Any] | None = None) -> float:
    return dec(sum((order_discount(order, ctx) for order in orders), Decimal("0")))


def recommended_reorder_action(risk: str) -> str:
    return {
        "low": "send reminder",
        "medium": "send reminder",
        "high": "offer reorder discount",
        "lost": "check subscription opportunity",
    }.get(risk, "send reminder")


def parse_date(value: Any, end_of_day: bool = False) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.max.time() if end_of_day else datetime.min.time())
    else:
        parsed_date = date.fromisoformat(str(value))
        parsed = datetime.combine(parsed_date, datetime.max.time() if end_of_day else datetime.min.time())
    return make_aware(parsed)


def make_aware(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc)
    try:
        local_timezone = ZoneInfo(get_settings().admin_timezone)
    except ZoneInfoNotFoundError:
        local_timezone = timezone.utc
    return value.replace(tzinfo=local_timezone).astimezone(timezone.utc)


def money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def dec(value: Any) -> float:
    if value is None:
        return 0
    return round(float(value), 2)


def percent(numerator: Any, denominator: Any) -> float:
    denominator_decimal = money(denominator)
    if denominator_decimal == 0:
        return 0
    return round(float(money(numerator) / denominator_decimal * Decimal("100")), 2)


def safe_div(numerator: Any, denominator: Any) -> float:
    denominator_decimal = money(denominator)
    if denominator_decimal == 0:
        return 0
    return dec(money(numerator) / denominator_decimal)


def normalized_email(value: str | None) -> str:
    return clean(value).lower()


def clean_key(value: Any) -> str:
    return clean(value).upper()


def clean(value: Any) -> str:
    return str(value or "").strip()


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def min_date(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if not candidate:
        return current
    return candidate if current is None or candidate < current else current


def max_date(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if not candidate:
        return current
    return candidate if current is None or candidate > current else current
