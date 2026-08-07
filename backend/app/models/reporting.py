from datetime import datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleReportsConfiguration(Base):
    __tablename__ = "google_reports_configuration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    client_id_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    folder_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, index=True)

    __table_args__ = (CheckConstraint("id = 1", name="ck_google_reports_configuration_singleton"),)


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Edmonton")
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    csv_artifact: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    csv_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    pdf_artifact: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    pdf_artifact_hash: Mapped[str | None] = mapped_column(String(64))
    generated_by: Mapped[str | None] = mapped_column(String(120))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class ReportJob(Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        Index(
            "uq_report_jobs_active_request",
            "request_key",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    request_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), index=True, nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_by: Mapped[str | None] = mapped_column(String(120))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("report_runs.id"), index=True)
    previous_run_id: Mapped[str | None] = mapped_column(ForeignKey("report_runs.id"), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )


class ReportDelivery(Base):
    __tablename__ = "report_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_run_id: Mapped[str] = mapped_column(ForeignKey("report_runs.id"), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(320), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    external_url: Mapped[str | None] = mapped_column(String(1000))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
