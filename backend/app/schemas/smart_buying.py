from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


Money = Annotated[Decimal, Field(ge=0, le=10_000_000, max_digits=12, decimal_places=2)]


class SmartBuyingExportLine(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    product_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    cases: int = Field(ge=1, le=10_000, strict=True)
    units: int = Field(ge=1, le=1_000_000, strict=True)
    unit_cost: Money
    discount: Decimal = Field(ge=0, le=1)
    effective_cost: Decimal = Field(ge=0, le=10_000_000, max_digits=14, decimal_places=6)
    line_total: Money
    retail_value: Money


class SmartBuyingExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    po_number: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    supplier_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    as_of: date
    expected_delivery: date
    lines: list[SmartBuyingExportLine] = Field(min_length=1, max_length=100)
    freight: Money
    tax: Money

    @model_validator(mode="after")
    def validate_order(self):
        if not 0 <= (self.expected_delivery - self.as_of).days <= 365:
            raise ValueError("Expected delivery must be within one year after the draft date.")
        if len({line.product_id for line in self.lines}) != len(self.lines):
            raise ValueError("Each product may appear only once in a draft purchase order.")
        return self
