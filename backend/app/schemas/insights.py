from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DataQualityWarning(BaseModel):
    code: str
    severity: str = "info"
    message: str


class InsightResponse(BaseModel):
    generated_at: datetime
    dashboard: str
    summary: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    trends: dict[str, list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    tables: dict[str, list[dict[str, Any]]] = {}
    data_quality: list[DataQualityWarning] = []
    empty_state: str | None = None
    comparison: dict[str, Any] | None = None
