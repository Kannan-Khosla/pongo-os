from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.allocations import Allocation
from app.models.cycle_counts import CycleCount
from app.models.fulfillments import Fulfillment
from app.models.imports import ImportJob
from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryTransfer, MovementType, StockAdjustment, StockMovement
from app.models.orders import Order, OrderItem
from app.models.picks import Pick
from app.models.receipts import Receipt
from app.models.routes import Route, RouteStop
from app.models.woocommerce import WooCommerceSyncError
from app.schemas.dashboard import (
    DashboardActivityItem,
    DashboardResponse,
    DashboardWarningGroup,
    DashboardWarningSample,
    InventoryHealthCards,
    OrderOperationsCards,
    RouteCards,
)
from app.services.routes import ROUTE_ELIGIBLE_STATUSES


def build_dashboard(db: Session, activity_limit: int = 25) -> DashboardResponse:
    activity_limit = max(1, min(activity_limit, 100))
    return DashboardResponse(
        generated_at=datetime.now(timezone.utc),
        inventory_health=build_inventory_health(db),
        order_operations=build_order_operations(db),
        routes=build_route_cards(db),
        warnings=build_warnings(db),
        activity=build_activity(db, activity_limit),
    )


def build_inventory_health(db: Session) -> InventoryHealthCards:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    missing_sku = func.trim(func.coalesce(InventoryItem.sku, "")) == ""
    selected_location = case(
        (
            and_(InventoryItem.default_location.is_not(None), InventoryItem.default_location != ""),
            InventoryItem.default_location,
        ),
        else_=InventoryItem.inventory_location,
    )
    missing_location = func.trim(func.coalesce(selected_location, "")) == ""
    values = db.execute(
        select(
            func.count(InventoryItem.id).label("total_items"),
            _count_when(InventoryItem.active.is_(True)).label("active_items"),
            func.coalesce(
                func.sum(func.coalesce(InventoryItem.in_stock, 0) * func.coalesce(InventoryItem.unit_cost, 0)),
                0,
            ).label("total_inventory_value"),
            _count_when(func.coalesce(InventoryItem.in_stock, 0) <= 0).label("low_stock_count"),
            _count_when(and_(InventoryItem.reorder.is_(True), InventoryItem.under_par.is_(True))).label("reorder_count"),
            _count_when(InventoryItem.under_par.is_(True)).label("under_par_count"),
            _count_when(func.coalesce(InventoryItem.sellable, 0) < 0).label("negative_sellable_count"),
            _count_when(func.coalesce(InventoryItem.allocated, 0) > func.coalesce(InventoryItem.in_stock, 0)).label(
                "allocated_greater_than_stock_count"
            ),
            _count_when(missing_sku).label("missing_sku_count"),
            _count_when(missing_location).label("missing_default_location_count"),
            _count_when(InventoryItem.unit_cost.is_(None)).label("missing_unit_cost_count"),
            _count_when(InventoryItem.sales_price.is_(None)).label("missing_sales_price_count"),
            _count_when(InventoryItem.woo_product_id.is_not(None)).label("woo_synced_items_count"),
            _count_when(InventoryItem.woo_sync_status.in_({"unmatched", "conflict", "error"})).label("woo_unmatched_items_count"),
        )
    ).mappings().one()
    damage_loss_value = db.scalar(
        select(
            func.coalesce(
                func.sum(func.coalesce(StockMovement.quantity_change, 0) * func.coalesce(StockMovement.unit_cost, 0)),
                0,
            )
        ).where(
            StockMovement.created_at >= month_start,
            StockMovement.movement_type.in_({MovementType.damage, MovementType.loss}),
        )
    )
    return InventoryHealthCards(
        total_items=values["total_items"],
        active_items=values["active_items"],
        total_inventory_value=decimal_to_float(values["total_inventory_value"]),
        low_stock_count=values["low_stock_count"],
        reorder_count=values["reorder_count"],
        under_par_count=values["under_par_count"],
        negative_sellable_count=values["negative_sellable_count"],
        allocated_greater_than_stock_count=values["allocated_greater_than_stock_count"],
        missing_sku_count=values["missing_sku_count"],
        missing_default_location_count=values["missing_default_location_count"],
        missing_unit_cost_count=values["missing_unit_cost_count"],
        missing_sales_price_count=values["missing_sales_price_count"],
        woo_synced_items_count=values["woo_synced_items_count"],
        woo_unmatched_items_count=values["woo_unmatched_items_count"],
        damage_loss_value_this_month=decimal_to_float(damage_loss_value),
        transfers_this_week=db.scalar(select(func.count(InventoryTransfer.id)).where(InventoryTransfer.created_at >= week_start)) or 0,
        receiving_this_week=db.scalar(select(func.count(Receipt.id)).where(Receipt.created_at >= week_start)) or 0,
        adjustment_count_this_week=db.scalar(select(func.count(StockAdjustment.id)).where(StockAdjustment.created_at >= week_start)) or 0,
    )


def build_order_operations(db: Session) -> OrderOperationsCards:
    unmatched_line = _order_line_exists(OrderItem.matched_status.in_({"unmatched", "conflict"}))
    attention_line = _order_line_exists(
        or_(
            OrderItem.matched_status.in_({"unmatched", "conflict"}),
            func.coalesce(OrderItem.sellable_snapshot, 0) < 0,
            _impossible_line_condition(),
        )
    )
    values = db.execute(
        select(
            _count_when(func.coalesce(func.nullif(Order.local_status, ""), "open") == "open").label("open_orders_count"),
            _count_when(unmatched_line).label("orders_with_unmatched_lines_count"),
            _count_when(Order.local_status == "allocated").label("allocated_orders_count"),
            _count_when(Order.local_status == "partially_allocated").label("partially_allocated_orders_count"),
            _count_when(Order.local_status == "picked").label("picked_orders_count"),
            _count_when(Order.local_status == "partially_picked").label("partially_picked_orders_count"),
            _count_when(Order.local_status == "fulfilled").label("fulfilled_orders_count"),
            _count_when(Order.local_status == "partially_fulfilled").label("partially_fulfilled_orders_count"),
            _count_when(Order.local_status.in_({"fulfilled", "partially_fulfilled"})).label("completed_orders_count"),
            _count_when(attention_line).label("orders_needing_attention_count"),
        ).where(Order.is_historical_snapshot.is_(False))
    ).mappings().one()
    return OrderOperationsCards(
        **values,
    )


def build_route_cards(db: Session) -> RouteCards:
    active_route = exists(
        select(RouteStop.id)
        .join(Route, Route.id == RouteStop.route_id)
        .where(
            RouteStop.order_id == Order.id,
            or_(Route.status.is_(None), Route.status != "cancelled"),
        )
    )
    route_candidates_count = db.scalar(
        select(func.count(Order.id)).where(
            Order.is_historical_snapshot.is_(False),
            Order.local_status.in_(ROUTE_ELIGIBLE_STATUSES),
            ~active_route,
        )
    ) or 0
    route_values = db.execute(
        select(
            _count_when(Route.status == "draft").label("draft_routes_count"),
            _count_when(Route.status == "finalized").label("finalized_routes_count"),
            _count_when(Route.status == "in_progress").label("in_progress_routes_count"),
            _count_when(Route.status == "completed").label("completed_routes_count"),
            _count_when(Route.status == "cancelled").label("cancelled_routes_count"),
        )
    ).mappings().one()
    return RouteCards(
        route_candidates_count=route_candidates_count,
        **route_values,
    )


def build_warnings(db: Session) -> list[DashboardWarningGroup]:
    selected_location = case(
        (
            and_(InventoryItem.default_location.is_not(None), InventoryItem.default_location != ""),
            InventoryItem.default_location,
        ),
        else_=InventoryItem.inventory_location,
    )
    item_warning_specs = [
        ("items_missing_sku", "error", "Items missing SKU", func.trim(func.coalesce(InventoryItem.sku, "")) == "", "Items without SKUs cannot be matched reliably."),
        ("items_negative_sellable", "error", "Items with negative sellable", func.coalesce(InventoryItem.sellable, 0) < 0, "Sellable below zero usually means allocation exceeds stock."),
        ("items_allocated_gt_stock", "error", "Items allocated greater than stock", func.coalesce(InventoryItem.allocated, 0) > func.coalesce(InventoryItem.in_stock, 0), "Allocated quantity should not exceed local stock."),
        ("items_under_par", "warning", "Items under par", InventoryItem.under_par.is_(True), "Items at or below par level may need review."),
        ("items_missing_default_location", "warning", "Items missing default location", func.trim(func.coalesce(selected_location, "")) == "", "Missing locations slow receiving, counts, and picking."),
        ("items_missing_unit_cost", "warning", "Items missing unit cost", InventoryItem.unit_cost.is_(None), "Missing costs reduce report accuracy."),
        ("items_missing_sales_price", "info", "Items missing sales price", InventoryItem.sales_price.is_(None), "Missing sales prices reduce margin reporting."),
    ]
    groups = [
        warning_group_from_query(db, code, severity, title, condition, description, "#/items", InventoryItem, item_sample)
        for code, severity, title, condition, description in item_warning_specs
    ]
    order_warning_specs = [
        (
            "orders_unmatched_lines",
            "error",
            "Orders with unmatched lines",
            _order_line_exists(OrderItem.matched_status.in_({"unmatched", "conflict"})),
            "Unmatched lines cannot be allocated or picked cleanly.",
        ),
        (
            "orders_impossible_quantities",
            "error",
            "Orders with impossible quantities",
            _order_line_exists(_impossible_line_condition()),
            "Picked, allocated, or fulfilled quantities exceed expected limits.",
        ),
    ]
    groups.extend(
        warning_group_from_query(
            db,
            code,
            severity,
            title,
            and_(Order.is_historical_snapshot.is_(False), condition),
            description,
            "#/orders",
            Order,
            order_sample,
        )
        for code, severity, title, condition, description in order_warning_specs
    )
    recent_sync_errors = list(db.scalars(select(WooCommerceSyncError).order_by(WooCommerceSyncError.created_at.desc()).limit(20)).all())
    failed_imports = list(db.scalars(select(ImportJob).where(ImportJob.failed_rows > 0).order_by(ImportJob.created_at.desc()).limit(20)).all())
    groups.append(warning_group("woo_sync_errors", "warning", "Recent Woo sync errors", recent_sync_errors, "Recent read-only sync runs produced row-level errors.", "#/settings", sync_error_sample))
    groups.append(warning_group("import_failed_rows", "warning", "Import jobs with failed rows", failed_imports, "Some CSV imports have rows that need correction.", "#/items", import_job_sample))
    return [group for group in groups if group.count > 0]


def build_activity(db: Session, limit: int) -> list[DashboardActivityItem]:
    rows: list[DashboardActivityItem] = []
    rows.extend(activity_from_stock(row) for row in db.scalars(select(StockMovement).order_by(StockMovement.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_audit(row) for row in db.scalars(select(InventoryAuditEvent).order_by(InventoryAuditEvent.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_receipt(row) for row in db.scalars(select(Receipt).order_by(Receipt.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_cycle(row) for row in db.scalars(select(CycleCount).order_by(CycleCount.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_allocation(row) for row in db.scalars(select(Allocation).order_by(Allocation.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_pick(row) for row in db.scalars(select(Pick).order_by(Pick.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_fulfillment(row) for row in db.scalars(select(Fulfillment).order_by(Fulfillment.created_at.desc()).limit(limit)).all())
    rows.extend(activity_from_route(row) for row in db.scalars(select(Route).order_by(Route.created_at.desc()).limit(limit)).all())
    return sorted(rows, key=lambda row: row.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:limit]


def order_needs_attention(order: Order) -> bool:
    return any(line.matched_status in {"unmatched", "conflict"} or (line.sellable_snapshot or Decimal("0")) < 0 or line_has_impossible_quantity(line) for line in order.items)


def line_has_impossible_quantity(line: OrderItem) -> bool:
    ordered = line.quantity_ordered or Decimal("0")
    allocated = line.quantity_allocated or Decimal("0")
    picked = line.quantity_picked or Decimal("0")
    fulfilled = line.quantity_fulfilled or Decimal("0")
    return allocated > ordered or picked > allocated or picked > ordered or fulfilled > picked or fulfilled > ordered


def warning_group(code: str, severity: str, title: str, records: list, description: str, link_target: str, sample_builder) -> DashboardWarningGroup:
    return DashboardWarningGroup(
        code=code,
        severity=severity,
        title=title,
        count=len(records),
        description=description,
        link_target=link_target,
        sample_records=[sample_builder(record) for record in records[:5]],
    )


def warning_group_from_query(
    db: Session,
    code: str,
    severity: str,
    title: str,
    condition,
    description: str,
    link_target: str,
    model,
    sample_builder,
) -> DashboardWarningGroup:
    count = db.scalar(select(func.count(model.id)).where(condition)) or 0
    samples = list(db.scalars(select(model).where(condition).order_by(model.id.asc()).limit(5)).all()) if count else []
    return DashboardWarningGroup(
        code=code,
        severity=severity,
        title=title,
        count=count,
        description=description,
        link_target=link_target,
        sample_records=[sample_builder(record) for record in samples],
    )


def _count_when(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _order_line_exists(condition):
    return exists(select(OrderItem.id).where(OrderItem.order_id == Order.id, condition))


def _impossible_line_condition():
    ordered = func.coalesce(OrderItem.quantity_ordered, 0)
    allocated = func.coalesce(OrderItem.quantity_allocated, 0)
    picked = func.coalesce(OrderItem.quantity_picked, 0)
    fulfilled = func.coalesce(OrderItem.quantity_fulfilled, 0)
    return or_(allocated > ordered, picked > allocated, picked > ordered, fulfilled > picked, fulfilled > ordered)


def item_sample(item: InventoryItem) -> DashboardWarningSample:
    return DashboardWarningSample(id=item.id, label=item.sku or f"Item {item.id}", detail=item.description)


def order_sample(order: Order) -> DashboardWarningSample:
    return DashboardWarningSample(id=order.id, label=order.woo_order_number or order.order_number or f"Order {order.id}", detail=order.customer_name)


def sync_error_sample(error: WooCommerceSyncError) -> DashboardWarningSample:
    return DashboardWarningSample(id=error.id, label=error.sku or error.barcode or f"Sync error {error.id}", detail=error.error_message)


def import_job_sample(job: ImportJob) -> DashboardWarningSample:
    return DashboardWarningSample(id=job.id, label=job.file_name or f"Import {job.id}", detail=f"{job.failed_rows} failed row(s)")


def activity_from_stock(row: StockMovement) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"stock-{row.id}", type="stock_movement", title=f"Stock movement: {row.movement_type.value}", subtitle=row.sku or row.reference_number, created_at=row.created_at, entity_type="stock_movement", entity_id=row.id, severity="info")


def activity_from_audit(row: InventoryAuditEvent) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"audit-{row.id}", type="audit_event", title=f"Audit: {row.event_type}", subtitle=row.sku or row.reference_number, created_at=row.created_at, entity_type="audit_event", entity_id=row.id, severity="info")


def activity_from_receipt(row: Receipt) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"receipt-{row.id}", type="receipt", title=f"Receipt {row.receipt_number}", subtitle=row.warehouse, created_at=row.created_at, entity_type="receipt", entity_id=row.id, severity="success")


def activity_from_cycle(row: CycleCount) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"cycle-{row.id}", type="cycle_count", title=f"Cycle count {row.count_number}", subtitle=row.warehouse, created_at=row.created_at, entity_type="cycle_count", entity_id=row.id, severity="info")


def activity_from_allocation(row: Allocation) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"allocation-{row.id}", type="allocation", title=f"Allocation {row.allocation_number}", subtitle=row.woo_order_number, created_at=row.created_at, entity_type="allocation", entity_id=row.id, severity="success")


def activity_from_pick(row: Pick) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"pick-{row.id}", type="pick", title=f"Pick {row.pick_number}", subtitle=row.woo_order_number, created_at=row.created_at, entity_type="pick", entity_id=row.id, severity="success")


def activity_from_fulfillment(row: Fulfillment) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"fulfillment-{row.id}", type="fulfillment", title=f"Fulfillment {row.fulfillment_number}", subtitle=row.woo_order_number, created_at=row.created_at, entity_type="fulfillment", entity_id=row.id, severity="success")


def activity_from_route(row: Route) -> DashboardActivityItem:
    return DashboardActivityItem(id=f"route-{row.id}", type="route", title=f"Route {row.route_number}", subtitle=row.route_name, created_at=row.created_at, entity_type="route", entity_id=row.id, severity="info")


def clean(value: str | None) -> str:
    return (value or "").strip()


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)
