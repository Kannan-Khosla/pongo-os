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
