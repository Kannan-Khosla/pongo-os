from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import Order


class Route(TimestampMixin, Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_name: Mapped[str | None] = mapped_column(String(200))
    route_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str | None] = mapped_column(String(80), index=True)
    start_address: Mapped[str | None] = mapped_column(String(500))
    end_address: Mapped[str | None] = mapped_column(String(500))
    total_stops: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_distance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    estimated_duration: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)

    stops: Mapped[list["RouteStop"]] = relationship(back_populates="route", cascade="all, delete-orphan")


class RouteStop(TimestampMixin, Base):
    __tablename__ = "route_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True, nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), index=True)
    stop_number: Mapped[int | None] = mapped_column(Integer, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(240))
    address_1: Mapped[str | None] = mapped_column(String(240))
    address_2: Mapped[str | None] = mapped_column(String(240))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    zip: Mapped[str | None] = mapped_column(String(40))
    phone: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    optimized_sequence: Mapped[int | None] = mapped_column(Integer, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    route: Mapped[Route] = relationship(back_populates="stops")
    order: Mapped["Order | None"] = relationship(back_populates="route_stops")
