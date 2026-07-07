from datetime import date, datetime

from pydantic import BaseModel, Field


class DirectReceiptLineInput(BaseModel):
    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    inventory_location: str | None = None
    default_location: str | None = None
    quantity_received: float
    unit_cost: float | None = None
    lot_number: str | None = None
    expiry_date: date | None = None
    notes: str | None = None


class DirectReceiptRequest(BaseModel):
    warehouse: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    created_by: str | None = "system"
    lines: list[DirectReceiptLineInput] = Field(default_factory=list)


class DirectReceiptLinePreview(BaseModel):
    line_number: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    quantity_received: float
    previous_in_stock: float
    new_in_stock: float
    previous_location_in_stock: float | None = None
    new_location_in_stock: float | None = None
    previous_item_in_stock: float | None = None
    new_item_in_stock: float | None = None
    unit_cost: float
    line_value: float
    status: str
    warnings: list[str] = []
    errors: list[str] = []


class DirectReceiptPreviewResponse(BaseModel):
    total_lines: int
    valid_lines: int
    invalid_lines: int
    total_quantity: float
    estimated_inventory_value: float
    errors: list[str] = []
    warnings: list[str] = []
    preview_lines: list[DirectReceiptLinePreview] = []


class DirectReceiptCommitResponse(BaseModel):
    receipt_id: int
    receipt_number: str
    status: str
    total_lines: int
    total_quantity_received: float
    total_inventory_value: float
    created_movements: int
    warnings: list[str] = []


class ReceiptLineRead(BaseModel):
    id: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    default_location: str | None = None
    quantity_received: float
    unit_cost: float | None = None
    lot_number: str | None = None
    expiry_date: date | None = None
    notes: str | None = None
    created_at: datetime


class ReceiptRead(BaseModel):
    id: int
    receipt_number: str
    receipt_type: str | None = None
    status: str | None = None
    warehouse: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    created_by: str | None = None
    received_at: datetime | None = None
    created_at: datetime
    total_lines: int
    total_quantity: float


class ReceiptDetail(ReceiptRead):
    lines: list[ReceiptLineRead] = []


class ReceiptListResponse(BaseModel):
    receipts: list[ReceiptRead]
    total: int
