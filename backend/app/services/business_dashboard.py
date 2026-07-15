from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.orders import Order, OrderItem


OPEN_STATUSES = {"open", "processing", "on-hold", "pending", "allocated", "partially_allocated", "picked", "partially_picked"}
DONE_STATUSES = {"completed", "fulfilled", "partially_fulfilled"}
FAILED_STATUSES = {"failed", "cancelled", "canceled", "refunded"}
CITY_COORDINATES = {
    "edmonton": (53.5461, -113.4938),
    "sherwood park": (53.5412, -113.2957),
    "leduc": (53.2594, -113.5493),
    "st. albert": (53.6305, -113.6256),
    "beaumont": (53.3528, -113.4152),
    "spruce grove": (53.5414, -113.9007),
    "fort saskatchewan": (53.7126, -113.2140),
}


def build_business_dashboard(db: Session, target_date: date | None = None) -> dict[str, Any]:
    target_date = target_date or date.today()
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


def build_today(db: Session, target_date: date | None = None) -> dict[str, Any]:
    target_date = target_date or date.today()
    orders = load_orders(db)
    today_orders = [order for order in orders if order_is_on_date(order, target_date)]
    customers_today = {customer_key(order) for order in today_orders}
    earlier_customers = {customer_key(order) for order in orders if order_day(order) and order_day(order) < target_date}
    revenue = sum((order_total(order) for order in today_orders), Decimal("0"))
    subscription_count = sum(1 for order in today_orders if is_subscription_order(order))
    warnings = data_quality_warnings(orders=today_orders, include_limited_history=not orders)
    if not any_subscription_data(orders):
        warnings += warning("missing_subscription_data", "info", "Subscription data is not synced yet.")
    summary = {
        "today_date": target_date.isoformat(),
        "today_orders_count": len(today_orders),
        "today_revenue": dec(revenue),
        "today_new_customers": sum(1 for customer in customers_today if customer not in earlier_customers),
        "today_returning_customers": sum(1 for customer in customers_today if customer in earlier_customers),
        "today_subscription_orders": subscription_count,
        "today_units_sold": dec(sum((line_qty(line) for order in today_orders for line in order.items), Decimal("0"))),
        "open_orders_count": len(open_order_rows(orders)),
        "completed_orders_today": sum(1 for order in today_orders if normalized_status(order) in DONE_STATUSES),
        "failed_orders_today": sum(1 for order in today_orders if normalized_status(order) == "failed"),
        "cancelled_orders_today": sum(1 for order in today_orders if normalized_status(order) in {"cancelled", "canceled"}),
        "average_order_value_today": dec(revenue / Decimal(len(today_orders))) if today_orders else 0,
    }
    return {"summary": summary, "data_quality": warnings}


def build_open_orders(db: Session) -> dict[str, Any]:
    orders = load_orders(db)
    rows = open_order_rows(orders)
    warnings = data_quality_warnings(orders=rows, include_limited_history=False)
    return {"summary": {"open_orders_count": len(rows)}, "rows": [order_row(order) for order in rows], "data_quality": warnings}


def build_subscriptions(db: Session, target_date: date | None = None) -> dict[str, Any]:
    orders = load_orders(db)
    rows = []
    for order in orders:
        payload = order.raw_woo_payload or {}
        subscription_rows = payload.get("subscriptions") or payload.get("subscription_items") or []
        if isinstance(subscription_rows, dict):
            subscription_rows = [subscription_rows]
        for row in subscription_rows:
            rows.append(
                {
                    "subscription_id": row.get("id") or row.get("subscription_id"),
                    "product_name": row.get("product_name") or row.get("name"),
                    "customer_name": order.customer_name or full_name(order),
                    "customer_email": normalized_email(order.customer_email),
                    "next_payment_date": row.get("next_payment_date") or row.get("next_payment"),
                    "quantity_due": row.get("quantity") or row.get("quantity_due") or 1,
                    "status": row.get("status"),
                    "order_number": order.woo_order_number or order.order_number,
                    "sku": row.get("sku"),
                }
            )
    available = bool(rows)
    warnings = [] if available else warning("missing_subscription_data", "info", "Subscription data is not synced yet. This section will populate after subscription sync is connected.")
    return {
        "summary": {
            "upcoming_7_days_count": count_due_within(rows, target_date or date.today(), 7),
            "upcoming_30_days_count": count_due_within(rows, target_date or date.today(), 30),
            "active_subscriptions_count": sum(1 for row in rows if str(row.get("status") or "").lower() == "active"),
            "subscription_data_available": available,
        },
        "rows": rows,
        "data_quality": warnings,
        "empty_state": None if available else "Subscription data is not synced yet.",
    }


def build_revenue_comparison(db: Session, target_date: date | None = None, mode: str = "month_to_date") -> dict[str, Any]:
    target_date = target_date or date.today()
    orders = load_orders(db)
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


def build_order_map(db: Session, target_date: date | None = None) -> dict[str, Any]:
    target_date = target_date or date.today()
    orders = [order for order in load_orders(db) if order_is_on_date(order, target_date)]
    city_groups = defaultdict(lambda: {"orders": [], "customers": set(), "revenue": Decimal("0")})
    markers = []
    unplotted = 0
    for order in orders:
        city = clean(order.shipping_city or order.billing_city or "Unknown")
        city_key = city.lower()
        city_groups[city]["orders"].append(order)
        city_groups[city]["customers"].add(customer_key(order))
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


def load_orders(db: Session) -> list[Order]:
    return list(db.scalars(select(Order).options(selectinload(Order.items))).all())


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


def count_due_within(rows: list[dict[str, Any]], target_date: date, days: int) -> int:
    end = target_date + timedelta(days=days)
    count = 0
    for row in rows:
        due = parse_date(row.get("next_payment_date"))
        if due and target_date <= due <= end:
            count += 1
    return count


def revenue_for_day(orders: list[Order], day: date) -> Decimal:
    return sum((order_total(order) for order in orders if order_is_on_date(order, day)), Decimal("0"))


def order_is_on_date(order: Order, day: date) -> bool:
    return order_day(order) == day


def order_day(order: Order) -> date | None:
    value = order_date(order)
    return value.date() if value else None


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


def customer_key(order: Order) -> str:
    email = normalized_email(order.customer_email)
    if email:
        return email
    if order.customer_id is not None:
        return f"customer:{order.customer_id}"
    return f"guest:{clean(order.customer_name or full_name(order))}|{clean(order.customer_phone or order.shipping_phone or order.billing_phone)}|{clean(order.shipping_zip or order.billing_zip)}"


def data_quality_warnings(orders: list[Order], include_limited_history: bool) -> list[dict[str, str]]:
    warnings = []
    if include_limited_history:
        warnings += warning("limited_order_history", "info", "No local order snapshots are available for this dashboard yet.")
    if any(order.total is None for order in orders):
        warnings += warning("missing_order_total", "warning", "Some orders are missing totals; line totals are used where possible.")
    if any(not normalized_email(order.customer_email) for order in orders):
        warnings += warning("missing_customer_email", "info", "Some orders are missing customer email, so customer counts may use fallback identities.")
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
