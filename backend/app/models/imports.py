from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str | None] = mapped_column(String(300))
    import_type: Mapped[str | None] = mapped_column(String(80), index=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    options_json: Mapped[dict | None] = mapped_column(JSON)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    raw_row: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    import_job: Mapped[ImportJob] = relationship(back_populates="errors")
