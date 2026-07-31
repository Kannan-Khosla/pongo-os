from __future__ import annotations

from sqlalchemy import JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class StockMutationRequest(TimestampMixin, Base):
    __tablename__ = "stock_mutation_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    response_payload: Mapped[dict | None] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("operation", "idempotency_key", name="uq_stock_mutation_request_operation_key"),
    )
