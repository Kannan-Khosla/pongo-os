from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class ScannerSession(TimestampMixin, Base):
    __tablename__ = "scanner_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, default="active", nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(80), index=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    events: Mapped[list["ScannerEvent"]] = relationship(back_populates="session")


class ScannerEvent(Base):
    __tablename__ = "scanner_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scanner_session_id: Mapped[int | None] = mapped_column(ForeignKey("scanner_sessions.id"), index=True)
    session_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    scan_input: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    matched_entity_type: Mapped[str | None] = mapped_column(String(80), index=True)
    matched_entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    result_status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    warehouse: Mapped[str | None] = mapped_column(String(120), index=True)
    inventory_location: Mapped[str | None] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped[ScannerSession | None] = relationship(back_populates="events")
