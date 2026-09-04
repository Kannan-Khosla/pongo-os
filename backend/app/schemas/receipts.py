from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    idempotency_key: str | None = Field(default=None, max_length=120)
    warehouse: str | None = None
    reference_number: str | None = None
    notes: str | None = None
    created_by: str | None = "system"
    lines: list[DirectReceiptLineInput] = Field(default_factory=list)


class DirectReceiptCommitRequest(DirectReceiptRequest):
    idempotency_key: str = Field(min_length=1, max_length=120)


class BulkReceiptLineInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    scan_input: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    quantity: float | None = None
    quantity_received: float | None = None
    unit_cost: float | None = None
    notes: str | None = None

    @field_validator("unit_cost", mode="before")
    @classmethod
    def blank_unit_cost_uses_saved_cost(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class BulkReceiptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(default=None, max_length=120)
    source: Literal["manual"] = "manual"
    warehouse: str | None = None
    reference_number: str | None = Field(default=None, max_length=120)
    receipt_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    commit_valid_lines_only: bool = False
    lines: list[BulkReceiptLineInput] = Field(default_factory=list)


class BulkReceiptCommitRequest(BulkReceiptRequest):
    idempotency_key: str = Field(min_length=1, max_length=120)


class InvoiceReceiptLineInput(BaseModel):
    source_line_number: int = Field(ge=1)
    item_id: int
    upc: str = Field(min_length=1, max_length=120)
    invoice_description: str = Field(min_length=1, max_length=500)
    uom: str = Field(min_length=1, max_length=20)
    shipped_quantity: float = Field(gt=0)
    pack_multiplier: int = Field(default=1, ge=1, le=1000)
    quantity_pieces: float = Field(gt=0)
    net_price: float = Field(gt=0)
    unit_cost: float = Field(gt=0)
    inventory_location: str = Field(min_length=1, max_length=200)
    review_required: bool = False
    human_verified: bool = False
    notes: str | None = Field(default=None, max_length=500)


class InvoiceReceiptCommitRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)
    supplier: str = Field(min_length=1, max_length=120)
    invoice_number: str = Field(min_length=1, max_length=120)
    invoice_date: date | None = None
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    warehouse: str = Field(default="Main Warehouse", min_length=1, max_length=120)
    duplicate_override: bool = False
    override_reason: str | None = Field(default=None, max_length=500)
    sync_woocommerce: bool = True
    lines: list[InvoiceReceiptLineInput] = Field(min_length=1)


class InvoiceReceiptReversalRequest(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=3, max_length=500)
    sync_woocommerce: bool = True


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
    client: str | None = None
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
    page: int = 1
    page_size: int = 0
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False
