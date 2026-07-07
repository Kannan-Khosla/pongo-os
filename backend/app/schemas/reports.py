from datetime import datetime

from pydantic import BaseModel


class ReceivedInventoryReportRow(BaseModel):
    receipt_id: int
    receipt_number: str
    receipt_type: str | None = None
    status: str | None = None
    received_at: datetime | None = None
    created_at: datetime
    warehouse: str | None = None
    inventory_location: str | None = None
    default_location: str | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    quantity_received: float
    unit_cost: float
    total_received_value: float
    reference_number: str | None = None
    created_by: str | None = None
    line_notes: str | None = None
    receipt_notes: str | None = None


class ReceivedInventoryWarehouseSummary(BaseModel):
    warehouse: str
    total_lines: int
    total_quantity_received: float
    total_received_value: float


class ReceivedInventoryLocationSummary(BaseModel):
    warehouse: str
    inventory_location: str
    total_lines: int
    total_quantity_received: float
    total_received_value: float


class ReceivedInventorySkuSummary(BaseModel):
    sku: str
    barcode: str | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    total_quantity_received: float
    total_received_value: float
    receipt_count: int


class ReceivedInventorySummaryResponse(BaseModel):
    total_receipts: int
    total_lines: int
    total_quantity_received: float
    total_received_value: float
    unique_skus: int
    unique_locations: int
    date_from: str | None = None
    date_to: str | None = None
    by_warehouse: list[ReceivedInventoryWarehouseSummary]
    by_location: list[ReceivedInventoryLocationSummary]
    by_sku: list[ReceivedInventorySkuSummary]


class FulfillmentReportRow(BaseModel):
    fulfillment_id: int
    fulfillment_number: str
    status: str
    posted_at: datetime | None = None
    created_at: datetime
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_picked: float
    quantity_fulfilled: float
    quantity_previously_fulfilled: float
    remaining_to_fulfill: float
    unit_cost: float
    fulfilled_value: float
    in_stock_before: float
    allocated_before: float
    sellable_before: float
    in_stock_after: float
    allocated_after: float
    sellable_after: float
    created_by: str | None = None
    line_notes: str | None = None
    fulfillment_notes: str | None = None


class FulfillmentWarehouseSummary(BaseModel):
    warehouse: str
    total_lines: int
    total_quantity_fulfilled: float
    total_fulfilled_value: float


class FulfillmentLocationSummary(BaseModel):
    warehouse: str
    inventory_location: str
    total_lines: int
    total_quantity_fulfilled: float
    total_fulfilled_value: float


class FulfillmentSkuSummary(BaseModel):
    sku: str
    barcode: str | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    total_quantity_fulfilled: float
    total_fulfilled_value: float
    fulfillment_count: int
    order_count: int


class FulfillmentOrderSummary(BaseModel):
    woo_order_number: str | None = None
    woo_order_id: int | None = None
    customer_email: str | None = None
    local_status: str | None = None
    total_lines: int
    total_quantity_fulfilled: float
    total_fulfilled_value: float


class FulfillmentSummaryResponse(BaseModel):
    total_fulfillments: int
    total_orders: int
    total_lines: int
    total_quantity_fulfilled: float
    total_fulfilled_value: float
    unique_skus: int
    unique_locations: int
    date_from: str | None = None
    date_to: str | None = None
    by_warehouse: list[FulfillmentWarehouseSummary]
    by_location: list[FulfillmentLocationSummary]
    by_sku: list[FulfillmentSkuSummary]
    by_order: list[FulfillmentOrderSummary]


class SkuOrdersReportRow(BaseModel):
    sku: str
    item_id: int | None = None
    description: str | None = None
    brand: str | None = None
    category: str | None = None
    location: str | None = None
    total_orders_count: int
    total_quantity_ordered: float
    total_quantity_allocated: float
    total_quantity_picked: float
    total_quantity_fulfilled: float
    unfulfilled_quantity: float
    unmatched_order_line_count: int
    first_order_date: datetime | None = None
    last_order_date: datetime | None = None
    current_in_stock: float | None = None
    current_allocated: float | None = None
    current_sellable: float | None = None
    woo_stock_snapshot: float | None = None


class SkuOrdersSummaryResponse(BaseModel):
    total_skus: int
    total_quantity_ordered: float
    total_quantity_fulfilled: float
    total_unfulfilled_quantity: float
    unmatched_lines_count: int
    top_sku_by_quantity: str | None = None
