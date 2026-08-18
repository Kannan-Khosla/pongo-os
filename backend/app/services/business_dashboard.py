from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Text, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, load_only, selectinload

from app.core.config import get_settings
from app.models.orders import Order, OrderItem
from app.services.metric_cache import cached_metric_payload
from app.services.woocommerce_subscriptions import build_subscription_data, overlay_subscription_freshness


OPEN_STATUSES = {"open", "processing", "on-hold", "pending", "allocated", "partially_allocated", "picked", "partially_picked"}
DONE_STATUSES = {"completed", "fulfilled", "partially_fulfilled"}
FAILED_STATUSES = {"failed", "cancelled", "canceled", "refunded"}
SALES_STATUSES = {"completed", "processing", "fulfilled", "partially_fulfilled", "open", "allocated", "picked"}
CITY_COORDINATES = {
    "edmonton": (53.5461, -113.4938),
    "sherwood park": (53.5412, -113.2957),
    "leduc": (53.2594, -113.5493),
    "st. albert": (53.6305, -113.6256),
    "beaumont": (53.3528, -113.4152),
    "spruce grove": (53.5414, -113.9007),
    "fort saskatchewan": (53.7126, -113.2140),
}
BUSINESS_ORDER_COLUMNS = (
    Order.id,
    Order.woo_order_id,
    Order.woo_order_number,
    Order.order_number,
    Order.woo_status,
    Order.local_status,
    Order.status,
    Order.customer_id,
    Order.customer_first_name,
    Order.customer_last_name,
    Order.customer_name,
    Order.customer_email,
    Order.customer_phone,
    Order.shipping_phone,
    Order.billing_phone,
    Order.payment_method,
    Order.payment_method_title,
    Order.total,
    Order.date_created,
    Order.placed_on,
    Order.completed_on,
    Order.created_at,
    Order.shipping_address_1,
    Order.shipping_city,
    Order.shipping_state,
    Order.shipping_zip,
    Order.billing_city,
    Order.billing_zip,
    Order.is_historical_snapshot,
    Order.historical_source_present,
)
BUSINESS_LINE_COLUMNS = (
    OrderItem.id,
    OrderItem.order_id,
    OrderItem.quantity_ordered,
    OrderItem.ordered_qty,
    OrderItem.unit_price,
    OrderItem.line_total,
    OrderItem.total_price,
)
BUSINESS_OPEN_ORDER_ROW_LIMIT = 200


def build_business_dashboard(db: Session, target_date: date | None = None) -> dict[str, Any]:
    target_date = target_date or admin_today()
    today = build_today(db, target_date)
    open_orders = build_open_orders(db)
    subscriptions = build_subscriptions(db, target_date)
    revenue_comparison = build_revenue_comparison(db, target_date)
    order_map = build_order_map(db, target_date)
    warnings = merge_warnings(
        today["data_quality"],
        open_orders["data_quality"],
        subscriptions["data_quality"],
        revenue_comparison["data_quality"],
        order_map["data_quality"],
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "today": today,
        "open_orders": open_orders,
        "subscriptions": subscriptions,
        "revenue_comparison": revenue_comparison,
        "order_map": order_map,
        "data_quality": warnings,
    }


def get_cached_business_metric(
    db: Session,
    section: str,
    target_date: date | None = None,
    *,
    mode: str | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    effective_date = target_date or admin_today()
    combined_sections = {
        "today": "today",
        "open-orders": "open_orders",
        "subscriptions": "subscriptions",
        "revenue-comparison": "revenue_comparison",
        "order-map": "order_map",
    }
    if section in combined_sections and (section != "revenue-comparison" or mode in {None, "month_to_date"}):
        dashboard = get_cached_business_metric(db, "dashboard", effective_date, force_refresh=force_refresh)
        return dashboard[combined_sections[section]]
    params = {
        "date": None if section == "open-orders" else effective_date.isoformat(),
        "mode": mode,
    }
    builders = {
        "dashboard": lambda: build_business_dashboard(db, effective_date),
        "today": lambda: build_today(db, effective_date),
        "open-orders": lambda: build_open_orders(db),
        "subscriptions": lambda: build_subscriptions(db, effective_date),
        "revenue-comparison": lambda: build_revenue_comparison(db, effective_date, mode or "month_to_date"),
        "order-map": lambda: build_order_map(db, effective_date),
    }
    payload = cached_metric_payload(
        db,
        f"business-dashboard:{section}",
        params,
        builders[section],
        force_refresh=force_refresh,
    )
    if section != "dashboard":
        return payload
    subscriptions = overlay_subscription_freshness(db, payload["subscriptions"])
    return {
        **payload,
        "subscriptions": subscriptions,
        "data_quality": merge_warnings(
            payload["today"]["data_quality"],
            payload["open_orders"]["data_quality"],
            subscriptions["data_quality"],
            payload["revenue_comparison"]["data_quality"],
            payload["order_map"]["data_quality"],
        ),
    }


def build_today(db: Session, target_date: date | None = None, *, orders: list[Order] | None = None) -> dict[str, Any]:
    target_date = target_date or admin_today()
    if orders is None:
        return build_today_from_sql(db, target_date)
    today_orders = [order for order in orders if order_is_on_date(order, target_date)]
    today_sales_orders = [order for order in today_orders if is_sales_order(order)]
    customers_today = {email for order in today_sales_orders if (email := normalized_email(order.customer_email))}
    earlier_customers = {
        email
        for order in orders
        if is_sales_order(order)
        and order_day(order)
        and order_day(order) < target_date
        and (email := normalized_email(order.customer_email))
    }
    revenue = sum((order_total(order) for order in today_sales_orders), Decimal("0"))
    subscription_count = sum(1 for order in today_sales_orders if is_subscription_order(order))
    warnings = data_quality_warnings(orders=today_sales_orders, include_limited_history=not orders)
    if not any_subscription_data(orders):
        warnings += warning("missing_subscription_data", "info", "Subscription data is not synced yet.")
    summary = {
        "today_date": target_date.isoformat(),
        "today_orders_count": len(today_sales_orders),
        "today_revenue": dec(revenue),
        "today_new_customers": sum(1 for customer in customers_today if customer not in earlier_customers),
        "today_returning_customers": sum(1 for customer in customers_today if customer in earlier_customers),
        "today_subscription_orders": subscription_count,
        "today_units_sold": dec(sum((line_qty(line) for order in today_sales_orders for line in order.items), Decimal("0"))),
        "open_orders_count": len(open_order_rows(orders)),
        "completed_orders_today": sum(1 for order in today_sales_orders if normalized_status(order) in DONE_STATUSES),
        "failed_orders_today": sum(1 for order in today_orders if normalized_status(order) == "failed"),
        "cancelled_orders_today": sum(1 for order in today_orders if normalized_status(order) in {"cancelled", "canceled"}),
        "average_order_value_today": dec(revenue / Decimal(len(today_sales_orders))) if today_sales_orders else 0,
    }
    return {"summary": summary, "data_quality": warnings}


def build_open_orders(db: Session, *, orders: list[Order] | None = None) -> dict[str, Any]:
    if orders is None:
        return build_open_orders_from_sql(db)
    rows = open_order_rows(orders)
    warnings = data_quality_warnings(orders=rows, include_limited_history=False)
    return {"summary": {"open_orders_count": len(rows)}, "rows": [order_row(order) for order in rows], "data_quality": warnings}


def build_subscriptions(db: Session, target_date: date | None = None) -> dict[str, Any]:
    data = build_subscription_data(db, target_date)
    rows = [row for row in data["subscription_rows"] if row["due_within_30_days"]]
    return {
        "summary": data["summary"],
        "rows": rows,
        "products": data["product_rows"],
        "data_quality": data["warnings"],
        "empty_state": (
            "Subscription data is not synced yet."
            if not data["available"]
            else None if rows else "No active subscription renewals are due in the next 30 days."
        ),
    }


def build_revenue_comparison(
    db: Session,
    target_date: date | None = None,
    mode: str = "month_to_date",
    *,
    orders: list[Order] | None = None,
) -> dict[str, Any]:
    target_date = target_date or admin_today()
    if orders is None:
        return build_revenue_comparison_from_sql(db, target_date, mode)
    if mode == "last_7_days":
        current_start = target_date - timedelta(days=6)
    elif mode == "today":
        current_start = target_date
    else:
        current_start = target_date.replace(day=1)
    previous_start = previous_month_date(current_start)
    previous_end = previous_start + (target_date - current_start)
    current_days = days_between(current_start, target_date)
    previous_days = days_between(previous_start, previous_end)
    daily_series = []
    for index, current_day in enumerate(current_days):
        previous_day = previous_days[index]
        daily_series.append(
            {
                "day_index": index + 1,
                "current_date": current_day.isoformat(),
                "current_revenue": dec(revenue_for_day(orders, current_day)),
                "previous_date": previous_day.isoformat(),
                "previous_revenue": dec(revenue_for_day(orders, previous_day)),
            }
        )
    current_revenue = sum((money(row["current_revenue"]) for row in daily_series), Decimal("0"))
    previous_revenue = sum((money(row["previous_revenue"]) for row in daily_series), Decimal("0"))
    delta = current_revenue - previous_revenue
    return {
        "summary": {
            "current_period_label": period_label(current_start, target_date),
            "previous_period_label": period_label(previous_start, previous_end),
            "current_period_revenue": dec(current_revenue),
            "previous_period_revenue": dec(previous_revenue),
            "delta_amount": dec(delta),
            "delta_percent": percent(delta, previous_revenue),
        },
        "daily_series": daily_series,
        "data_quality": data_quality_warnings(orders=orders, include_limited_history=not orders),
    }


def build_order_map(db: Session, target_date: date | None = None, *, orders: list[Order] | None = None) -> dict[str, Any]:
    target_date = target_date or admin_today()
    source_orders = orders if orders is not None else load_orders_for_day(db, target_date, include_payload=True, include_lines=True)
    orders = [order for order in source_orders if order_is_on_date(order, target_date) and is_sales_order(order)]
    city_groups = defaultdict(lambda: {"orders": [], "customers": set(), "revenue": Decimal("0")})
    markers = []
    unplotted = 0
    for order in orders:
        city = clean(order.shipping_city or order.billing_city or "Unknown")
        city_key = city.lower()
        city_groups[city]["orders"].append(order)
        if email := normalized_email(order.customer_email):
            city_groups[city]["customers"].add(email)
        city_groups[city]["revenue"] += order_total(order)
        latitude, longitude, approximate = coordinates_for_order(order)
        if latitude is None or longitude is None:
            unplotted += 1
            continue
        markers.append(
            {
                "order_number": order.woo_order_number or order.order_number,
                "customer_name": order.customer_name or full_name(order),
                "city": city,
                "postal_code": order.shipping_zip or order.billing_zip,
                "shipping_address_summary": shipping_summary(order),
                "latitude": latitude,
                "longitude": longitude,
                "marker_label": order.woo_order_number or order.order_number or str(order.id),
                "approximate": approximate,
            }
        )
    city_breakdown = [
        {"city": city, "order_count": len(data["orders"]), "revenue": dec(data["revenue"]), "customer_count": len(data["customers"])}
        for city, data in city_groups.items()
    ]
    city_breakdown.sort(key=lambda row: row["order_count"], reverse=True)
    warnings = []
    if any(marker["approximate"] for marker in markers):
        warnings += warning("approximate_coordinates", "info", "Map uses city-level approximate markers until address geocoding is configured.")
    if unplotted:
        warnings += warning("unplotted_orders", "info", "Some orders could not be plotted because city or coordinate data is unavailable.")
    return {
        "summary": {"total_orders_plotted": len(markers), "total_orders_unplotted": unplotted, "total_orders_today": len(orders)},
        "city_breakdown": city_breakdown,
        "markers": markers,
        "data_quality": warnings,
    }


def build_today_from_sql(db: Session, target_date: date) -> dict[str, Any]:
    start, end = admin_day_bounds(target_date)
    order_timestamp = order_date_expression()
    eligible = eligible_order_condition()
    on_target_date = and_(order_timestamp >= start, order_timestamp < end)
    sales_order = sales_order_condition()
    normalized = normalized_status_expression()
    order_value = order_total_expression()
    subscription_order = subscription_order_condition()

    values = db.execute(
        select(
            func.count(Order.id).label("eligible_order_count"),
            _count_when(and_(on_target_date, sales_order)).label("today_orders_count"),
            func.coalesce(func.sum(case((and_(on_target_date, sales_order), order_value), else_=0)), 0).label("today_revenue"),
            _count_when(and_(on_target_date, sales_order, subscription_order)).label("today_subscription_orders"),
            _count_when(normalized.in_(OPEN_STATUSES)).label("open_orders_count"),
            _count_when(and_(on_target_date, sales_order, normalized.in_(DONE_STATUSES))).label("completed_orders_today"),
            _count_when(and_(on_target_date, normalized == "failed")).label("failed_orders_today"),
            _count_when(and_(on_target_date, normalized.in_({"cancelled", "canceled"}))).label("cancelled_orders_today"),
            _count_when(and_(on_target_date, sales_order, Order.total.is_(None))).label("missing_today_sales_total_count"),
            _count_when(subscription_order).label("subscription_source_count"),
        ).where(eligible)
    ).mappings().one()

    line_quantity = line_quantity_expression()
    units_sold = db.scalar(
        select(func.coalesce(func.sum(line_quantity), 0))
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(eligible, on_target_date, sales_order)
    ) or Decimal("0")

    email = normalized_email_expression()
    customer_history = (
        select(
            email.label("email"),
            func.min(order_timestamp).label("first_order_at"),
            _count_when(on_target_date).label("orders_today"),
        )
        .where(eligible, sales_order, email != "")
        .group_by(email)
        .subquery()
    )
    customer_values = db.execute(
        select(
            _count_when(and_(customer_history.c.orders_today > 0, customer_history.c.first_order_at >= start)).label("new_customers"),
            _count_when(and_(customer_history.c.orders_today > 0, customer_history.c.first_order_at < start)).label("returning_customers"),
        )
    ).mappings().one()

    revenue = money(values["today_revenue"])
    today_order_count = int(values["today_orders_count"] or 0)
    warnings = []
    if not values["eligible_order_count"]:
        warnings += warning("limited_order_history", "info", "No local order snapshots are available for this dashboard yet.")
    if values["missing_today_sales_total_count"]:
        warnings += warning("missing_order_total", "warning", "Some orders are missing totals; line totals are used where possible.")
    if not values["subscription_source_count"]:
        warnings += warning("missing_subscription_data", "info", "Subscription data is not synced yet.")

    summary = {
        "today_date": target_date.isoformat(),
        "today_orders_count": today_order_count,
        "today_revenue": dec(revenue),
        "today_new_customers": int(customer_values["new_customers"] or 0),
        "today_returning_customers": int(customer_values["returning_customers"] or 0),
        "today_subscription_orders": int(values["today_subscription_orders"] or 0),
        "today_units_sold": dec(units_sold),
        "open_orders_count": int(values["open_orders_count"] or 0),
        "completed_orders_today": int(values["completed_orders_today"] or 0),
        "failed_orders_today": int(values["failed_orders_today"] or 0),
        "cancelled_orders_today": int(values["cancelled_orders_today"] or 0),
        "average_order_value_today": dec(revenue / Decimal(today_order_count)) if today_order_count else 0,
    }
    return {"summary": summary, "data_quality": warnings}


def build_open_orders_from_sql(db: Session) -> dict[str, Any]:
    condition = and_(eligible_order_condition(), normalized_status_expression().in_(OPEN_STATUSES))
    summary = db.execute(
        select(
            func.count(Order.id).label("open_orders_count"),
            _count_when(Order.total.is_(None)).label("missing_total_count"),
        ).where(condition)
    ).mappings().one()
    rows = list(
        db.scalars(
            select(Order)
            .where(condition)
            .options(load_only(*BUSINESS_ORDER_COLUMNS), selectinload(Order.items).load_only(*BUSINESS_LINE_COLUMNS))
            .order_by(order_date_expression().desc().nullslast(), Order.id.asc())
            .limit(BUSINESS_OPEN_ORDER_ROW_LIMIT)
        ).all()
    )
    warnings = []
    if summary["missing_total_count"]:
        warnings += warning("missing_order_total", "warning", "Some orders are missing totals; line totals are used where possible.")
    return {
        "summary": {"open_orders_count": int(summary["open_orders_count"] or 0)},
        "rows": [order_row(order) for order in rows],
        "data_quality": warnings,
    }


def build_revenue_comparison_from_sql(db: Session, target_date: date, mode: str) -> dict[str, Any]:
    if mode == "last_7_days":
        current_start = target_date - timedelta(days=6)
    elif mode == "today":
        current_start = target_date
    else:
        current_start = target_date.replace(day=1)
    previous_start = previous_month_date(current_start)
    previous_end = previous_start + (target_date - current_start)
    current_days = days_between(current_start, target_date)
    previous_days = days_between(previous_start, previous_end)

    order_timestamp = order_date_expression()
    order_value = order_total_expression()
    all_days = current_days + previous_days
    range_start, _ = admin_day_bounds(min(all_days))
    _, range_end = admin_day_bounds(max(all_days))
    day_columns = []
    for prefix, days in (("current", current_days), ("previous", previous_days)):
        for index, day in enumerate(days):
            start, end = admin_day_bounds(day)
            day_columns.append(
                func.coalesce(
                    func.sum(case((and_(order_timestamp >= start, order_timestamp < end), order_value), else_=0)),
                    0,
                ).label(f"{prefix}_{index}")
            )
    totals = db.execute(
        select(*day_columns).where(
            eligible_order_condition(),
            sales_order_condition(),
            order_timestamp >= range_start,
            order_timestamp < range_end,
        )
    ).mappings().one()
    quality = db.execute(
        select(
            func.count(Order.id).label("eligible_order_count"),
            _count_when(Order.total.is_(None)).label("missing_total_count"),
        ).where(eligible_order_condition())
    ).mappings().one()

    daily_series = []
    for index, current_day in enumerate(current_days):
        previous_day = previous_days[index]
        daily_series.append(
            {
                "day_index": index + 1,
                "current_date": current_day.isoformat(),
                "current_revenue": dec(totals[f"current_{index}"]),
                "previous_date": previous_day.isoformat(),
                "previous_revenue": dec(totals[f"previous_{index}"]),
            }
        )
    current_revenue = sum((money(row["current_revenue"]) for row in daily_series), Decimal("0"))
    previous_revenue = sum((money(row["previous_revenue"]) for row in daily_series), Decimal("0"))
    delta = current_revenue - previous_revenue
    warnings = []
    if not quality["eligible_order_count"]:
        warnings += warning("limited_order_history", "info", "No local order snapshots are available for this dashboard yet.")
    if quality["missing_total_count"]:
        warnings += warning("missing_order_total", "warning", "Some orders are missing totals; line totals are used where possible.")
    return {
        "summary": {
            "current_period_label": period_label(current_start, target_date),
            "previous_period_label": period_label(previous_start, previous_end),
            "current_period_revenue": dec(current_revenue),
            "previous_period_revenue": dec(previous_revenue),
            "delta_amount": dec(delta),
            "delta_percent": percent(delta, previous_revenue),
        },
        "daily_series": daily_series,
        "data_quality": warnings,
    }


def load_orders_for_day(
    db: Session,
    target_date: date,
    *,
    include_payload: bool = False,
    include_lines: bool = False,
) -> list[Order]:
    start, end = admin_day_bounds(target_date)
    columns = list(BUSINESS_ORDER_COLUMNS)
    if include_payload:
        columns.append(Order.raw_woo_payload)
    options = [load_only(*columns)]
    if include_lines:
        options.append(selectinload(Order.items).load_only(*BUSINESS_LINE_COLUMNS))
    return list(
        db.scalars(
            select(Order)
            .where(
                eligible_order_condition(),
                order_date_expression() >= start,
                order_date_expression() < end,
            )
            .options(*options)
            .order_by(Order.id.asc())
        ).all()
    )


def eligible_order_condition():
    return or_(Order.is_historical_snapshot.is_(False), Order.historical_source_present.is_(True))


def order_date_expression():
    return func.coalesce(Order.placed_on, Order.date_created, Order.completed_on, Order.created_at)


def normalized_status_expression():
    return func.lower(
        func.trim(
            func.coalesce(
                func.nullif(Order.local_status, ""),
                func.nullif(Order.status, ""),
                Order.woo_status,
                "",
            )
        )
    )


def sales_order_condition():
    status = func.lower(func.trim(func.coalesce(Order.status, "")))
    woo_status = func.lower(func.trim(func.coalesce(Order.woo_status, "")))
    local_status = func.lower(func.trim(func.coalesce(Order.local_status, "")))
    return and_(
        ~or_(status.in_(FAILED_STATUSES), woo_status.in_(FAILED_STATUSES), local_status.in_(FAILED_STATUSES)),
        or_(status.in_(SALES_STATUSES), woo_status.in_(SALES_STATUSES), local_status.in_(SALES_STATUSES)),
    )


def normalized_email_expression():
    return func.lower(func.trim(func.coalesce(Order.customer_email, "")))


def subscription_order_condition():
    return and_(
        Order.raw_woo_payload.is_not(None),
        func.lower(cast(Order.raw_woo_payload, Text)).like("%subscription%"),
    )


def line_quantity_expression():
    return func.coalesce(func.nullif(OrderItem.quantity_ordered, 0), OrderItem.ordered_qty, 0)


def line_total_expression():
    return case(
        (OrderItem.total_price.is_not(None), OrderItem.total_price),
        (OrderItem.line_total.is_not(None), OrderItem.line_total),
        else_=func.coalesce(OrderItem.unit_price, 0) * line_quantity_expression(),
    )


def order_total_expression():
    fallback = (
        select(func.coalesce(func.sum(line_total_expression()), 0))
        .where(OrderItem.order_id == Order.id)
        .correlate(Order)
        .scalar_subquery()
    )
    return func.coalesce(Order.total, fallback)


def admin_day_bounds(value: date) -> tuple[datetime, datetime]:
    zone = admin_timezone()
    start = datetime.combine(value, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(value + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, end


def _count_when(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def open_order_rows(orders: list[Order]) -> list[Order]:
    rows = [order for order in orders if normalized_status(order) in OPEN_STATUSES]
    rows.sort(key=lambda order: order_date(order) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return rows


def order_row(order: Order) -> dict[str, Any]:
    return {
        "order_number": order.woo_order_number or order.order_number,
        "woo_order_id": order.woo_order_id,
        "customer_name": order.customer_name or full_name(order),
        "customer_email": normalized_email(order.customer_email),
        "customer_phone": order.customer_phone or order.shipping_phone or order.billing_phone,
        "status": order.local_status or order.status or order.woo_status,
        "payment_status": order.payment_method_title or order.payment_method,
        "placed_on": iso(order_date(order)),
        "order_total": dec(order_total(order)),
        "item_count": len(order.items),
        "total_quantity": dec(sum((line_qty(line) for line in order.items), Decimal("0"))),
        "city": order.shipping_city or order.billing_city,
        "postal_code": order.shipping_zip or order.billing_zip,
        "shipping_address_summary": shipping_summary(order),
    }


def coordinates_for_order(order: Order) -> tuple[float | None, float | None, bool]:
    payload = order.raw_woo_payload or {}
    for source in [payload.get("shipping") or {}, payload.get("billing") or {}, payload]:
        latitude = source.get("latitude") or source.get("lat")
        longitude = source.get("longitude") or source.get("lng") or source.get("lon")
        if latitude is not None and longitude is not None:
            return float(latitude), float(longitude), False
    city = clean(order.shipping_city or order.billing_city).lower()
    if city in CITY_COORDINATES:
        lat, lng = CITY_COORDINATES[city]
        return lat, lng, True
    return None, None, False


def is_subscription_order(order: Order) -> bool:
    payload = order.raw_woo_payload or {}
    if payload.get("subscription_renewal") or payload.get("subscription_id") or payload.get("subscriptions"):
        return True
    return "subscription" in str(payload).lower()


def any_subscription_data(orders: list[Order]) -> bool:
    return any(is_subscription_order(order) for order in orders)


def revenue_for_day(orders: list[Order], day: date) -> Decimal:
    return sum((order_total(order) for order in orders if order_is_on_date(order, day) and is_sales_order(order)), Decimal("0"))


def order_is_on_date(order: Order, day: date) -> bool:
    return order_day(order) == day


def order_day(order: Order) -> date | None:
    value = order_date(order)
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.astimezone(admin_timezone()).date()


def admin_timezone(settings=None) -> ZoneInfo:
    try:
        return ZoneInfo((settings or get_settings()).admin_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def admin_today(now: datetime | None = None, settings=None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(admin_timezone(settings)).date()


def order_date(order: Order) -> datetime | None:
    return order.placed_on or order.date_created or order.completed_on or order.created_at


def order_total(order: Order) -> Decimal:
    if order.total is not None:
        return money(order.total)
    return sum((line_total(line) for line in order.items), Decimal("0"))


def line_total(line: OrderItem) -> Decimal:
    if line.total_price is not None:
        return money(line.total_price)
    if line.line_total is not None:
        return money(line.line_total)
    return money(line.unit_price) * line_qty(line)


def line_qty(line: OrderItem) -> Decimal:
    return money(line.quantity_ordered or line.ordered_qty)


def normalized_status(order: Order) -> str:
    return clean(order.local_status or order.status or order.woo_status).lower()


def is_sales_order(order: Order) -> bool:
    statuses = {clean(order.status).lower(), clean(order.woo_status).lower(), clean(order.local_status).lower()}
    return not statuses & FAILED_STATUSES and bool(statuses & SALES_STATUSES)


def customer_key(order: Order) -> str:
    email = normalized_email(order.customer_email)
    if email:
        return email
    if order.customer_id:
        return f"customer:{order.customer_id}"
    fallback = f"{clean(order.customer_name or full_name(order))}|{clean(order.customer_phone or order.shipping_phone or order.billing_phone)}|{clean(order.shipping_zip or order.billing_zip)}"
    return f"guest:{fallback if fallback != '||' else order.id}"


def data_quality_warnings(orders: list[Order], include_limited_history: bool) -> list[dict[str, str]]:
    warnings = []
    if include_limited_history:
        warnings += warning("limited_order_history", "info", "No local order snapshots are available for this dashboard yet.")
    if any(order.total is None for order in orders):
        warnings += warning("missing_order_total", "warning", "Some orders are missing totals; line totals are used where possible.")
    return warnings


def merge_warnings(*groups: list[dict[str, str]]) -> list[dict[str, str]]:
    merged = {}
    for group in groups:
        for row in group:
            merged[row["code"]] = row
    return list(merged.values())


def warning(code: str, severity: str, message: str) -> list[dict[str, str]]:
    return [{"code": code, "severity": severity, "message": message}]


def previous_month_date(value: date) -> date:
    month = value.month - 1 or 12
    year = value.year - 1 if value.month == 1 else value.year
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def days_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=index) for index in range((end - start).days + 1)]


def period_label(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%B %-d")
    return f"{start.strftime('%B %-d')}-{end.day}"


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def shipping_summary(order: Order) -> str:
    return ", ".join(part for part in [order.shipping_address_1, order.shipping_city, order.shipping_state, order.shipping_zip] if part)


def full_name(order: Order) -> str:
    return clean(f"{order.customer_first_name or ''} {order.customer_last_name or ''}")


def normalized_email(value: str | None) -> str:
    return clean(value).lower()


def clean(value: Any) -> str:
    return str(value or "").strip()


def money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def dec(value: Any) -> float:
    return round(float(value or 0), 2)


def percent(numerator: Decimal, denominator: Decimal) -> float:
    if denominator == 0:
        return 0
    return round(float(numerator / denominator * Decimal("100")), 2)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
