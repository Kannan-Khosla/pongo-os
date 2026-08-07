from datetime import datetime

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str | None] = mapped_column(String(300))
    import_type: Mapped[str | None] = mapped_column(String(80), index=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    preview_id: Mapped[str | None] = mapped_column(String(36), index=True)
    outcome: Mapped[str | None] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    options_json: Mapped[dict | None] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    excluded_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    starting_units: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(80), index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    errors: Mapped[list["ImportError"]] = relationship(back_populates="import_job", cascade="all, delete-orphan")

    __table_args__ = (
        Index(
            "uq_import_jobs_opening_file",
            "import_type",
            "file_sha256",
            unique=True,
            postgresql_where=text("import_type = 'items_enrichment_opening_stock' AND file_sha256 IS NOT NULL"),
            sqlite_where=text("import_type = 'items_enrichment_opening_stock' AND file_sha256 IS NOT NULL"),
        ),
    )


class ImportError(Base):
    __tablename__ = "import_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True, nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer, index=True)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(100), index=True)
    field_name: Mapped[str | None] = mapped_column(String(120), index=True)
    invalid_value: Mapped[str | None] = mapped_column(Text)
    blocking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    raw_row: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    import_job: Mapped[ImportJob] = relationship(back_populates="errors")


class ImportPreview(Base):
    __tablename__ = "import_previews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    outcome: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_file_text: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_headers: Mapped[list] = mapped_column(JSON, nullable=False)
    source_columns_json: Mapped[list] = mapped_column(JSON, nullable=False)
    mapping_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    options_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    commit_idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    import_job_id: Mapped[int | None] = mapped_column(ForeignKey("import_jobs.id"), index=True)
    created_by: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rows: Mapped[list["ImportPreviewRow"]] = relationship(back_populates="preview", cascade="all, delete-orphan")


class ImportPreviewRow(Base):
    __tablename__ = "import_preview_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    preview_id: Mapped[str] = mapped_column(ForeignKey("import_previews.id", ondelete="CASCADE"), index=True, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    barcode: Mapped[str | None] = mapped_column(String(120), index=True)
    product_name: Mapped[str | None] = mapped_column(String(500), index=True)
    source_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    corrected_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    existing_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_items.id"), index=True)
    source_item_hash: Mapped[str | None] = mapped_column(String(64))
    proposed_changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    issues_json: Mapped[list] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    match_method: Mapped[str | None] = mapped_column(String(80))
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    preview: Mapped[ImportPreview] = relationship(back_populates="rows")

    __table_args__ = (UniqueConstraint("preview_id", "row_number", name="uq_import_preview_rows_preview_row"),)


class ImportMappingProfile(Base):
    __tablename__ = "import_mapping_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    outcome: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    source_signature: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_headers: Mapped[list] = mapped_column(JSON, nullable=False)
    mapping_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("created_by", "outcome", "name", name="uq_import_mapping_profiles_actor_outcome_name"),)


class ItemImportChange(Base):
    __tablename__ = "item_import_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True, nullable=False)
    preview_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory_items.id"), index=True, nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120), index=True)
    field_name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    previous_value: Mapped[object | None] = mapped_column(JSON)
    new_value: Mapped[object | None] = mapped_column(JSON)
    source_filename: Mapped[str | None] = mapped_column(String(300))
    outcome: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    mapping_profile_id: Mapped[int | None] = mapped_column(ForeignKey("import_mapping_profiles.id"), index=True)
    created_by: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
