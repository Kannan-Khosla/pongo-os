from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportRowError(BaseModel):
    row_number: int | None = None
    sku: str | None = None
    barcode: str | None = None
    error_message: str
    raw_row: dict | None = None


class ImportPreviewRow(BaseModel):
    row_number: int
    action: str
    sku: str | None = None
    barcode: str | None = None
    warnings: list[str] = []
    row: dict


class ImportPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    create_count: int
    update_count: int
    skipped_count: int
    warnings: list[str] = []
    errors: list[ImportRowError] = []
    preview_rows: list[ImportPreviewRow] = []


class ImportCommitResponse(BaseModel):
    import_job_id: int
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    errors: list[ImportRowError] = []


class ImportErrorRead(BaseModel):
    id: int
    import_job_id: int
    row_number: int | None
    sku: str | None
    barcode: str | None
    error_message: str | None
    raw_row: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportJobRead(BaseModel):
    id: int
    file_name: str | None
    import_type: str | None
    total_rows: int
    successful_rows: int
    failed_rows: int
    status: str | None
    created_by: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ImportJobDetail(ImportJobRead):
    errors: list[ImportErrorRead] = []
