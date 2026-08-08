from datetime import datetime

from pydantic import BaseModel, Field


class CycleCountLineInput(BaseModel):
    item_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    counted_quantity: float
    notes: str | None = None


class CycleCountRequest(BaseModel):
    warehouse: str | None = None
    inventory_location: str | None = None
    count_type: str = "selected_items"
    notes: str | None = None
    created_by: str | None = "system"
    lines: list[CycleCountLineInput] = Field(default_factory=list)


class CycleCountPreviewLine(BaseModel):
    line_number: int
    item_id: int | None = None
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    system_quantity: float
    counted_quantity: float
    variance_quantity: float
    unit_cost: float
    variance_value: float
    status: str
    warnings: list[str] = []
    errors: list[str] = []


class CycleCountPreviewResponse(BaseModel):
    total_lines: int
    valid_lines: int
    invalid_lines: int
    adjustment_lines: int
    total_positive_variance: float
    total_negative_variance: float
    total_absolute_variance: float
    total_variance_value: float
    errors: list[str] = []
    warnings: list[str] = []
    preview_lines: list[CycleCountPreviewLine] = []


class CycleCountCommitResponse(BaseModel):
    cycle_count_id: int
    count_number: str
    status: str
    total_lines: int
    adjustment_lines: int
    total_positive_variance: float
    total_negative_variance: float
    total_absolute_variance: float
    total_variance_value: float
    created_movements: int
    warnings: list[str] = []


class CycleCountLineRead(BaseModel):
    id: int
    item_id: int
    inventory_item_location_id: int | None = None
    sku: str | None = None
    barcode: str | None = None
    description: str | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    system_quantity: float
    counted_quantity: float
    variance_quantity: float
    unit_cost: float | None = None
    variance_value: float
    notes: str | None = None
    created_at: datetime


class CycleCountRead(BaseModel):
    id: int
    count_number: str
    status: str
    warehouse: str
    inventory_location: str | None = None
    count_type: str
    notes: str | None = None
    created_by: str | None = None
    created_at: datetime
    posted_at: datetime | None = None
    total_lines: int
    adjustment_lines: int
    total_positive_variance: float
    total_negative_variance: float
    total_absolute_variance: float
    total_variance_value: float


class CycleCountDetail(CycleCountRead):
    lines: list[CycleCountLineRead] = []


class CycleCountListResponse(BaseModel):
    cycle_counts: list[CycleCountRead]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False
