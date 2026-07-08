from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class UISavedView(TimestampMixin, Base):
    __tablename__ = "ui_saved_views"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    view_key: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    page: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    filters_json: Mapped[str | None] = mapped_column(Text)
    columns_json: Mapped[str | None] = mapped_column(Text)
    sort_json: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
