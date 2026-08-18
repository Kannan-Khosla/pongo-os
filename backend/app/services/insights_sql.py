from __future__ import annotations

"""Database-first builders for the interactive Insights screens.

The original implementation materialized every matching ``Order``, every line,
every Woo payload, and the complete item catalog before calculating even a
single headline.  These builders keep the same response contract and business
definitions, but push the work into bounded scalar queries and SQL aggregates.
Only drill-down rows are materialized, and those always respect the requested
``limit``/``offset`` (with a hard interactive-page limit of 100 rows).
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from numbers import Number
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import (
    JSON,
    Date,
    Integer,
    Numeric,
    String,
    and_,
    case,
    cast,
    desc,
    distinct,
    func,
    literal,
    not_,
    or_,
    select,
    true,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import FunctionElement

from app.core.config import get_settings
from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.schemas.insights import InsightResponse
from app.services.woocommerce_subscriptions import build_subscription_data


SUCCESS_STATUSES = {
    "completed",
    "processing",
    "fulfilled",
    "partially_fulfilled",
    "open",
    "allocated",
    "picked",
    "refunded",
}
FAILED_STATUSES = {"failed", "cancelled", "canceled"}
DETAIL_LIMIT = 100


class JsonRefundTotal(FunctionElement):
    """Sum refunds inside a Woo payload without returning the payload to Python."""

    type = Numeric(14, 2)
    inherit_cache = True


@compiles(JsonRefundTotal, "sqlite")
def _compile_refund_total_sqlite(element, compiler, **kw):
    payload = compiler.process(list(element.clauses)[0], **kw)
    return (
        "(SELECT COALESCE(SUM(ABS(CAST(COALESCE("
        "json_extract(refund.value, '$.total'), "
        "json_extract(refund.value, '$.amount'), 0) AS NUMERIC))), 0) "
        f"FROM json_each({payload}, '$.refunds') AS refund)"
    )


@compiles(JsonRefundTotal, "postgresql")
def _compile_refund_total_postgresql(element, compiler, **kw):
    payload = compiler.process(list(element.clauses)[0], **kw)
    return (
        "(SELECT COALESCE(SUM(ABS(CAST(COALESCE("
        "refund.value->>'total', refund.value->>'amount', '0') AS NUMERIC))), 0) "
        f"FROM json_array_elements(COALESCE(({payload})->'refunds', '[]'::json)) AS refund(value))"
    )


class JsonHasRefunds(FunctionElement):
    type = Integer()
    inherit_cache = True


@compiles(JsonHasRefunds, "sqlite")
def _compile_has_refunds_sqlite(element, compiler, **kw):
    payload = compiler.process(list(element.clauses)[0], **kw)
    return f"CASE WHEN json_type({payload}, '$.refunds') IS NULL THEN 0 ELSE 1 END"


@compiles(JsonHasRefunds, "postgresql")
def _compile_has_refunds_postgresql(element, compiler, **kw):
    payload = compiler.process(list(element.clauses)[0], **kw)
    return f"CASE WHEN ({payload})->'refunds' IS NULL THEN 0 ELSE 1 END"


@dataclass(frozen=True)
class SqlInsightContext:
    db: Session
    params: dict[str, Any]
    start: datetime | None
    end: datetime | None
    limit: int
    offset: int

    @property
    def product_filtered(self) -> bool:
        return any(clean(self.params.get(key)) for key in ("sku", "brand", "category"))

    @property
    def dialect(self) -> str:
        return self.db.get_bind().dialect.name


def build_context(db: Session, params: dict[str, Any]) -> SqlInsightContext:
    requested_limit = int(params.get("limit") or DETAIL_LIMIT)
    maximum = 100_000 if params.get("_export") else DETAIL_LIMIT
    return SqlInsightContext(
        db=db,
        params=params,
        start=parse_date(params.get("start_date")),
        end=parse_date(params.get("end_date"), end_of_day=True),
        limit=min(max(requested_limit, 1), maximum),
        offset=max(int(params.get("offset") or 0), 0),
    )


def build_insight(db: Session, dashboard: str, params: dict[str, Any] | None = None) -> InsightResponse:
    params = params or {}
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
    context = build_context(db, params)
    result = builders[dashboard](context)
    if params.get("compare_start_date") and params.get("compare_end_date"):
        comparison_params = {
            **params,
            "start_date": params["compare_start_date"],
            "end_date": params["compare_end_date"],
            "compare_start_date": None,
            "compare_end_date": None,
            # Comparisons only expose summary values, never drill-down pages.
            "limit": 1,
            "offset": 0,
        }
        previous = builders[dashboard](build_context(db, comparison_params))
        result.comparison = {
            "start_date": params["compare_start_date"],
            "end_date": params["compare_end_date"],
            "summary": previous.summary,
            "changes": summary_changes(result.summary, previous.summary),
        }
    return result


def reporting_order_date(order=Order):
    return func.coalesce(order.placed_on, order.date_created, order.completed_on, order.created_at)


def reporting_order_filter(order=Order):
    return or_(order.is_historical_snapshot.is_(False), order.historical_source_present.is_(True))


def successful_order_filter(order=Order):
    statuses = [func.lower(func.coalesce(column, "")) for column in (order.status, order.woo_status, order.local_status)]
    return and_(
        not_(or_(*(status.in_(FAILED_STATUSES) for status in statuses))),
        or_(*(status.in_(SUCCESS_STATUSES) for status in statuses)),
    )


def sql_first_nonblank(*columns):
    return func.coalesce(*(func.nullif(func.trim(column), "") for column in columns), "")


def sql_customer_email(order=Order):
    return func.lower(func.trim(func.coalesce(order.customer_email, "")))


def sql_customer_key(order=Order):
    email = sql_customer_email(order)
    phone = sql_first_nonblank(order.customer_phone, order.shipping_phone, order.billing_phone)
    name = sql_first_nonblank(
        order.customer_name,
        func.trim(func.coalesce(order.customer_first_name, "") + literal(" ") + func.coalesce(order.customer_last_name, "")),
    )
    postal = sql_first_nonblank(order.shipping_zip, order.billing_zip)
    fallback = phone + literal("|") + name + literal("|") + postal
    return case(
        (email != "", email),
        (order.customer_id.is_not(None), literal("customer:") + cast(order.customer_id, String)),
        else_=literal("guest:") + case((fallback != "||", fallback), else_=cast(order.id, String)),
    )


def line_quantity(line=OrderItem):
    return case(
        (func.coalesce(line.quantity_ordered, 0) != 0, func.coalesce(line.quantity_ordered, 0)),
        else_=func.coalesce(line.ordered_qty, 0),
    )


def line_revenue(line=OrderItem):
    return func.coalesce(line.total_price, line.line_total, func.coalesce(line.unit_price, 0) * line_quantity(line), 0)


def line_gross(line=OrderItem):
    return func.coalesce(line.line_subtotal, line_revenue(line), 0)


def _order_conditions(ctx: SqlInsightContext, *, successful: bool) -> list[Any]:
    conditions: list[Any] = [reporting_order_filter()]
    placed_at = reporting_order_date()
    if ctx.start is not None:
        conditions.append(placed_at >= ctx.start)
    if ctx.end is not None:
        conditions.append(placed_at <= ctx.end)
    if successful:
        conditions.append(successful_order_filter())

    status = clean(ctx.params.get("order_status")).lower()
    if status:
        conditions.append(or_(*(func.lower(func.coalesce(column, "")) == status for column in (Order.status, Order.local_status, Order.woo_status))))
    payment = clean(ctx.params.get("payment_method")).lower()
    if payment:
        conditions.append(func.lower(sql_first_nonblank(Order.payment_method_title, Order.payment_method)).contains(payment))
    email = normalized_email(ctx.params.get("customer_email"))
    if email:
        conditions.append(sql_customer_email() == email)
    city = clean(ctx.params.get("city")).lower()
    if city:
        conditions.append(func.lower(sql_first_nonblank(Order.shipping_city, Order.billing_city)).contains(city))
    postal = clean(ctx.params.get("postal_code")).lower()
    if postal:
        conditions.append(func.lower(sql_first_nonblank(Order.shipping_zip, Order.billing_zip)).contains(postal))

    if ctx.product_filtered:
        line_conditions = [OrderItem.order_id == Order.id, *_line_filter_conditions(ctx)]
        conditions.append(
            select(OrderItem.id)
            .outerjoin(InventoryItem, InventoryItem.id == OrderItem.inventory_item_id)
            .where(*line_conditions)
            .exists()
        )
    return conditions


def _line_filter_conditions(ctx: SqlInsightContext) -> list[Any]:
    conditions: list[Any] = []
    sku = clean_key(ctx.params.get("sku"))
    brand = clean(ctx.params.get("brand")).lower()
    category = clean(ctx.params.get("category")).lower()
    if sku:
        conditions.append(func.upper(sql_first_nonblank(OrderItem.sku, InventoryItem.sku)) == sku)
    if brand:
        conditions.append(func.lower(sql_first_nonblank(OrderItem.brand, InventoryItem.brand)) == brand)
    if category:
        conditions.append(func.lower(func.trim(func.coalesce(InventoryItem.category, ""))) == category)
    return conditions


def order_scope(ctx: SqlInsightContext, *, successful: bool, include_payload: bool = False):
    columns = [
        Order.id.label("id"),
        Order.status.label("status"),
        Order.local_status.label("local_status"),
        Order.woo_status.label("woo_status"),
        Order.customer_id.label("customer_id"),
        Order.customer_first_name.label("customer_first_name"),
        Order.customer_last_name.label("customer_last_name"),
        Order.customer_name.label("customer_name"),
        Order.customer_email.label("customer_email"),
        Order.customer_phone.label("customer_phone"),
        Order.shipping_phone.label("shipping_phone"),
        Order.billing_phone.label("billing_phone"),
        Order.payment_method.label("payment_method"),
        Order.payment_method_title.label("payment_method_title"),
        Order.subtotal.label("subtotal"),
        Order.discount_total.label("discount_total"),
        Order.shipping_total.label("shipping_total"),
        Order.tax_total.label("tax_total"),
        Order.total.label("total"),
        reporting_order_date().label("placed_at"),
        Order.shipping_city.label("shipping_city"),
        Order.billing_city.label("billing_city"),
        Order.shipping_zip.label("shipping_zip"),
        Order.billing_zip.label("billing_zip"),
    ]
    if include_payload:
        columns.append(Order.raw_woo_payload.label("raw_woo_payload"))
    return select(*columns).where(*_order_conditions(ctx, successful=successful)).subquery()


def _scoped_line_aggregate(ctx: SqlInsightContext, orders):
    statement = (
        select(
            OrderItem.order_id.label("order_id"),
            func.count(OrderItem.id).label("line_count"),
            func.coalesce(func.sum(line_quantity()), 0).label("units"),
            func.coalesce(func.sum(line_revenue()), 0).label("net_lines"),
            func.coalesce(func.sum(line_gross()), 0).label("gross_lines"),
        )
        .select_from(OrderItem)
        .join(orders, orders.c.id == OrderItem.order_id)
        .outerjoin(InventoryItem, InventoryItem.id == OrderItem.inventory_item_id)
    )
    filters = _line_filter_conditions(ctx)
    if filters:
        statement = statement.where(*filters)
    return statement.group_by(OrderItem.order_id).subquery()


def per_order_metrics(ctx: SqlInsightContext, *, successful: bool, include_payload: bool = False):
    # Refund data is transformed inside SQL; it is never returned or materialized.
    orders = order_scope(ctx, successful=successful, include_payload=True)
    lines = _scoped_line_aggregate(ctx, orders)
    line_count = func.coalesce(lines.c.line_count, 0)
    net_before_refund = case(
        (line_count > 0, func.coalesce(lines.c.net_lines, 0)),
        else_=func.coalesce(orders.c.total, 0) - func.coalesce(orders.c.shipping_total, 0) - func.coalesce(orders.c.tax_total, 0),
    )
    refund_total = JsonRefundTotal(orders.c.raw_woo_payload)
    refund_present = JsonHasRefunds(orders.c.raw_woo_payload)
    net = net_before_refund
    if not ctx.product_filtered:
        net = case((net_before_refund - refund_total < 0, 0), else_=net_before_refund - refund_total)
    gross = (
        func.coalesce(lines.c.gross_lines, 0)
        if ctx.product_filtered
        else func.coalesce(orders.c.subtotal, lines.c.gross_lines, 0)
    )
    discount = (
        case((gross - net_before_refund < 0, 0), else_=gross - net_before_refund)
        if ctx.product_filtered
        else func.coalesce(orders.c.discount_total, 0)
    )
    columns = [
        *[orders.c[name] for name in orders.c.keys() if name != "raw_woo_payload"],
        sql_customer_email(orders.c).label("customer_email_key"),
        sql_customer_key(orders.c).label("customer_key"),
        line_count.label("line_count"),
        func.coalesce(lines.c.units, 0).label("units"),
        gross.label("gross"),
        net.label("net"),
        discount.label("discount"),
        refund_total.label("refund_total"),
        refund_present.label("refund_present"),
    ]
    if include_payload:
        columns.append(orders.c.raw_woo_payload.label("raw_woo_payload"))
    return select(*columns).select_from(orders).outerjoin(lines, lines.c.order_id == orders.c.id).subquery()


def _period_expression(ctx: SqlInsightContext, value):
    granularity = clean(ctx.params.get("granularity")) or "day"
    if ctx.dialect == "sqlite":
        if granularity == "week":
            weekday = (cast(func.strftime("%w", value), Integer) + 6) % 7
            return func.date(value, func.printf("-%d days", weekday))
        return func.date(value)
    if granularity == "week":
        return cast(func.date_trunc("week", value), Date)
    return cast(value, Date)


def _days_between(ctx: SqlInsightContext, later, earlier):
    if ctx.dialect == "sqlite":
        return cast(func.julianday(later) - func.julianday(earlier), Integer)
    return cast(func.extract("epoch", later - earlier) / 86400, Integer)


def _warnings(ctx: SqlInsightContext, order_count: int, *, include_cost: bool = True) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if order_count == 0:
        warnings += warning("limited_order_history", "info", "No local order snapshots matched the current filters.")
    if include_cost and ctx.db.scalar(select(InventoryItem.id).where(InventoryItem.unit_cost.is_(None)).limit(1)) is not None:
        warnings += warning("missing_unit_cost", "warning", "Some inventory items are missing unit cost, so margin and value metrics may be incomplete.")
    return warnings


def order_summary(ctx: SqlInsightContext, *, successful: bool = True) -> tuple[dict[str, Any], Any]:
    per_order = per_order_metrics(ctx, successful=successful)
    row = ctx.db.execute(
        select(
            func.count(per_order.c.id).label("total_orders"),
            func.coalesce(func.sum(per_order.c.gross), 0).label("gross_sales"),
            func.coalesce(func.sum(per_order.c.net), 0).label("net_sales"),
            func.coalesce(func.sum(per_order.c.units), 0).label("units_sold"),
            func.coalesce(func.sum(per_order.c.discount), 0).label("discount_amount"),
            func.coalesce(func.sum(per_order.c.shipping_total), 0).label("shipping_revenue"),
            func.coalesce(func.sum(per_order.c.tax_total), 0).label("tax_total"),
            func.coalesce(func.sum(per_order.c.refund_total), 0).label("refund_amount"),
            func.coalesce(func.sum(per_order.c.refund_present), 0).label("refund_present_count"),
        )
    ).mappings().one()
    count = int(row["total_orders"] or 0)
    gross = money(row["gross_sales"])
    net = money(row["net_sales"])
    refund_complete = bool(count and not ctx.product_filtered and int(row["refund_present_count"] or 0) == count)
    refunds = money(row["refund_amount"]) if refund_complete else None
    summary = {
        "total_orders": count,
        "gross_sales": dec(gross),
        "net_sales": dec(net),
        "average_order_value": dec(net / Decimal(count)) if count else None,
        "units_sold": dec(row["units_sold"]),
        "refund_amount": dec(refunds) if refunds is not None else None,
        "refund_rate": percent(refunds, gross) if refunds is not None else None,
        "discount_amount": dec(row["discount_amount"]),
        "shipping_revenue": dec(row["shipping_revenue"]),
        "tax_total": dec(row["tax_total"]),
    }
    return summary, per_order


def _median_sql(db: Session, value_statement) -> float:
    values = value_statement.subquery()
    ranked = select(
        values.c.value,
        func.row_number().over(order_by=values.c.value).label("rn"),
        func.count().over().label("n"),
    ).subquery()
    lower = cast((ranked.c.n + 1) / 2, Integer)
    upper = cast((ranked.c.n + 2) / 2, Integer)
    value = db.scalar(select(func.avg(ranked.c.value)).where(ranked.c.rn.in_([lower, upper])))
    return dec(value)


def daily_rows(ctx: SqlInsightContext, per_order) -> list[dict[str, Any]]:
    period = _period_expression(ctx, per_order.c.placed_at)
    rows = ctx.db.execute(
        select(
            period.label("date"),
            func.count(per_order.c.id).label("order_count"),
            func.coalesce(func.sum(per_order.c.gross), 0).label("gross_sales"),
            func.coalesce(func.sum(per_order.c.net), 0).label("net_sales"),
            func.coalesce(func.sum(per_order.c.units), 0).label("units_sold"),
        )
        .group_by(period)
        .order_by(period)
        .limit(400)
    ).mappings().all()
    return [
        {
            "date": iso_date(row["date"]),
            "order_count": int(row["order_count"] or 0),
            "gross_sales": dec(row["gross_sales"]),
            "net_sales": dec(row["net_sales"]),
            "units_sold": dec(row["units_sold"]),
        }
        for row in rows
    ]


def status_rows(ctx: SqlInsightContext, per_order) -> list[dict[str, Any]]:
    status = sql_first_nonblank(per_order.c.status, per_order.c.local_status, per_order.c.woo_status)
    rows = ctx.db.execute(
        select(
            case((status == "", "unknown"), else_=status).label("status"),
            func.count(per_order.c.id).label("order_count"),
            func.coalesce(func.sum(per_order.c.net), 0).label("revenue"),
        )
        .group_by(status)
        .order_by(status)
        .limit(100)
    ).mappings().all()
    return [{"status": row["status"], "order_count": int(row["order_count"]), "revenue": dec(row["revenue"])} for row in rows]


def refund_warnings(ctx: SqlInsightContext, summary: dict[str, Any]) -> list[dict[str, str]]:
    if ctx.product_filtered:
        return warning("sku_refund_allocation_unavailable", "info", "Order-level refunds cannot be assigned to filtered products from order summaries alone.")
    if summary["total_orders"] and summary["refund_amount"] is not None:
        return []
    return warning("missing_refund_data", "info", "Refund summaries are missing on some local orders, so refund metrics are unavailable.")


def orders_revenue(ctx: SqlInsightContext) -> InsightResponse:
    summary, per_order = order_summary(ctx, successful=True)
    summary.update(
        {
            "median_order_value": _median_sql(ctx.db, select(per_order.c.net.label("value"))),
            "units_per_order": safe_div(summary["units_sold"], summary["total_orders"]),
            "revenue_growth_percent": None,
            "order_growth_percent": None,
            "discount_rate": percent(summary["discount_amount"], summary["gross_sales"]),
        }
    )
    daily = daily_rows(ctx, per_order)
    payment = payment_rows(ctx, per_order)
    warnings = _warnings(ctx, summary["total_orders"]) + refund_warnings(ctx, summary)
    return response(
        "orders-revenue",
        summary=summary,
        metrics=summary,
        trends={
            "daily_revenue": daily,
            "revenue_by_day": daily,
            "orders_by_day": [{"date": row["date"], "order_count": row["order_count"]} for row in daily],
        },
        rows=daily,
        tables={"status_breakdown": status_rows(ctx, per_order), "payment_methods": payment},
        warnings=warnings,
        empty_state=None if summary["total_orders"] else "No matching completed or active sales orders",
    )


def _global_first_orders(ctx: SqlInsightContext):
    email = sql_customer_email()
    return (
        select(email.label("email"), func.min(reporting_order_date()).label("first_order"))
        .where(
            reporting_order_filter(),
            successful_order_filter(),
            email != "",
        )
        .group_by(email)
        .subquery()
    )


def customer_aggregate(ctx: SqlInsightContext, per_order=None):
    if per_order is None:
        per_order = per_order_metrics(ctx, successful=True)
    email_orders = select(
        per_order.c.id,
        per_order.c.customer_email_key.label("email"),
        per_order.c.customer_name,
        per_order.c.customer_first_name,
        per_order.c.customer_last_name,
        per_order.c.customer_phone,
        per_order.c.shipping_phone,
        per_order.c.billing_phone,
        per_order.c.placed_at,
        per_order.c.net,
    ).where(per_order.c.customer_email_key != "").subquery()
    previous_date = func.lag(email_orders.c.placed_at).over(
        partition_by=email_orders.c.email,
        order_by=(email_orders.c.placed_at, email_orders.c.id),
    )
    events = select(
        email_orders,
        _days_between(ctx, email_orders.c.placed_at, previous_date).label("interval_days"),
    ).subquery()
    intervals = select(
        events.c.email,
        func.avg(events.c.interval_days).label("average_days_between_orders"),
    ).where(events.c.interval_days.is_not(None)).group_by(events.c.email).subquery()
    names = sql_first_nonblank(
        events.c.customer_name,
        func.trim(func.coalesce(events.c.customer_first_name, "") + literal(" ") + func.coalesce(events.c.customer_last_name, "")),
    )
    phone = sql_first_nonblank(events.c.customer_phone, events.c.shipping_phone, events.c.billing_phone)
    aggregate = (
        select(
            events.c.email.label("customer_key"),
            func.max(names).label("customer_name"),
            events.c.email.label("email"),
            func.max(phone).label("phone"),
            func.count(events.c.id).label("order_count"),
            func.coalesce(func.sum(events.c.net), 0).label("lifetime_spend"),
            func.min(events.c.placed_at).label("first_order_date"),
            func.max(events.c.placed_at).label("last_order_date"),
            intervals.c.average_days_between_orders,
        )
        .outerjoin(intervals, intervals.c.email == events.c.email)
        .group_by(events.c.email, intervals.c.average_days_between_orders)
        .subquery()
    )
    return aggregate, per_order


def _customer_segment(ctx: SqlInsightContext, customers):
    recency = _days_between(ctx, datetime.now(timezone.utc), customers.c.last_order_date)
    return case(
        (and_(customers.c.order_count == 1, recency <= 30), "New Customers"),
        (customers.c.lifetime_spend >= 500, "Big Spenders"),
        (and_(customers.c.order_count >= 5, recency <= 45), "Champions"),
        (and_(customers.c.order_count >= 3, recency <= 90), "Loyal Customers"),
        (and_(customers.c.order_count >= 2, recency <= 60), "Potential Loyalists"),
        (customers.c.order_count == 1, "One-Time Customers"),
        (recency <= 120, "At Risk"),
        (recency <= 240, "Dormant"),
        else_="Lost",
    )


def customer_summary(ctx: SqlInsightContext, customers, per_order) -> dict[str, Any]:
    first_orders = _global_first_orders(ctx)
    new_condition = true()
    if ctx.start is not None:
        new_condition = and_(new_condition, first_orders.c.first_order >= ctx.start)
    if ctx.end is not None:
        new_condition = and_(new_condition, first_orders.c.first_order <= ctx.end)
    joined = select(
        customers,
        case((new_condition, 1), else_=0).label("is_new"),
        _days_between(ctx, datetime.now(timezone.utc), customers.c.last_order_date).label("recency_days"),
    ).join(first_orders, first_orders.c.email == customers.c.email).subquery()
    row = ctx.db.execute(
        select(
            func.count(joined.c.customer_key).label("total_customers"),
            func.coalesce(func.sum(joined.c.is_new), 0).label("new_customers"),
            func.coalesce(func.sum(case((joined.c.order_count == 1, 1), else_=0)), 0).label("one"),
            func.coalesce(func.sum(case((joined.c.order_count == 2, 1), else_=0)), 0).label("two"),
            func.coalesce(func.sum(case((joined.c.order_count >= 3, 1), else_=0)), 0).label("three_plus"),
            func.coalesce(func.sum(case((joined.c.recency_days >= 60, 1), else_=0)), 0).label("dormant_60"),
            func.coalesce(func.sum(case((joined.c.recency_days >= 90, 1), else_=0)), 0).label("dormant_90"),
            func.coalesce(func.sum(joined.c.order_count), 0).label("orders"),
            func.coalesce(func.sum(joined.c.lifetime_spend), 0).label("spend"),
            func.avg(joined.c.average_days_between_orders).label("average_interval"),
        )
    ).mappings().one()
    count = int(row["total_customers"] or 0)
    new = int(row["new_customers"] or 0)
    anonymous = int(ctx.db.scalar(select(func.count(per_order.c.id)).where(per_order.c.customer_email_key == "")) or 0)
    median_spend = _median_sql(ctx.db, select(customers.c.lifetime_spend.label("value")))
    return {
        "total_customers": count,
        "new_customers": new,
        "returning_customers": count - new,
        "guest_customers": 0,
        "registered_customers": count,
        "anonymous_orders_without_email": anonymous,
        "repeat_customer_rate": percent(count - new, count),
        "average_orders_per_customer": safe_div(row["orders"], count),
        "average_customer_lifetime_value": safe_div(row["spend"], count),
        "median_customer_lifetime_value": median_spend,
        "average_days_between_orders": dec(row["average_interval"]) if row["average_interval"] is not None else 0,
        "customers_with_1_order": int(row["one"] or 0),
        "customers_with_2_orders": int(row["two"] or 0),
        "customers_with_3_plus_orders": int(row["three_plus"] or 0),
        "dormant_customers_60_days": int(row["dormant_60"] or 0),
        "dormant_customers_90_days": int(row["dormant_90"] or 0),
    }


def customer_detail_rows(ctx: SqlInsightContext, customers, *, offset: int | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    rows = ctx.db.execute(
        select(customers)
        .order_by(customers.c.lifetime_spend.desc(), customers.c.customer_key)
        .offset(ctx.offset if offset is None else offset)
        .limit(ctx.limit if limit is None else limit)
    ).mappings().all()
    now = datetime.now(timezone.utc)
    return [
        {
            "customer_key": row["customer_key"],
            "customer_name": row["customer_name"],
            "email": row["email"],
            "phone": row["phone"],
            "order_count": int(row["order_count"]),
            "lifetime_spend": dec(row["lifetime_spend"]),
            "average_order_value": safe_div(row["lifetime_spend"], row["order_count"]),
            "first_order_date": iso(row["first_order_date"]),
            "last_order_date": iso(row["last_order_date"]),
            "average_days_between_orders": dec(row["average_days_between_orders"]) if row["average_days_between_orders"] is not None else None,
            "recency_days": (now - make_aware(row["last_order_date"])).days if row["last_order_date"] else None,
        }
        for row in rows
    ]


def customer_metrics(ctx: SqlInsightContext) -> InsightResponse:
    customers, per_order = customer_aggregate(ctx)
    summary = customer_summary(ctx, customers, per_order)
    reorder, reorder_total = reorder_detail_rows(ctx)
    summary["customers_due_to_reorder"] = reorder_total
    rows = customer_detail_rows(ctx, customers)
    dormant = [row for row in customer_detail_rows(replace(ctx, offset=0), customers, offset=0, limit=DETAIL_LIMIT) if (row["recency_days"] or 0) >= 60][:25]
    warnings = _warnings(ctx, int(ctx.db.scalar(select(func.count(per_order.c.id))) or 0))
    return response(
        "customer-metrics",
        summary=summary,
        metrics=summary,
        rows=rows,
        tables={"top_customers": customer_detail_rows(replace(ctx, offset=0), customers, offset=0, limit=25), "customers_due_to_reorder": reorder[:25], "dormant_customers": dormant},
        warnings=warnings,
    )


def customer_segmentation(ctx: SqlInsightContext) -> InsightResponse:
    customers, per_order = customer_aggregate(ctx)
    segment = _customer_segment(ctx, customers)
    segment_source = select(customers, segment.label("segment")).subquery()
    aggregates = ctx.db.execute(
        select(
            segment_source.c.segment,
            func.count(segment_source.c.customer_key).label("customer_count"),
            func.coalesce(func.sum(segment_source.c.lifetime_spend), 0).label("revenue"),
            func.coalesce(func.sum(case((segment_source.c.order_count > 1, 1), else_=0)), 0).label("repeat"),
        )
        .group_by(segment_source.c.segment)
        .order_by(desc("customer_count"), segment_source.c.segment)
    ).mappings().all()
    rows_raw = ctx.db.execute(
        select(segment_source)
        .order_by(segment_source.c.lifetime_spend.desc(), segment_source.c.customer_key)
        .offset(ctx.offset)
        .limit(ctx.limit)
    ).mappings().all()
    now = datetime.now(timezone.utc)
    rows = [
        {
            "customer_key": row["customer_key"],
            "customer_name": row["customer_name"],
            "email": row["email"],
            "phone": row["phone"],
            "order_count": int(row["order_count"]),
            "lifetime_spend": dec(row["lifetime_spend"]),
            "average_order_value": safe_div(row["lifetime_spend"], row["order_count"]),
            "first_order_date": iso(row["first_order_date"]),
            "last_order_date": iso(row["last_order_date"]),
            "average_days_between_orders": dec(row["average_days_between_orders"]) if row["average_days_between_orders"] is not None else None,
            "recency_days": (now - make_aware(row["last_order_date"])).days if row["last_order_date"] else None,
            "segment": row["segment"],
        }
        for row in rows_raw
    ]
    segment_rows = [
        {
            "segment": row["segment"],
            "customer_count": int(row["customer_count"]),
            "revenue": dec(row["revenue"]),
            "repeat_rate": percent(row["repeat"], row["customer_count"]),
        }
        for row in aggregates
    ]
    counts = {row["segment"]: row["customer_count"] for row in segment_rows}
    order_count = int(ctx.db.scalar(select(func.count(per_order.c.id))) or 0)
    return response(
        "customer-segmentation",
        summary={"segment_counts": counts, "total_segments": len(counts)},
        rows=rows,
        tables={"segments": segment_rows},
        warnings=_warnings(ctx, order_count),
    )


def product_aggregate(ctx: SqlInsightContext):
    orders = order_scope(ctx, successful=True)
    item_by_sku = (
        select(
            func.upper(func.trim(InventoryItem.sku)).label("sku"),
            func.min(InventoryItem.id).label("item_id"),
        )
        .where(func.trim(func.coalesce(InventoryItem.sku, "")) != "")
        .group_by(func.upper(func.trim(InventoryItem.sku)))
        .subquery()
    )
    fallback_item = InventoryItem.__table__.alias("fallback_item")
    direct_item = InventoryItem.__table__.alias("direct_item")
    line_sku = func.upper(func.trim(func.coalesce(OrderItem.sku, "")))
    sku = case((line_sku != "", line_sku), else_=literal("line-") + cast(OrderItem.id, String))
    item_id = func.coalesce(OrderItem.inventory_item_id, item_by_sku.c.item_id)
    item_sku = func.coalesce(direct_item.c.sku, fallback_item.c.sku)
    item_woo_name = func.coalesce(direct_item.c.woo_name, fallback_item.c.woo_name)
    item_description = func.coalesce(direct_item.c.description, fallback_item.c.description)
    item_brand = func.coalesce(direct_item.c.brand, fallback_item.c.brand)
    item_category = func.coalesce(direct_item.c.category, fallback_item.c.category)
    item_barcode = func.coalesce(direct_item.c.barcode, fallback_item.c.barcode)
    item_in_stock = func.coalesce(direct_item.c.in_stock, fallback_item.c.in_stock)
    item_allocated = func.coalesce(direct_item.c.allocated, fallback_item.c.allocated)
    item_sellable = func.coalesce(direct_item.c.sellable, fallback_item.c.sellable)
    item_unit_cost = func.coalesce(direct_item.c.unit_cost, fallback_item.c.unit_cost)
    unit_cost = func.coalesce(OrderItem.unit_cost, item_unit_cost)
    cost_missing = case((unit_cost.is_(None), 1), else_=0)
    statement = (
        select(
            sku.label("sku"),
            func.max(sql_first_nonblank(OrderItem.barcode, item_barcode)).label("barcode"),
            func.max(sql_first_nonblank(OrderItem.name, item_woo_name, item_description, OrderItem.description)).label("product_title"),
            func.max(sql_first_nonblank(OrderItem.brand, item_brand)).label("brand"),
            func.max(item_category).label("category"),
            func.coalesce(func.sum(line_quantity()), 0).label("units_sold"),
            func.count(distinct(OrderItem.order_id)).label("order_count"),
            func.count(distinct(sql_customer_key(orders.c))).label("customer_count"),
            func.coalesce(func.sum(line_revenue()), 0).label("revenue"),
            func.coalesce(func.sum(cost_missing), 0).label("missing_cost_count"),
            func.coalesce(func.sum(func.coalesce(unit_cost, 0) * line_quantity()), 0).label("estimated_cost"),
            func.max(item_in_stock).label("current_in_stock"),
            func.max(item_allocated).label("current_allocated"),
            func.max(item_sellable).label("current_sellable"),
            func.min(orders.c.placed_at).label("first_sold_at"),
            func.max(orders.c.placed_at).label("last_sold_at"),
        )
        .select_from(OrderItem)
        .join(orders, orders.c.id == OrderItem.order_id)
        .outerjoin(item_by_sku, item_by_sku.c.sku == line_sku)
        .outerjoin(direct_item, direct_item.c.id == OrderItem.inventory_item_id)
        .outerjoin(fallback_item, fallback_item.c.id == item_by_sku.c.item_id)
    )
    filters = _line_filter_conditions(ctx)
    if filters:
        # Reuse the ORM table for filter semantics; it resolves to the selected
        # inventory item and never materializes an InventoryItem object.
        statement = statement.outerjoin(InventoryItem, InventoryItem.id == item_id).where(*filters)
    return statement.group_by(sku).subquery()


def format_product_row(row) -> dict[str, Any]:
    cost_available = int(row["missing_cost_count"] or 0) == 0
    revenue = money(row["revenue"])
    cost = money(row["estimated_cost"])
    margin = revenue - cost if cost_available else None
    return {
        "sku": row["sku"],
        "barcode": row["barcode"] or None,
        "product_title": row["product_title"] or None,
        "description": row["product_title"] or None,
        "brand": row["brand"] or None,
        "category": row["category"],
        "units_sold": dec(row["units_sold"]),
        "order_count": int(row["order_count"] or 0),
        "customer_count": int(row["customer_count"] or 0),
        "revenue": dec(revenue),
        "cost_available": cost_available,
        "estimated_cost": dec(cost) if cost_available else None,
        "estimated_margin": dec(margin) if margin is not None else None,
        "margin_percent": percent(margin, revenue) if margin is not None else None,
        "current_in_stock": dec(row["current_in_stock"]) if row["current_in_stock"] is not None else None,
        "current_allocated": dec(row["current_allocated"]) if row["current_allocated"] is not None else None,
        "current_sellable": dec(row["current_sellable"]) if row["current_sellable"] is not None else None,
        "days_of_stock_left": None,
        "last_sold_at": iso(row["last_sold_at"]),
        "first_sold_at": iso(row["first_sold_at"]),
    }


def product_rows(ctx: SqlInsightContext, products, *, order_by=None, offset=None, limit=None) -> list[dict[str, Any]]:
    ordering = order_by if order_by is not None else [products.c.units_sold.desc(), products.c.sku]
    rows = ctx.db.execute(
        select(products)
        .order_by(*ordering)
        .offset(ctx.offset if offset is None else offset)
        .limit(ctx.limit if limit is None else limit)
    ).mappings().all()
    return [format_product_row(row) for row in rows]


def product_summary(ctx: SqlInsightContext, products) -> dict[str, Any]:
    row = ctx.db.execute(
        select(
            func.count(products.c.sku).label("sku_count"),
            func.coalesce(func.sum(products.c.units_sold), 0).label("units_sold"),
            func.coalesce(func.sum(products.c.revenue), 0).label("revenue"),
            func.coalesce(func.sum(products.c.estimated_cost), 0).label("cost"),
            func.coalesce(func.sum(case((products.c.missing_cost_count > 0, 1), else_=0)), 0).label("missing"),
        )
    ).mappings().one()
    cost_available = int(row["missing"] or 0) == 0
    return {
        "sku_count": int(row["sku_count"] or 0),
        "units_sold": dec(row["units_sold"]),
        "revenue": dec(row["revenue"]),
        "estimated_margin": dec(money(row["revenue"]) - money(row["cost"])) if cost_available else None,
        "cost_data_available": cost_available,
    }


def _inventory_filters(ctx: SqlInsightContext) -> list[Any]:
    filters: list[Any] = []
    sku = clean_key(ctx.params.get("sku"))
    brand = clean(ctx.params.get("brand")).lower()
    category = clean(ctx.params.get("category")).lower()
    if sku:
        filters.append(func.upper(func.trim(func.coalesce(InventoryItem.sku, ""))) == sku)
    if brand:
        filters.append(func.lower(func.trim(func.coalesce(InventoryItem.brand, ""))) == brand)
    if category:
        filters.append(func.lower(func.trim(func.coalesce(InventoryItem.category, ""))) == category)
    return filters


def dead_stock_rows(ctx: SqlInsightContext, products) -> list[dict[str, Any]]:
    sku = func.upper(func.trim(func.coalesce(InventoryItem.sku, "")))
    rows = ctx.db.execute(
        select(
            sku.label("sku"),
            sql_first_nonblank(InventoryItem.woo_name, InventoryItem.description).label("product_title"),
            InventoryItem.brand,
            InventoryItem.category,
            InventoryItem.sellable.label("current_sellable"),
        )
        .outerjoin(products, products.c.sku == sku)
        .where(sku != "", products.c.sku.is_(None), *_inventory_filters(ctx))
        .order_by(sku)
        .limit(25)
    ).mappings().all()
    return [
        {
            "sku": row["sku"],
            "product_title": row["product_title"],
            "description": row["product_title"],
            "brand": row["brand"],
            "category": row["category"],
            "units_sold": 0,
            "current_sellable": dec(row["current_sellable"]),
        }
        for row in rows
    ]


def product_sku(ctx: SqlInsightContext) -> InsightResponse:
    products = product_aggregate(ctx)
    costed_products = select(products).where(products.c.missing_cost_count == 0).subquery()
    summary = product_summary(ctx, products)
    main_rows = product_rows(ctx, products)
    top = product_rows(replace(ctx, offset=0), products, offset=0, limit=10)
    summary.update(
        {
            "top_selling_skus": top,
            "slow_moving_skus": product_rows(replace(ctx, offset=0), products, order_by=[products.c.units_sold, products.c.sku], offset=0, limit=10),
            "dead_stock_skus": dead_stock_rows(ctx, products),
            "fast_moving_skus": top,
            "high_revenue_skus": product_rows(replace(ctx, offset=0), products, order_by=[products.c.revenue.desc(), products.c.sku], offset=0, limit=10),
            "high_margin_skus": product_rows(
                replace(ctx, offset=0),
                costed_products,
                order_by=[(costed_products.c.revenue - costed_products.c.estimated_cost).desc(), costed_products.c.sku],
                offset=0,
                limit=10,
            ),
            "high_volume_low_margin_skus": product_rows(
                replace(ctx, offset=0),
                select(products).where(
                    products.c.missing_cost_count == 0,
                    products.c.units_sold >= 5,
                    case((products.c.revenue == 0, 0), else_=(products.c.revenue - products.c.estimated_cost) * 100 / products.c.revenue) < 20,
                ).subquery(),
                offset=0,
                limit=DETAIL_LIMIT,
            ),
        }
    )
    order_count = int(ctx.db.scalar(select(func.count(order_scope(ctx, successful=True).c.id))) or 0)
    warnings = _warnings(ctx, order_count, include_cost=False)
    if not summary["cost_data_available"]:
        warnings += warning("missing_unit_cost", "warning", "Some SKU margin estimates are unavailable because unit cost is missing.")
    per_order = per_order_metrics(ctx, successful=True)
    if ctx.db.scalar(select(per_order.c.id).where(per_order.c.refund_total > 0).limit(1)) is not None:
        warnings += warning("sku_refund_allocation_unavailable", "info", "Order-level refunds cannot be assigned to individual SKUs from order summaries alone.")
    return response("product-sku", summary=summary, rows=main_rows, tables={"skus": main_rows}, warnings=warnings)


def forecast_source(ctx: SqlInsightContext):
    orders = order_scope(ctx, successful=True)
    sku = func.upper(func.trim(func.coalesce(OrderItem.sku, "")))
    now = datetime.now(timezone.utc)
    sales = (
        select(
            sku.label("sku"),
            func.coalesce(func.sum(case((and_(orders.c.placed_at <= now, orders.c.placed_at >= now - timedelta(days=8)), line_quantity()), else_=0)), 0).label("units_7"),
            func.coalesce(func.sum(case((and_(orders.c.placed_at <= now, orders.c.placed_at >= now - timedelta(days=31)), line_quantity()), else_=0)), 0).label("units_30"),
            func.coalesce(func.sum(case((and_(orders.c.placed_at <= now, orders.c.placed_at >= now - timedelta(days=61)), line_quantity()), else_=0)), 0).label("units_60"),
            func.coalesce(func.sum(case((and_(orders.c.placed_at <= now, orders.c.placed_at >= now - timedelta(days=91)), line_quantity()), else_=0)), 0).label("units_90"),
        )
        .select_from(OrderItem)
        .join(orders, orders.c.id == OrderItem.order_id)
        .where(sku != "")
        .group_by(sku)
        .subquery()
    )
    item_sku = func.upper(func.trim(func.coalesce(InventoryItem.sku, "")))
    units_30 = func.coalesce(sales.c.units_30, 0)
    velocity = units_30 / Decimal("30")
    sellable = func.coalesce(InventoryItem.sellable, 0)
    lead = func.coalesce(InventoryItem.default_lead_time_days, 7)
    days_left = case((velocity > 0, sellable / velocity), else_=None)
    suggested = case(
        (velocity > 0, case((((velocity * lead) + func.coalesce(InventoryItem.par_level, 0) - sellable) < 0, 0), else_=(velocity * lead) + func.coalesce(InventoryItem.par_level, 0) - sellable)),
        else_=None,
    )
    risk = case(
        (units_30 <= 0, "insufficient_history"),
        (or_(InventoryItem.under_par.is_(True), days_left < lead), "high"),
        (days_left < lead * 2, "medium"),
        (days_left > 180, "overstock"),
        else_="low",
    )
    return (
        select(
            item_sku.label("sku"),
            sql_first_nonblank(InventoryItem.woo_name, InventoryItem.description).label("product_title"),
            InventoryItem.brand,
            InventoryItem.category,
            sellable.label("current_sellable"),
            func.coalesce(sales.c.units_7, 0).label("units_7"),
            units_30.label("units_30"),
            func.coalesce(sales.c.units_60, 0).label("units_60"),
            func.coalesce(sales.c.units_90, 0).label("units_90"),
            velocity.label("daily_velocity"),
            days_left.label("days_left"),
            lead.label("lead_time"),
            func.coalesce(InventoryItem.par_level, 0).label("par_level"),
            suggested.label("suggested"),
            risk.label("risk"),
            InventoryItem.under_par.label("under_par"),
        )
        .outerjoin(sales, sales.c.sku == item_sku)
        .where(item_sku != "", *_inventory_filters(ctx))
        .subquery()
    )


def format_forecast_row(row) -> dict[str, Any]:
    available = money(row["units_30"]) > 0
    velocity = money(row["daily_velocity"]) if available else None
    return {
        "sku": row["sku"],
        "product_title": row["product_title"],
        "description": row["product_title"],
        "brand": row["brand"],
        "category": row["category"],
        "current_sellable": dec(row["current_sellable"]),
        "units_sold_7d": dec(row["units_7"]),
        "units_sold_30d": dec(row["units_30"]),
        "units_sold_60d": dec(row["units_60"]),
        "units_sold_90d": dec(row["units_90"]),
        "forecast_available": available,
        "forecast_status": "available" if available else "insufficient_history",
        "daily_velocity": dec(velocity) if velocity is not None else None,
        "days_of_stock_left": dec(row["days_left"]) if row["days_left"] is not None else None,
        "lead_time_days": int(row["lead_time"] or 7),
        "par_level": dec(row["par_level"]),
        "suggested_reorder_qty": dec(row["suggested"]) if row["suggested"] is not None else None,
        "risk_level": row["risk"],
        "forecasted_30_day_demand": dec(velocity * Decimal("30")) if velocity is not None else None,
        "forecasted_60_day_demand": dec(velocity * Decimal("60")) if velocity is not None else None,
        "forecasted_90_day_demand": dec(velocity * Decimal("90")) if velocity is not None else None,
        "under_par_risk": bool(row["under_par"]),
    }


def forecast_details(ctx: SqlInsightContext, source=None, *, offset=None, limit=None) -> list[dict[str, Any]]:
    if source is None:
        source = forecast_source(ctx)
    priority = case((source.c.risk == "high", 0), (source.c.risk == "medium", 1), (source.c.risk == "low", 2), (source.c.risk == "overstock", 3), else_=4)
    rows = ctx.db.execute(
        select(source)
        .order_by(priority, source.c.sku)
        .offset(ctx.offset if offset is None else offset)
        .limit(ctx.limit if limit is None else limit)
    ).mappings().all()
    return [format_forecast_row(row) for row in rows]


def forecast_summary(ctx: SqlInsightContext, source) -> dict[str, Any]:
    row = ctx.db.execute(
        select(
            func.count(source.c.sku).label("sku_count"),
            func.coalesce(func.sum(case((source.c.units_30 > 0, 1), else_=0)), 0).label("available"),
            func.coalesce(func.sum(case((source.c.risk == "high", 1), else_=0)), 0).label("stockout"),
            func.coalesce(func.sum(case((source.c.risk == "overstock", 1), else_=0)), 0).label("overstock"),
            func.coalesce(func.sum(source.c.units_30), 0).label("demand30"),
        )
    ).mappings().one()
    sku_count = int(row["sku_count"] or 0)
    available = int(row["available"] or 0)
    status = "available" if sku_count and available == sku_count else ("partial" if available else ("insufficient_history" if sku_count else "unavailable"))
    demand30 = dec(row["demand30"]) if available else None
    return {
        "sku_count": sku_count,
        "forecast_available_count": available,
        "insufficient_history_count": sku_count - available,
        "forecast_status": status,
        "stockout_risk": int(row["stockout"] or 0),
        "overstock_risk": int(row["overstock"] or 0),
        "forecasted_30_day_demand": demand30,
        "forecasted_60_day_demand": round(demand30 * 2, 2) if demand30 is not None else None,
        "forecasted_90_day_demand": round(demand30 * 3, 2) if demand30 is not None else None,
    }


def inventory_forecasting(ctx: SqlInsightContext) -> InsightResponse:
    source = forecast_source(ctx)
    summary = forecast_summary(ctx, source)
    rows = forecast_details(ctx, source)
    order_count = int(ctx.db.scalar(select(func.count(order_scope(ctx, successful=True).c.id))) or 0)
    warnings = _warnings(ctx, order_count)
    if summary["insufficient_history_count"]:
        warnings += warning("insufficient_sales_history", "info", "Forecasts are unavailable for SKUs without usable sales in the last 30 days.")
    return response("inventory-forecasting", summary=summary, rows=rows, tables={"forecast": rows}, warnings=warnings)


def _duplicate_source(ctx: SqlInsightContext):
    orders = order_scope(ctx, successful=False)
    failed = orders.alias("failed")
    success = orders.alias("success")
    failed_status = func.lower(sql_first_nonblank(failed.c.status, failed.c.woo_status, failed.c.local_status))
    success_statuses = [func.lower(func.coalesce(success.c[name], "")) for name in ("status", "woo_status", "local_status")]
    if ctx.dialect == "sqlite":
        within_hour = func.abs(func.julianday(success.c.placed_at) - func.julianday(failed.c.placed_at)) * 86400 <= 3600
    else:
        within_hour = func.abs(func.extract("epoch", success.c.placed_at - failed.c.placed_at)) <= 3600
    candidates = select(
        failed.c.id.label("failed_order_id"),
        success.c.id.label("success_order_id"),
        sql_customer_key(failed.c).label("customer_key"),
        sql_first_nonblank(failed.c.payment_method_title, failed.c.payment_method).label("payment_method"),
        func.row_number().over(partition_by=failed.c.id, order_by=(success.c.placed_at, success.c.id)).label("rn"),
    ).where(
        failed_status.in_(FAILED_STATUSES),
        success.c.id != failed.c.id,
        sql_customer_key(success.c) == sql_customer_key(failed.c),
        not_(or_(*(status.in_(FAILED_STATUSES) for status in success_statuses))),
        failed.c.placed_at.is_not(None),
        success.c.placed_at.is_not(None),
        within_hour,
    ).subquery()
    return select(candidates).where(candidates.c.rn == 1).subquery()


def payment_rows(ctx: SqlInsightContext, per_order=None) -> list[dict[str, Any]]:
    if per_order is None:
        per_order = per_order_metrics(ctx, successful=False)
    method = sql_first_nonblank(per_order.c.payment_method_title, per_order.c.payment_method)
    method = case((method == "", "Unknown"), else_=method)
    primary_status = func.lower(sql_first_nonblank(per_order.c.status, per_order.c.woo_status, per_order.c.local_status))
    duplicates = _duplicate_source(ctx)
    duplicate_counts = select(duplicates.c.payment_method, func.count().label("duplicates")).group_by(duplicates.c.payment_method).subquery()
    grouped = (
        select(
            method.label("payment_method"),
            func.count(per_order.c.id).label("attempts"),
            func.coalesce(func.sum(case((primary_status.in_(FAILED_STATUSES), 0), else_=1)), 0).label("success"),
            func.coalesce(func.sum(case((primary_status.in_(FAILED_STATUSES), 1), else_=0)), 0).label("failed"),
            func.coalesce(func.sum(case((primary_status.in_(FAILED_STATUSES), 0), else_=per_order.c.net)), 0).label("revenue"),
        )
        .group_by(method)
        .subquery()
    )
    rows = ctx.db.execute(
        select(grouped, func.coalesce(duplicate_counts.c.duplicates, 0).label("duplicates"))
        .outerjoin(duplicate_counts, duplicate_counts.c.payment_method == grouped.c.payment_method)
        .order_by(grouped.c.attempts.desc(), grouped.c.payment_method)
        .limit(100)
    ).mappings().all()
    return [
        {
            "payment_method": row["payment_method"],
            "attempt_count": int(row["attempts"]),
            "success_count": int(row["success"]),
            "failed_count": int(row["failed"]),
            "success_rate": percent(row["success"], row["attempts"]),
            "revenue": dec(row["revenue"]),
            "duplicate_pattern_count": int(row["duplicates"]),
        }
        for row in rows
    ]


def duplicate_rows(ctx: SqlInsightContext) -> tuple[list[dict[str, Any]], int]:
    source = _duplicate_source(ctx)
    total = int(ctx.db.scalar(select(func.count()).select_from(source)) or 0)
    rows = ctx.db.execute(
        select(source)
        .order_by(source.c.failed_order_id)
        .offset(ctx.offset)
        .limit(ctx.limit)
    ).mappings().all()
    return [
        {
            "customer_key": row["customer_key"],
            "failed_order_id": row["failed_order_id"],
            "success_order_id": row["success_order_id"],
            "payment_method": row["payment_method"] or "Unknown",
        }
        for row in rows
    ], total


def payment_health(ctx: SqlInsightContext) -> InsightResponse:
    per_order = per_order_metrics(ctx, successful=False)
    rows = payment_rows(ctx, per_order)
    primary_status = func.lower(sql_first_nonblank(per_order.c.status, per_order.c.woo_status, per_order.c.local_status))
    totals = ctx.db.execute(
        select(
            func.count(per_order.c.id).label("attempts"),
            func.coalesce(func.sum(case((primary_status.in_(FAILED_STATUSES), 1), else_=0)), 0).label("failed"),
        )
    ).mappings().one()
    attempts = int(totals["attempts"] or 0)
    failed = int(totals["failed"] or 0)
    duplicates, duplicate_total = duplicate_rows(ctx)
    summary = {
        "orders_by_payment_method": {row["payment_method"]: row["attempt_count"] for row in rows},
        "revenue_by_payment_method": {row["payment_method"]: row["revenue"] for row in rows},
        "failed_orders_by_payment_method": {row["payment_method"]: row["failed_count"] for row in rows},
        "failed_order_rate": percent(failed, attempts),
        "successful_payment_rate": percent(attempts - failed, attempts),
        "duplicate_failed_to_success_patterns": duplicate_total,
    }
    order_count = int(ctx.db.scalar(select(func.count(per_order.c.id))) or 0)
    return response("payment-health", summary=summary, rows=rows, tables={"payment_methods": rows, "duplicate_patterns": duplicates}, warnings=_warnings(ctx, order_count))


def geography(ctx: SqlInsightContext) -> InsightResponse:
    per_order = per_order_metrics(ctx, successful=True)
    city = sql_first_nonblank(per_order.c.shipping_city, per_order.c.billing_city)
    postal = sql_first_nonblank(per_order.c.shipping_zip, per_order.c.billing_zip)
    area_orders = select(
        case((city == "", "Unknown"), else_=city).label("city"),
        case((postal == "", "Unknown"), else_=postal).label("postal"),
        per_order.c.id,
        per_order.c.customer_key,
        per_order.c.net,
        per_order.c.placed_at,
    ).subquery()
    customer_area = select(
        area_orders.c.city,
        area_orders.c.postal,
        area_orders.c.customer_key,
        func.count(area_orders.c.id).label("orders"),
    ).group_by(area_orders.c.city, area_orders.c.postal, area_orders.c.customer_key).subquery()
    customer_stats = select(
        customer_area.c.city,
        customer_area.c.postal,
        func.count(customer_area.c.customer_key).label("customers"),
        func.coalesce(func.sum(case((customer_area.c.orders > 1, 1), else_=0)), 0).label("repeat"),
    ).group_by(customer_area.c.city, customer_area.c.postal).subquery()
    area = (
        select(
            area_orders.c.city,
            area_orders.c.postal.label("postal_code"),
            func.count(area_orders.c.id).label("order_count"),
            func.coalesce(func.sum(area_orders.c.net), 0).label("revenue"),
            func.max(area_orders.c.placed_at).label("last_order_date"),
            customer_stats.c.customers,
            customer_stats.c.repeat,
        )
        .join(customer_stats, and_(customer_stats.c.city == area_orders.c.city, customer_stats.c.postal == area_orders.c.postal))
        .group_by(area_orders.c.city, area_orders.c.postal, customer_stats.c.customers, customer_stats.c.repeat)
        .subquery()
    )
    total = int(ctx.db.scalar(select(func.count()).select_from(area)) or 0)
    rows_raw = ctx.db.execute(
        select(area)
        .order_by(area.c.revenue.desc(), area.c.city, area.c.postal_code)
        .offset(ctx.offset)
        .limit(ctx.limit)
    ).mappings().all()
    rows = [
        {
            "city": row["city"],
            "postal_code": row["postal_code"],
            "order_count": int(row["order_count"]),
            "customer_count": int(row["customers"]),
            "revenue": dec(row["revenue"]),
            "average_order_value": safe_div(row["revenue"], row["order_count"]),
            "repeat_customer_rate": percent(row["repeat"], row["customers"]),
            "last_order_date": iso(row["last_order_date"]),
        }
        for row in rows_raw
    ]
    top_raw = ctx.db.execute(select(area).order_by(area.c.revenue.desc(), area.c.city).limit(5)).mappings().all()
    top = [
        {"city": row["city"], "postal_code": row["postal_code"], "order_count": int(row["order_count"]), "customer_count": int(row["customers"]), "revenue": dec(row["revenue"]), "average_order_value": safe_div(row["revenue"], row["order_count"]), "repeat_customer_rate": percent(row["repeat"], row["customers"]), "last_order_date": iso(row["last_order_date"])}
        for row in top_raw
    ]
    order_count = int(ctx.db.scalar(select(func.count(per_order.c.id))) or 0)
    warnings = _warnings(ctx, order_count)
    if ctx.db.scalar(select(area.c.city).where(area.c.postal_code == "Unknown").limit(1)) is not None:
        warnings += warning("missing_shipping_postal_code", "info", "Some orders are missing shipping postal codes.")
    return response("geography", summary={"area_count": total, "top_areas": top}, rows=rows, tables={"areas": rows}, warnings=warnings)


def coupon_aggregate(ctx: SqlInsightContext):
    per_order = per_order_metrics(ctx, successful=True, include_payload=True)
    if ctx.dialect == "sqlite":
        coupons = func.json_each(per_order.c.raw_woo_payload, "$.coupon_lines").table_valued("key", "value").alias("coupon")
        code = func.trim(func.coalesce(func.json_extract(coupons.c.value, "$.code"), func.json_extract(coupons.c.value, "$.coupon_code"), ""))
        coupon_discount = cast(func.coalesce(func.json_extract(coupons.c.value, "$.discount"), func.json_extract(coupons.c.value, "$.discount_amount"), per_order.c.discount), Numeric(14, 2))
    else:
        coupons = func.json_array_elements(cast(per_order.c.raw_woo_payload, JSON)["coupon_lines"]).table_valued("value").lateral().alias("coupon")
        value = cast(coupons.c.value, JSON)
        code = func.trim(func.coalesce(value["code"].as_string(), value["coupon_code"].as_string(), ""))
        coupon_discount = cast(func.coalesce(value["discount"].as_string(), value["discount_amount"].as_string(), cast(per_order.c.discount, String)), Numeric(14, 2))
    discount = per_order.c.discount if ctx.product_filtered else coupon_discount
    return (
        select(
            code.label("coupon_code"),
            func.count().label("usage_count"),
            func.count(distinct(per_order.c.id)).label("order_count"),
            func.coalesce(func.sum(per_order.c.net), 0).label("revenue"),
            func.coalesce(func.sum(discount), 0).label("discount_amount"),
        )
        .select_from(per_order)
        .join(coupons, true())
        .where(code != "")
        .group_by(code)
        .subquery()
    )


def coupon_rows(ctx: SqlInsightContext, grouped=None) -> list[dict[str, Any]]:
    if grouped is None:
        grouped = coupon_aggregate(ctx)
    rows = ctx.db.execute(
        select(grouped)
        .order_by(grouped.c.usage_count.desc(), grouped.c.coupon_code)
        .offset(ctx.offset)
        .limit(ctx.limit)
    ).mappings().all()
    return [
        {
            "coupon_code": row["coupon_code"],
            "usage_count": int(row["usage_count"]),
            "order_count": int(row["order_count"]),
            "revenue": dec(row["revenue"]),
            "discount_amount": dec(row["discount_amount"]),
            "average_order_value": safe_div(row["revenue"], row["order_count"]),
            "repeat_customer_count": 0,
            "repeat_after_coupon_rate": None,
            "estimated_margin_impact": dec(-money(row["discount_amount"])),
        }
        for row in rows
    ]


def coupons(ctx: SqlInsightContext) -> InsightResponse:
    grouped = coupon_aggregate(ctx)
    rows = coupon_rows(ctx, grouped)
    totals = ctx.db.execute(
        select(
            func.coalesce(func.sum(grouped.c.order_count), 0).label("coupon_orders"),
            func.coalesce(func.sum(grouped.c.usage_count), 0).label("coupon_usage_count"),
            func.coalesce(func.sum(grouped.c.discount_amount), 0).label("discount"),
            func.coalesce(func.sum(grouped.c.revenue), 0).label("revenue"),
        )
    ).mappings().one()
    discount = money(totals["discount"])
    revenue = money(totals["revenue"])
    summary = {
        "coupon_orders": int(totals["coupon_orders"] or 0),
        "coupon_usage_count": int(totals["coupon_usage_count"] or 0),
        "coupon_discount_total": dec(discount),
        "coupon_revenue": dec(revenue),
        "discount_rate": percent(discount, revenue),
        "top_coupons": rows[:10],
    }
    order_count = int(ctx.db.scalar(select(func.count(order_scope(ctx, successful=True).c.id))) or 0)
    missing = [] if rows else warning("missing_coupon_data", "info", "Coupon line snapshots are not synced locally yet.")
    return response("coupons", summary=summary, rows=rows, tables={"coupons": rows}, warnings=_warnings(ctx, order_count) + missing, empty_state=None if rows else "Not enough coupon data yet")


def product_affinity(ctx: SqlInsightContext) -> InsightResponse:
    per_order = per_order_metrics(ctx, successful=True)
    orders = order_scope(ctx, successful=True)
    sku = func.upper(func.trim(func.coalesce(OrderItem.sku, "")))
    line_source = (
        select(
            OrderItem.order_id,
            sku.label("sku"),
            func.max(sql_first_nonblank(OrderItem.description, OrderItem.name)).label("description"),
        )
        .join(orders, orders.c.id == OrderItem.order_id)
        .outerjoin(InventoryItem, InventoryItem.id == OrderItem.inventory_item_id)
        .where(sku != "", *_line_filter_conditions(ctx))
        .group_by(OrderItem.order_id, sku)
        .subquery()
    )
    left = line_source.alias("left_line")
    right = line_source.alias("right_line")
    base_counts = select(left.c.sku, func.count(distinct(left.c.order_id)).label("base_count")).group_by(left.c.sku).subquery()
    pairs = (
        select(
            left.c.sku.label("base_sku"),
            func.max(left.c.description).label("base_description"),
            right.c.sku.label("paired_sku"),
            func.max(right.c.description).label("paired_description"),
            func.count(distinct(left.c.order_id)).label("pair_count"),
            func.coalesce(func.sum(per_order.c.net), 0).label("pair_revenue"),
            base_counts.c.base_count,
        )
        .join(right, and_(right.c.order_id == left.c.order_id, right.c.sku > left.c.sku))
        .join(per_order, per_order.c.id == left.c.order_id)
        .join(base_counts, base_counts.c.sku == left.c.sku)
        .group_by(left.c.sku, right.c.sku, base_counts.c.base_count)
        .subquery()
    )
    rows_raw = ctx.db.execute(
        select(pairs)
        .order_by(pairs.c.pair_count.desc(), pairs.c.base_sku, pairs.c.paired_sku)
        .offset(ctx.offset)
        .limit(ctx.limit)
    ).mappings().all()
    rows = [
        {
            "base_sku": row["base_sku"],
            "base_description": row["base_description"],
            "paired_sku": row["paired_sku"],
            "paired_description": row["paired_description"],
            "pair_order_count": int(row["pair_count"]),
            "attach_rate": percent(row["pair_count"], row["base_count"]),
            "average_order_value_with_pair": safe_div(row["pair_revenue"], row["pair_count"]),
            "suggested_cross_sell_text": f"Customers buying {row['base_sku']} also bought {row['paired_sku']}.",
        }
        for row in rows_raw
    ]
    total = min(int(ctx.db.scalar(select(func.count()).select_from(pairs)) or 0), DETAIL_LIMIT)
    order_count = int(ctx.db.scalar(select(func.count(per_order.c.id))) or 0)
    return response("product-affinity", summary={"pair_count": total, "frequently_bought_together_skus": rows[:10]}, rows=rows, warnings=_warnings(ctx, order_count), empty_state=None if rows else "Not enough multi-line order data yet")


def _reorder_candidates(ctx: SqlInsightContext):
    per_order = per_order_metrics(ctx, successful=True)
    orders = order_scope(ctx, successful=True)
    sku = func.upper(func.trim(func.coalesce(OrderItem.sku, "")))
    events = (
        select(
            per_order.c.customer_key,
            per_order.c.customer_email_key,
            sql_first_nonblank(per_order.c.customer_name, func.trim(func.coalesce(per_order.c.customer_first_name, "") + literal(" ") + func.coalesce(per_order.c.customer_last_name, ""))).label("customer_name"),
            sql_first_nonblank(per_order.c.customer_phone, per_order.c.shipping_phone, per_order.c.billing_phone).label("phone"),
            sku.label("sku"),
            func.max(OrderItem.brand).label("brand"),
            per_order.c.placed_at,
            per_order.c.net,
        )
        .select_from(OrderItem)
        .join(orders, orders.c.id == OrderItem.order_id)
        .join(per_order, per_order.c.id == orders.c.id)
        .outerjoin(InventoryItem, InventoryItem.id == OrderItem.inventory_item_id)
        .where(sku != "", *_line_filter_conditions(ctx))
        .group_by(
            per_order.c.customer_key,
            per_order.c.customer_email_key,
            per_order.c.customer_name,
            per_order.c.customer_first_name,
            per_order.c.customer_last_name,
            per_order.c.customer_phone,
            per_order.c.shipping_phone,
            per_order.c.billing_phone,
            sku,
            per_order.c.placed_at,
            per_order.c.net,
        )
        .subquery()
    )
    pair = (
        select(
            events.c.customer_key,
            func.max(events.c.customer_email_key).label("customer_email"),
            func.max(events.c.customer_name).label("customer_name"),
            func.max(events.c.phone).label("phone"),
            events.c.sku,
            func.max(events.c.brand).label("brand"),
            func.count().label("order_count"),
            func.min(events.c.placed_at).label("first_date"),
            func.max(events.c.placed_at).label("last_date"),
            func.max(events.c.net).label("expected_order_value"),
        )
        .group_by(events.c.customer_key, events.c.sku)
        .having(func.count() >= 2)
        .subquery()
    )
    average_interval = case((pair.c.order_count > 1, _days_between(ctx, pair.c.last_date, pair.c.first_date) / (pair.c.order_count - 1)), else_=1)
    if ctx.dialect == "sqlite":
        expected = func.datetime(pair.c.last_date, func.printf("+%f days", average_interval))
    else:
        # PostgreSQL make_interval(years, months, weeks, days).
        expected = pair.c.last_date + func.make_interval(0, 0, 0, cast(average_interval, Integer))
    days_overdue = _days_between(ctx, datetime.now(timezone.utc), expected)
    risk = case(
        (days_overdue > average_interval * 2, "lost"),
        (days_overdue > 14, "high"),
        (days_overdue > 0, "medium"),
        else_="low",
    )
    ranked = select(
        pair,
        average_interval.label("average_interval"),
        expected.label("expected"),
        days_overdue.label("days_overdue"),
        risk.label("risk"),
        func.row_number().over(partition_by=pair.c.customer_key, order_by=(days_overdue.desc(), pair.c.sku)).label("rn"),
    ).subquery()
    candidates = select(ranked).where(ranked.c.rn == 1).subquery()
    return candidates


def reorder_detail_rows(ctx: SqlInsightContext) -> tuple[list[dict[str, Any]], int]:
    candidates = _reorder_candidates(ctx)
    total = int(ctx.db.scalar(select(func.count()).select_from(candidates)) or 0)
    rows_raw = ctx.db.execute(
        select(candidates)
        .order_by(candidates.c.days_overdue.desc(), candidates.c.customer_key)
        .offset(ctx.offset)
        .limit(ctx.limit)
    ).mappings().all()
    rows = [
        {
            "customer_email": row["customer_email"] or None,
            "customer_name": row["customer_name"] or None,
            "phone": row["phone"] or None,
            "last_order_date": iso(row["last_date"]),
            "most_repeated_sku": row["sku"],
            "most_repeated_brand": row["brand"],
            "most_repeated_category": None,
            "average_reorder_interval_days": dec(row["average_interval"]),
            "expected_next_order_date": iso(parse_sql_datetime(row["expected"])),
            "days_overdue": int(row["days_overdue"] or 0),
            "churn_risk_score": row["risk"],
            "expected_order_value": dec(row["expected_order_value"]),
            "recommended_action": recommended_reorder_action(row["risk"]),
        }
        for row in rows_raw
    ]
    return rows, total


def reorder_forecast(ctx: SqlInsightContext) -> InsightResponse:
    rows, total = reorder_detail_rows(ctx)
    candidates = _reorder_candidates(ctx)
    grouped = dict(
        ctx.db.execute(
            select(candidates.c.risk, func.count()).group_by(candidates.c.risk)
        ).all()
    )
    counts = {risk: int(grouped.get(risk, 0)) for risk in ("low", "medium", "high", "lost")}
    order_count = int(ctx.db.scalar(select(func.count(order_scope(ctx, successful=True).c.id))) or 0)
    return response(
        "reorder-forecast",
        summary={"candidate_count": total, "due_soon": counts["low"], "overdue": counts["medium"] + counts["high"], "lost": counts["lost"]},
        rows=rows,
        warnings=_warnings(ctx, order_count),
        empty_state=None if total else "Not enough repeat purchase history yet",
    )


def _new_returning_months(ctx: SqlInsightContext, per_order) -> list[dict[str, Any]]:
    first_orders = _global_first_orders(ctx)
    period = func.substr(cast(per_order.c.placed_at, String), 1, 7) if ctx.dialect == "sqlite" else func.to_char(per_order.c.placed_at, "YYYY-MM")
    first_period = func.substr(cast(first_orders.c.first_order, String), 1, 7) if ctx.dialect == "sqlite" else func.to_char(first_orders.c.first_order, "YYYY-MM")
    rows = ctx.db.execute(
        select(
            period.label("month"),
            func.count(distinct(case((first_period == period, per_order.c.customer_email_key)))).label("new_customers"),
            func.count(distinct(case((first_period != period, per_order.c.customer_email_key)))).label("returning_customers"),
        )
        .join(first_orders, first_orders.c.email == per_order.c.customer_email_key)
        .where(per_order.c.customer_email_key != "")
        .group_by(period)
        .order_by(period)
        .limit(120)
    ).mappings().all()
    return [{"month": row["month"], "new_customers": int(row["new_customers"]), "returning_customers": int(row["returning_customers"])} for row in rows]


def _top_dimension(ctx: SqlInsightContext, products, field: str) -> list[dict[str, Any]]:
    column = products.c[field]
    value = case((func.trim(func.coalesce(column, "")) == "", "Unknown"), else_=column)
    rows = ctx.db.execute(
        select(value.label(field), func.coalesce(func.sum(products.c.units_sold), 0).label("units_sold"), func.coalesce(func.sum(products.c.revenue), 0).label("revenue"))
        .group_by(value)
        .order_by(desc("revenue"), value)
        .limit(10)
    ).mappings().all()
    return [{field: row[field], "units_sold": dec(row["units_sold"]), "revenue": dec(row["revenue"])} for row in rows]


def overview(ctx: SqlInsightContext) -> InsightResponse:
    summary, per_order = order_summary(ctx, successful=True)
    customers, _ = customer_aggregate(ctx, per_order)
    customer_stats = customer_summary(ctx, customers, per_order)
    products = product_aggregate(ctx)
    top_units = product_rows(replace(ctx, offset=0), products, offset=0, limit=1)
    top_revenue = product_rows(replace(ctx, offset=0), products, order_by=[products.c.revenue.desc(), products.c.sku], offset=0, limit=1)
    inventory_value = ctx.db.scalar(select(func.coalesce(func.sum(func.coalesce(InventoryItem.in_stock, 0) * func.coalesce(InventoryItem.unit_cost, 0)), 0)))
    forecast = forecast_source(ctx)
    forecast_stats = forecast_summary(ctx, forecast)
    reorder, reorder_total = reorder_detail_rows(replace(ctx, offset=0, limit=10))
    summary.update(
        {
            "total_customers": customer_stats["total_customers"],
            "new_customers": customer_stats["new_customers"],
            "returning_customers": customer_stats["returning_customers"],
            "anonymous_orders_without_email": customer_stats["anonymous_orders_without_email"],
            "repeat_customer_rate": customer_stats["repeat_customer_rate"],
            "top_sku_by_units": top_units[0] if top_units else None,
            "top_sku_by_revenue": top_revenue[0] if top_revenue else None,
            "inventory_value": dec(inventory_value),
            "stockout_risk_count": int(ctx.db.scalar(select(func.count()).select_from(forecast).where(forecast.c.risk.in_({"high", "medium"}))) or 0),
            "customers_due_to_reorder": reorder_total,
            "coupon_discount_total": summary["discount_amount"],
        }
    )
    daily = daily_rows(ctx, per_order)
    trends = {
        "daily_revenue": daily,
        "revenue_by_day": daily,
        "orders_by_day": [{"date": row["date"], "order_count": row["order_count"]} for row in daily],
        "new_vs_returning_by_month": _new_returning_months(ctx, per_order),
        "top_brands": _top_dimension(ctx, products, "brand"),
        "top_categories": _top_dimension(ctx, products, "category"),
        "top_skus": product_rows(replace(ctx, offset=0), products, offset=0, limit=10),
    }
    warnings = _warnings(ctx, summary["total_orders"]) + refund_warnings(ctx, summary)
    return response(
        "overview",
        summary=summary,
        trends=trends,
        tables={"stockout_risk": forecast_details(replace(ctx, offset=0), forecast, offset=0, limit=10), "reorder_risk": reorder[:10]},
        warnings=warnings,
        empty_state=None if summary["total_orders"] else "No matching completed or active sales orders",
    )


def subscriptions(ctx: SqlInsightContext) -> InsightResponse:
    data = build_subscription_data(ctx.db)
    email = clean(ctx.params.get("customer_email")).casefold()
    sku = clean(ctx.params.get("sku")).casefold()
    rows = [
        row
        for row in data["subscription_rows"]
        if (not email or email in str(row.get("email") or "").casefold())
        and (not sku or sku in str(row.get("sku") or "").casefold())
    ]
    rows = rows[ctx.offset : ctx.offset + ctx.limit]
    summary = data["summary"]
    return response(
        "subscriptions",
        summary={
            "data_available": data["available"],
            "active_subscriptions": summary["active_subscriptions_count"],
            "subscription_revenue": None,
            "monthly_recurring_revenue": None,
            "failed_renewals": None,
            "upcoming_renewals_7_days": summary["upcoming_7_days_count"],
            "upcoming_renewals_30_days": summary["upcoming_30_days_count"],
            "upcoming_30_day_units": summary["upcoming_30_day_units"],
            "last_synced_at": summary["last_synced_at"],
        },
        rows=rows,
        warnings=data["warnings"],
        empty_state=None if rows else "No active subscriptions match this scope." if data["available"] else "No subscription data synced yet",
    )


def subscription_products(ctx: SqlInsightContext) -> InsightResponse:
    data = build_subscription_data(ctx.db)
    sku = clean(ctx.params.get("sku")).casefold()
    brand = clean(ctx.params.get("brand")).casefold()
    category = clean(ctx.params.get("category")).casefold()
    rows = [
        row
        for row in data["product_rows"]
        if (not sku or sku in str(row.get("sku") or "").casefold())
        and (not brand or brand == str(row.get("brand") or "").casefold())
        and (not category or category == str(row.get("category") or "").casefold())
    ]
    total = len(rows)
    units = sum((Decimal(str(row["total_units_per_renewal"])) for row in rows), Decimal("0"))
    at_risk = sum(1 for row in rows if row["stockout_risk"] == "At risk")
    rows = rows[ctx.offset : ctx.offset + ctx.limit]
    return response(
        "subscription-products",
        summary={
            "data_available": data["available"],
            "products_on_subscription_count": total if data["available"] else None,
            "active_subscription_products": total if data["available"] else None,
            "units_per_renewal": (float(units) if units % 1 else int(units)) if data["available"] else None,
            "stockout_risk_for_subscription_products": at_risk if data["available"] else None,
            "at_risk_products": at_risk if data["available"] else None,
            "last_synced_at": data["summary"]["last_synced_at"],
        },
        rows=rows,
        warnings=data["warnings"],
        empty_state=None if rows else "No subscription products match this scope." if data["available"] else "No subscription data synced yet",
    )


def response(dashboard: str, summary=None, metrics=None, trends=None, rows=None, tables=None, warnings=None, empty_state=None) -> InsightResponse:
    return InsightResponse(
        generated_at=datetime.now(timezone.utc),
        dashboard=dashboard,
        summary=summary or {},
        metrics=metrics or {},
        trends=trends or {},
        rows=rows or [],
        tables=tables or {},
        data_quality=warnings or [],
        empty_state=empty_state,
    )


def warning(code: str, severity: str, message: str) -> list[dict[str, str]]:
    return [{"code": code, "severity": severity, "message": message}]


def summary_changes(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, float | None]:
    changes = {}
    for key, value in current.items():
        old = previous.get(key)
        if isinstance(value, Number) and not isinstance(value, bool) and isinstance(old, Number) and not isinstance(old, bool):
            changes[key] = None if old == 0 else round((float(value) - float(old)) * 100 / abs(float(old)), 1)
    return changes


def recommended_reorder_action(risk: str) -> str:
    return {"low": "send reminder", "medium": "send reminder", "high": "offer reorder discount", "lost": "check subscription opportunity"}.get(risk, "send reminder")


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


def parse_sql_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace(" ", "T"))


def normalized_email(value: Any) -> str:
    return clean(value).lower()


def clean_key(value: Any) -> str:
    return clean(value).upper()


def clean(value: Any) -> str:
    return str(value or "").strip()


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


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def iso_date(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
