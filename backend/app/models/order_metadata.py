from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import Order


class OrderNote(TimestampMixin, Base):
    __tablename__ = "order_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    order: Mapped["Order"] = relationship(back_populates="notes")

    __table_args__ = (Index("ix_order_notes_created_at", "created_at"),)


class OrderTag(TimestampMixin, Base):
    __tablename__ = "order_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    created_by: Mapped[str] = mapped_column(String(320), nullable=False, index=True)

    assignments: Mapped[list["OrderTagAssignment"]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class OrderTagAssignment(Base):
    __tablename__ = "order_tag_assignments"

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("order_tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assigned_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    order: Mapped["Order"] = relationship(back_populates="tag_assignments")
    tag: Mapped[OrderTag] = relationship(back_populates="assignments")

    __table_args__ = (
        Index("ix_order_tag_assignments_order_position", "order_id", "position"),
    )
