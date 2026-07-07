from datetime import datetime

from pydantic import BaseModel


class OpenOrderLineRead(BaseModel):
    id: int
    woo_line_item_id: int | None = None
    woo_product_id: int | None = None
    woo_variation_id: int | None = None
    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    name: str | None = None
    quantity_ordered: float
    quantity_allocated: float
    quantity_picked: float
    unit_price: float | None = None
    line_total: float | None = None
    matched_status: str | None = None
    availability_status: str | None = None
    sellable_snapshot: float
    shortage_quantity: float
    sync_status: str | None = None
    sync_error: str | None = None


class OpenOrderRead(BaseModel):
    id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    woo_status: str | None = None
    local_status: str | None = None
    currency: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    total: float | None = None
    date_created: datetime | None = None
    date_modified: datetime | None = None
    line_count: int
    availability_status: str | None = None
    matched_status: str | None = None
    last_synced_at: datetime | None = None


class OpenOrderDetail(OpenOrderRead):
    customer_id: int | None = None
    billing_summary: dict | None = None
    shipping_summary: dict | None = None
    payment_method: str | None = None
    payment_method_title: str | None = None
    subtotal: float | None = None
    discount_total: float | None = None
    shipping_total: float | None = None
    tax_total: float | None = None
    lines: list[OpenOrderLineRead]


class OpenOrderListResponse(BaseModel):
    orders: list[OpenOrderRead]
    total: int
    available_count: int
    partial_count: int
    unavailable_count: int
    unknown_count: int
