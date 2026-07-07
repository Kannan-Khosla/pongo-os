from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.orders import Order


class Route(TimestampMixin, Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_number: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)
    status: Mapped[str | None] = mapped_column(String(80), index=True)
    route_name: Mapped[str | None] = mapped_column(String(200))
    route_date: Mapped[date | None] = mapped_column(Date, index=True)
    driver_name: Mapped[str | None] = mapped_column(String(200), index=True)
    vehicle_name: Mapped[str | None] = mapped_column(String(200), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    start_address: Mapped[str | None] = mapped_column(String(500))
    end_address: Mapped[str | None] = mapped_column(String(500))
    total_stops: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_distance: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    estimated_duration: Mapped[int | None] = mapped_column(Integer)
    map_provider: Mapped[str | None] = mapped_column(String(80))
    optimization_status: Mapped[str | None] = mapped_column(String(80), index=True)
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[str | None] = mapped_column(String(120), index=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    stops: Mapped[list["RouteStop"]] = relationship(back_populates="route", cascade="all, delete-orphan")


class RouteStop(TimestampMixin, Base):
    __tablename__ = "route_stops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True, nullable=False)
    stop_sequence: Mapped[int | None] = mapped_column(Integer, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True, nullable=False)
    woo_order_id: Mapped[int | None] = mapped_column(Integer, index=True)
    woo_order_number: Mapped[str | None] = mapped_column(String(120), index=True)
    stop_number: Mapped[int | None] = mapped_column(Integer, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(240))
    customer_email: Mapped[str | None] = mapped_column(String(240), index=True)
    customer_phone: Mapped[str | None] = mapped_column(String(80))
    shipping_summary: Mapped[dict | None] = mapped_column(JSON)
    delivery_notes: Mapped[str | None] = mapped_column(Text)
    local_status: Mapped[str | None] = mapped_column(String(80), index=True)
    stop_status: Mapped[str | None] = mapped_column(String(40), index=True)
    address_1: Mapped[str | None] = mapped_column(String(240))
    address_2: Mapped[str | None] = mapped_column(String(240))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))
    zip: Mapped[str | None] = mapped_column(String(40))
    phone: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    geocode_status: Mapped[str | None] = mapped_column(String(40), default="not_requested", index=True)
    geocode_provider: Mapped[str | None] = mapped_column(String(80))
    geocode_error: Mapped[str | None] = mapped_column(Text)
    optimized_sequence: Mapped[int | None] = mapped_column(Integer, index=True)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    route: Mapped[Route] = relationship(back_populates="stops")
    order: Mapped["Order | None"] = relationship(back_populates="route_stops")
