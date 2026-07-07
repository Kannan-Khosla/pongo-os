from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.allocations import Allocation
from app.models.cycle_counts import CycleCount
from app.models.fulfillments import Fulfillment
from app.models.imports import ImportJob
from app.models.inventory import InventoryAuditEvent, InventoryItem, StockMovement
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
from app.services.routes import ROUTE_ELIGIBLE_STATUSES, order_has_active_route


def build_dashboard(db: Session, activity_limit: int = 25) -> DashboardResponse:
    activity_limit = max(1, min(activity_limit, 100))
    items = list(db.scalars(select(InventoryItem)).all())
    orders = list(db.scalars(select(Order).options(selectinload(Order.items), selectinload(Order.route_stops).selectinload(RouteStop.route))).all())
    routes = list(db.scalars(select(Route).options(selectinload(Route.stops))).all())
    warnings = build_warnings(db, items, orders)
    return DashboardResponse(
        generated_at=datetime.now(timezone.utc),
        inventory_health=build_inventory_health(items),
        order_operations=build_order_operations(orders),
        routes=build_route_cards(orders, routes),
        warnings=warnings,
        activity=build_activity(db, activity_limit),
    )


def build_inventory_health(items: list[InventoryItem]) -> InventoryHealthCards:
    return InventoryHealthCards(
        total_items=len(items),
        active_items=sum(1 for item in items if item.active),
        total_inventory_value=decimal_to_float(sum(((item.in_stock or Decimal("0")) * (item.unit_cost or Decimal("0")) for item in items), Decimal("0"))),
        low_stock_count=sum(1 for item in items if (item.in_stock or Decimal("0")) <= 0),
        under_par_count=sum(1 for item in items if item.under_par),
        negative_sellable_count=sum(1 for item in items if (item.sellable or Decimal("0")) < 0),
        allocated_greater_than_stock_count=sum(1 for item in items if (item.allocated or Decimal("0")) > (item.in_stock or Decimal("0"))),
        missing_sku_count=sum(1 for item in items if not clean(item.sku)),
        missing_default_location_count=sum(1 for item in items if not clean(item.default_location or item.inventory_location)),
        missing_unit_cost_count=sum(1 for item in items if item.unit_cost is None),
        missing_sales_price_count=sum(1 for item in items if item.sales_price is None),
        woo_synced_items_count=sum(1 for item in items if item.woo_product_id is not None),
        woo_unmatched_items_count=sum(1 for item in items if item.woo_sync_status in {"unmatched", "conflict", "error"}),
    )


def build_order_operations(orders: list[Order]) -> OrderOperationsCards:
    attention_ids = {order.id for order in orders if order_needs_attention(order)}
    return OrderOperationsCards(
        open_orders_count=sum(1 for order in orders if (order.local_status or "open") == "open"),
        orders_with_unmatched_lines_count=sum(1 for order in orders if any(line.matched_status in {"unmatched", "conflict"} for line in order.items)),
        allocated_orders_count=sum(1 for order in orders if order.local_status == "allocated"),
        partially_allocated_orders_count=sum(1 for order in orders if order.local_status == "partially_allocated"),
        picked_orders_count=sum(1 for order in orders if order.local_status == "picked"),
        partially_picked_orders_count=sum(1 for order in orders if order.local_status == "partially_picked"),
        fulfilled_orders_count=sum(1 for order in orders if order.local_status == "fulfilled"),
        partially_fulfilled_orders_count=sum(1 for order in orders if order.local_status == "partially_fulfilled"),
        completed_orders_count=sum(1 for order in orders if order.local_status in {"fulfilled", "partially_fulfilled"}),
        orders_needing_attention_count=len(attention_ids),
    )


def build_route_cards(orders: list[Order], routes: list[Route]) -> RouteCards:
    route_candidates = [order for order in orders if order.local_status in ROUTE_ELIGIBLE_STATUSES and not order_has_active_route(order)]
    return RouteCards(
        route_candidates_count=len(route_candidates),
        draft_routes_count=sum(1 for route in routes if route.status == "draft"),
        finalized_routes_count=sum(1 for route in routes if route.status == "finalized"),
        in_progress_routes_count=sum(1 for route in routes if route.status == "in_progress"),
        completed_routes_count=sum(1 for route in routes if route.status == "completed"),
        cancelled_routes_count=sum(1 for route in routes if route.status == "cancelled"),
    )


def build_warnings(db: Session, items: list[InventoryItem], orders: list[Order]) -> list[DashboardWarningGroup]:
    groups = [
        warning_group("items_missing_sku", "error", "Items missing SKU", [item for item in items if not clean(item.sku)], "Items without SKUs cannot be matched reliably.", "#/items", item_sample),
        warning_group("items_negative_sellable", "error", "Items with negative sellable", [item for item in items if (item.sellable or Decimal("0")) < 0], "Sellable below zero usually means allocation exceeds stock.", "#/items", item_sample),
        warning_group("items_allocated_gt_stock", "error", "Items allocated greater than stock", [item for item in items if (item.allocated or Decimal("0")) > (item.in_stock or Decimal("0"))], "Allocated quantity should not exceed local stock.", "#/items", item_sample),
        warning_group("items_under_par", "warning", "Items under par", [item for item in items if item.under_par], "Items at or below par level may need review.", "#/items", item_sample),
        warning_group("items_missing_default_location", "warning", "Items missing default location", [item for item in items if not clean(item.default_location or item.inventory_location)], "Missing locations slow receiving, counts, and picking.", "#/items", item_sample),
        warning_group("items_missing_unit_cost", "warning", "Items missing unit cost", [item for item in items if item.unit_cost is None], "Missing costs reduce report accuracy.", "#/items", item_sample),
        warning_group("items_missing_sales_price", "info", "Items missing sales price", [item for item in items if item.sales_price is None], "Missing sales prices reduce margin reporting.", "#/items", item_sample),
        warning_group("orders_unmatched_lines", "error", "Orders with unmatched lines", [order for order in orders if any(line.matched_status in {"unmatched", "conflict"} for line in order.items)], "Unmatched lines cannot be allocated or picked cleanly.", "#/orders", order_sample),
        warning_group("orders_impossible_quantities", "error", "Orders with impossible quantities", [order for order in orders if any(line_has_impossible_quantity(line) for line in order.items)], "Picked, allocated, or fulfilled quantities exceed expected limits.", "#/orders", order_sample),
    ]
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
