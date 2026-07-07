from datetime import datetime

from pydantic import BaseModel


class InventoryHealthCards(BaseModel):
    total_items: int = 0
    active_items: int = 0
    total_inventory_value: float = 0
    low_stock_count: int = 0
    under_par_count: int = 0
    negative_sellable_count: int = 0
    allocated_greater_than_stock_count: int = 0
    missing_sku_count: int = 0
    missing_default_location_count: int = 0
    missing_unit_cost_count: int = 0
    missing_sales_price_count: int = 0
    woo_synced_items_count: int = 0
    woo_unmatched_items_count: int = 0


class OrderOperationsCards(BaseModel):
    open_orders_count: int = 0
    orders_with_unmatched_lines_count: int = 0
    allocated_orders_count: int = 0
    partially_allocated_orders_count: int = 0
    picked_orders_count: int = 0
    partially_picked_orders_count: int = 0
    fulfilled_orders_count: int = 0
    partially_fulfilled_orders_count: int = 0
    completed_orders_count: int = 0
    orders_needing_attention_count: int = 0


class RouteCards(BaseModel):
    route_candidates_count: int = 0
    draft_routes_count: int = 0
    finalized_routes_count: int = 0
    in_progress_routes_count: int = 0
    completed_routes_count: int = 0
    cancelled_routes_count: int = 0


class DashboardActivityItem(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str | None = None
    created_at: datetime | None = None
    entity_type: str
    entity_id: int
    severity: str = "info"


class DashboardWarningSample(BaseModel):
    id: int
    label: str
    detail: str | None = None


class DashboardWarningGroup(BaseModel):
    code: str
    severity: str
    title: str
    count: int
    description: str
    link_target: str | None = None
    sample_records: list[DashboardWarningSample] = []


class DashboardResponse(BaseModel):
    generated_at: datetime
    inventory_health: InventoryHealthCards
    order_operations: OrderOperationsCards
    routes: RouteCards
    warnings: list[DashboardWarningGroup] = []
    activity: list[DashboardActivityItem] = []
