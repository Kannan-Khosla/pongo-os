from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class InventoryLocationBase(BaseModel):
    warehouse: str | None = Field(default=None, validation_alias=AliasChoices("warehouse", "Warehouse"))
    code: str | None = Field(default=None, validation_alias=AliasChoices("code", "location_code", "Location Code"))
    name: str | None = Field(default=None, validation_alias=AliasChoices("name", "location_name", "Location Name"))
    description: str | None = Field(default=None, validation_alias=AliasChoices("description", "Description"))
    zone: str | None = Field(default=None, validation_alias=AliasChoices("zone", "Zone"))
    aisle: str | None = Field(default=None, validation_alias=AliasChoices("aisle", "Aisle"))
    rack: str | None = Field(default=None, validation_alias=AliasChoices("rack", "Rack"))
    shelf: str | None = Field(default=None, validation_alias=AliasChoices("shelf", "Shelf"))
    bin: str | None = Field(default=None, validation_alias=AliasChoices("bin", "Bin"))
    is_default: bool | None = Field(default=False, validation_alias=AliasChoices("isDefault", "is_default", "Default"))
    is_active: bool | None = Field(default=True, validation_alias=AliasChoices("isActive", "active", "Active"))

    model_config = ConfigDict(populate_by_name=True)


class InventoryLocationCreate(InventoryLocationBase):
    warehouse: str = Field(validation_alias=AliasChoices("warehouse", "Warehouse"), min_length=1)
    code: str = Field(validation_alias=AliasChoices("code", "location_code", "Location Code"), min_length=1)
    name: str = Field(validation_alias=AliasChoices("name", "location_name", "Location Name"), min_length=1)


class InventoryLocationUpdate(InventoryLocationBase):
    pass


class InventoryLocationRead(BaseModel):
    id: int
    warehouse: str
    code: str
    name: str
    description: str | None = None
    zone: str | None = None
    aisle: str | None = None
    rack: str | None = None
    shelf: str | None = None
    bin: str | None = None
    isDefault: bool
    isActive: bool
    createdAt: datetime
    updatedAt: datetime


class InventoryLocationListResponse(BaseModel):
    locations: list[InventoryLocationRead]
    total: int


class LocationImportRowError(BaseModel):
    row_number: int | None = None
    warehouse: str | None = None
    code: str | None = None
    error_message: str
    raw_row: dict | None = None


class LocationImportPreviewRow(BaseModel):
    row_number: int
    action: str
    warehouse: str | None = None
    code: str | None = None
    name: str | None = None
    warnings: list[str] = []
    row: dict


class LocationImportPreviewResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    create_count: int
    update_count: int
    skipped_count: int
    warnings: list[str] = []
    errors: list[LocationImportRowError] = []
    preview_rows: list[LocationImportPreviewRow] = []


class LocationImportCommitResponse(BaseModel):
    import_job_id: int
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    warnings: list[str] = []
    errors: list[LocationImportRowError] = []
