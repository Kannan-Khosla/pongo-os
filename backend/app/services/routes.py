from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.orders import Order, OrderItem
from app.models.routes import Route, RouteStop
from app.schemas.routes import (
    RouteCandidateListResponse,
    RouteCandidateRead,
    RouteCommitResponse,
    RouteDetail,
    RouteMapPayload,
    RouteMapStop,
    RoutePreviewDetail,
    RoutePreviewResponse,
    RoutePreviewStop,
    RouteProviderPreviewResponse,
    RouteRead,
    RouteReorderRequest,
    RouteRequest,
    RouteStopUpdateRequest,
    RouteStopRead,
    RouteUpdateRequest,
)

ROUTE_ELIGIBLE_STATUSES = {"fulfilled", "partially_fulfilled"}
ROUTE_CSV_COLUMNS = [
    "Route Number",
    "Route Date",
    "Route Status",
    "Route Name",
    "Driver Name",
    "Vehicle Name",
    "Stop Sequence",
    "Woo Order Number",
    "Woo Order ID",
    "Local Status",
    "Customer Name",
    "Customer Email",
    "Customer Phone",
    "Shipping Summary",
    "Delivery Notes",
    "Stop Status",
    "Order Total",
    "Created At",
]


def list_route_candidates(
    db: Session,
    route_date: date | None = None,
    local_status: str | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    search: str | None = None,
) -> RouteCandidateListResponse:
    statement = select(Order).where(Order.local_status.in_(ROUTE_ELIGIBLE_STATUSES)).options(selectinload(Order.items), selectinload(Order.route_stops).selectinload(RouteStop.route)).order_by(Order.date_created.asc().nullslast(), Order.woo_order_number.asc().nullslast(), Order.id.asc())
    orders = list(db.scalars(statement).all())
    candidates = []
    for order in orders:
        candidate = order_to_candidate(order)
        if candidate.already_routed:
            continue
        if local_status and order.local_status != local_status:
            continue
        if customer_email and customer_email.casefold() not in (order.customer_email or "").casefold():
            continue
        if woo_order_number and woo_order_number.casefold() not in (order.woo_order_number or "").casefold():
            continue
        if search:
            needle = search.casefold()
            haystack = " ".join(str(value or "") for value in [order.woo_order_number, order.customer_name, order.customer_email, order.customer_phone]).casefold()
            if needle not in haystack:
                continue
        candidates.append(candidate)
    return RouteCandidateListResponse(total_candidates=len(candidates), candidates=candidates)


def preview_route(db: Session, payload: RouteRequest) -> RoutePreviewResponse:
    stops = build_preview_stops(db, payload)
    return build_preview_response(payload, stops)


def commit_route(db: Session, payload: RouteRequest) -> RouteCommitResponse:
    preview = preview_route(db, payload)
    if preview.errors or preview.invalid_orders:
        return RouteCommitResponse(status="rejected", route_date=payload.route_date, route_name=payload.route_name, total_stops=0, warnings=preview.warnings, errors=preview.errors or ["Route contains invalid orders."])
    valid_stops = [stop for stop in preview.preview_route.stops if stop.status == "valid"]
    if not valid_stops:
        return RouteCommitResponse(status="rejected", route_date=payload.route_date, route_name=payload.route_name, total_stops=0, warnings=preview.warnings, errors=["At least one valid route stop is required."])
    now = datetime.now(timezone.utc)
    route = Route(
        route_number=next_route_number(db, now),
        status="draft",
        route_date=payload.route_date,
        route_name=payload.route_name,
        driver_name=payload.driver_name,
        vehicle_name=payload.vehicle_name,
        notes=payload.notes,
        created_by=payload.created_by or "system",
        total_stops=len(valid_stops),
    )
    try:
        db.add(route)
        db.flush()
        for stop in valid_stops:
            order = db.get(Order, stop.order_id)
            if order is None or order_has_active_route(order):
                raise ValueError(f"Order {stop.order_id} is no longer available for routing.")
            db.add(
                RouteStop(
                    route_id=route.id,
                    stop_sequence=stop.stop_sequence,
                    stop_number=stop.stop_sequence,
                    order_id=order.id,
                    woo_order_id=order.woo_order_id,
                    woo_order_number=order.woo_order_number,
                    customer_name=order.customer_name,
                    customer_email=order.customer_email,
                    customer_phone=order.customer_phone,
                    shipping_summary=order.shipping_summary,
                    delivery_notes=payload.notes,
                    local_status=order.local_status,
                    stop_status="planned",
                    address_1=order.shipping_address_1,
                    address_2=order.shipping_address_2,
                    city=order.shipping_city,
                    state=order.shipping_state,
                    country=order.shipping_country,
                    zip=order.shipping_zip,
                    phone=order.shipping_phone or order.customer_phone,
                    notes=payload.notes,
                )
            )
        db.commit()
        db.refresh(route)
        return RouteCommitResponse(route_id=route.id, route_number=route.route_number, status=route.status or "draft", route_date=route.route_date, route_name=route.route_name, total_stops=route.total_stops, warnings=preview.warnings, errors=[])
    except Exception as exc:
        db.rollback()
        return RouteCommitResponse(status="error", route_date=payload.route_date, route_name=payload.route_name, total_stops=0, warnings=preview.warnings, errors=[str(exc)])


def build_preview_stops(db: Session, payload: RouteRequest) -> list[RoutePreviewStop]:
    stops = []
    seen = set()
    for sequence, order_id in enumerate(payload.order_ids, start=1):
        warnings = []
        errors = []
        if order_id in seen:
            errors.append("Order was selected more than once.")
        seen.add(order_id)
        order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items), selectinload(Order.route_stops).selectinload(RouteStop.route))).one_or_none()
        if order is None:
            stops.append(empty_preview_stop(sequence, order_id, ["Order was not found."]))
            continue
        candidate = order_to_candidate(order)
        if order.local_status not in ROUTE_ELIGIBLE_STATUSES:
            errors.append(f"Order status {order.local_status or 'unknown'} is not eligible for routing.")
        if candidate.fulfilled_line_count <= 0:
            errors.append("Order has no fulfilled lines.")
        if candidate.already_routed:
            errors.append("Order is already assigned to a non-cancelled route.")
        if not order.shipping_summary and not (order.customer_name or order.customer_email):
            errors.append("Order has no shipping summary or customer info.")
        if order.local_status == "partially_fulfilled":
            warnings.append("Order is partially fulfilled.")
        stops.append(
            RoutePreviewStop(
                stop_sequence=sequence,
                order_id=order.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                local_status=order.local_status,
                customer_name=order.customer_name,
                customer_email=order.customer_email,
                customer_phone=order.customer_phone,
                shipping_summary=order.shipping_summary,
                fulfilled_line_count=candidate.fulfilled_line_count,
                total_quantity_fulfilled=candidate.total_quantity_fulfilled,
                status="invalid" if errors else "valid",
                warnings=warnings,
                errors=errors,
            )
        )
    return stops


def build_preview_response(payload: RouteRequest, stops: list[RoutePreviewStop]) -> RoutePreviewResponse:
    warnings = [warning for stop in stops for warning in stop.warnings]
    errors = [error for stop in stops for error in stop.errors]
    return RoutePreviewResponse(
        total_orders=len(stops),
        valid_orders=sum(1 for stop in stops if stop.status == "valid"),
        invalid_orders=sum(1 for stop in stops if stop.status != "valid"),
        warning_count=len(warnings),
        warnings=warnings,
        errors=errors,
        preview_route=RoutePreviewDetail(
            route_date=payload.route_date,
            route_name=payload.route_name,
            driver_name=payload.driver_name,
            vehicle_name=payload.vehicle_name,
            estimated_stop_count=sum(1 for stop in stops if stop.status == "valid"),
            stops=stops,
        ),
    )


def list_routes(
    db: Session,
    status: str | None = None,
    route_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    driver_name: str | None = None,
    vehicle_name: str | None = None,
    search: str | None = None,
) -> list[Route]:
    statement = select(Route).options(selectinload(Route.stops)).order_by(Route.route_date.desc().nullslast(), Route.created_at.desc(), Route.id.desc())
    routes = list(db.scalars(statement).all())
    rows = []
    for route in routes:
        if status and route.status != status:
            continue
        if route_date and route.route_date != route_date:
            continue
        if date_from and route.route_date and route.route_date < date_from:
            continue
        if date_to and route.route_date and route.route_date > date_to:
            continue
        if driver_name and driver_name.casefold() not in (route.driver_name or "").casefold():
            continue
        if vehicle_name and vehicle_name.casefold() not in (route.vehicle_name or "").casefold():
            continue
        if search:
            haystack = " ".join(str(value or "") for value in [route.route_number, route.route_name, route.driver_name, route.vehicle_name]).casefold()
            if search.casefold() not in haystack:
                continue
        rows.append(route)
    return rows


def get_route_detail(db: Session, route_id: int) -> RouteDetail | None:
    route = db.scalars(select(Route).where(Route.id == route_id).options(selectinload(Route.stops).selectinload(RouteStop.order))).one_or_none()
    if route is None:
        return None
    base = route_to_read(route).model_dump()
    base["notes"] = route.notes
    base["stops"] = [route_stop_to_read(stop) for stop in sorted(route.stops, key=lambda row: row.stop_sequence or row.stop_number or row.id)]
    return RouteDetail.model_validate(base)


def update_route_metadata(db: Session, route_id: int, payload: RouteUpdateRequest) -> RouteDetail | None:
    route = db.scalars(select(Route).where(Route.id == route_id).options(selectinload(Route.stops))).one_or_none()
    if route is None:
        return None
    for field in ["route_name", "driver_name", "vehicle_name", "route_date", "notes"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(route, field, value)
    db.commit()
    return get_route_detail(db, route_id)


def reorder_route_stops(db: Session, route_id: int, payload: RouteReorderRequest) -> tuple[RouteDetail | None, list[str]]:
    route = db.scalars(select(Route).where(Route.id == route_id).options(selectinload(Route.stops))).one_or_none()
    if route is None:
        return None, []
    current_ids = {stop.id for stop in route.stops}
    requested_ids = payload.ordered_stop_ids
    if len(requested_ids) != len(set(requested_ids)):
        return None, ["Stop IDs must not contain duplicates."]
    if set(requested_ids) != current_ids:
        return None, ["Reorder request must include every stop on the route exactly once."]
    stops_by_id = {stop.id: stop for stop in route.stops}
    for sequence, stop_id in enumerate(requested_ids, start=1):
        stop = stops_by_id[stop_id]
        stop.stop_sequence = sequence
        stop.stop_number = sequence
        stop.optimized_sequence = None
    db.commit()
    return get_route_detail(db, route_id), []


def update_route_stop(db: Session, route_id: int, stop_id: int, payload: RouteStopUpdateRequest) -> RouteDetail | None:
    stop = db.scalars(select(RouteStop).where(RouteStop.route_id == route_id, RouteStop.id == stop_id)).one_or_none()
    if stop is None:
        return None
    for field in ["address_1", "address_2", "city", "state", "country", "zip", "delivery_notes", "internal_notes"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(stop, field, value)
    if payload.latitude is not None:
        stop.latitude = Decimal(str(payload.latitude))
        stop.geocode_status = "manual"
    if payload.longitude is not None:
        stop.longitude = Decimal(str(payload.longitude))
        stop.geocode_status = "manual"
    db.commit()
    return get_route_detail(db, route_id)


def get_route_map_payload(db: Session, route_id: int) -> RouteMapPayload | None:
    detail = get_route_detail(db, route_id)
    if detail is None:
        return None
    provider = get_settings().route_map_provider or "disabled"
    stops = [map_stop_from_read(stop) for stop in detail.stops]
    return RouteMapPayload(
        route=RouteRead(**detail.model_dump(exclude={"stops", "notes"})),
        stops=stops,
        missing_coordinates_count=sum(1 for stop in stops if stop.latitude is None or stop.longitude is None),
        provider_config_public={"provider": provider, "configured": provider not in {"", "disabled"}},
    )


def preview_route_geocode(db: Session, route_id: int) -> RouteProviderPreviewResponse | None:
    payload = get_route_map_payload(db, route_id)
    if payload is None:
        return None
    provider = get_settings().route_geo_provider or "disabled"
    if provider == "disabled":
        return RouteProviderPreviewResponse(status="disabled", provider=provider, message="No geocoding provider configured. Manual coordinates can be entered.", stops=payload.stops)
    return RouteProviderPreviewResponse(status="preview", provider=provider, message="Provider abstraction is configured; no external call was made by preview.", stops=payload.stops)


def commit_route_geocode(db: Session, route_id: int) -> RouteProviderPreviewResponse | None:
    payload = get_route_map_payload(db, route_id)
    if payload is None:
        return None
    provider = get_settings().route_geo_provider or "disabled"
    if provider == "disabled":
        return RouteProviderPreviewResponse(status="disabled", provider=provider, message="No geocoding provider configured. Manual coordinates can be entered.", stops=payload.stops)
    return RouteProviderPreviewResponse(status="disabled", provider=provider, message="Provider integration is not enabled for live calls in this MVP.", stops=payload.stops)


def preview_route_optimization(db: Session, route_id: int) -> RouteProviderPreviewResponse | None:
    payload = get_route_map_payload(db, route_id)
    if payload is None:
        return None
    provider = get_settings().route_optimization_provider or "disabled"
    if provider == "disabled":
        return RouteProviderPreviewResponse(status="disabled", provider=provider, message="No optimization provider configured.", stops=payload.stops)
    return RouteProviderPreviewResponse(status="preview", provider=provider, message="Provider abstraction is configured; no external call was made by preview.", stops=payload.stops)


def commit_route_optimization(db: Session, route_id: int) -> RouteProviderPreviewResponse | None:
    payload = get_route_map_payload(db, route_id)
    if payload is None:
        return None
    provider = get_settings().route_optimization_provider or "disabled"
    if provider == "disabled":
        return RouteProviderPreviewResponse(status="disabled", provider=provider, message="No optimization provider configured.", stops=payload.stops)
    route = db.get(Route, route_id)
    if route:
        route.optimization_status = "provider_not_enabled"
        db.commit()
    return RouteProviderPreviewResponse(status="disabled", provider=provider, message="Provider integration is not enabled for live calls in this MVP.", stops=payload.stops)


def export_route_csv(db: Session, route_id: int) -> str | None:
    detail = get_route_detail(db, route_id)
    if detail is None:
        return None
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(ROUTE_CSV_COLUMNS)
    for stop in detail.stops:
        writer.writerow(
            [
                detail.route_number,
                detail.route_date.isoformat() if detail.route_date else "",
                detail.status,
                detail.route_name or "",
                detail.driver_name or "",
                detail.vehicle_name or "",
                stop.stop_sequence,
                stop.woo_order_number or "",
                stop.woo_order_id or "",
                stop.local_status or "",
                stop.customer_name or "",
                stop.customer_email or "",
                stop.customer_phone or "",
                format_shipping_summary(stop.shipping_summary),
                stop.delivery_notes or "",
                stop.stop_status or "",
                stop.order_total or "",
                stop.created_at.isoformat() if stop.created_at else "",
            ]
        )
    return output.getvalue()


def finalize_route(db: Session, route_id: int) -> RouteCommitResponse | None:
    route = db.get(Route, route_id)
    if route is None:
        return None
    if route.status != "draft":
        return RouteCommitResponse(route_id=route.id, route_number=route.route_number, status="rejected", route_date=route.route_date, route_name=route.route_name, total_stops=route.total_stops, errors=["Only draft routes can be finalized."])
    route.status = "finalized"
    route.finalized_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(route)
    return RouteCommitResponse(route_id=route.id, route_number=route.route_number, status=route.status, route_date=route.route_date, route_name=route.route_name, total_stops=route.total_stops)


def cancel_route(db: Session, route_id: int) -> RouteCommitResponse | None:
    route = db.get(Route, route_id)
    if route is None:
        return None
    route.status = "cancelled"
    route.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(route)
    return RouteCommitResponse(route_id=route.id, route_number=route.route_number, status=route.status, route_date=route.route_date, route_name=route.route_name, total_stops=route.total_stops)


def route_to_read(route: Route) -> RouteRead:
    return RouteRead(
        id=route.id,
        route_number=route.route_number or "",
        status=route.status or "draft",
        route_date=route.route_date,
        route_name=route.route_name,
        driver_name=route.driver_name,
        vehicle_name=route.vehicle_name,
        total_stops=len(route.stops) if route.stops else route.total_stops,
        created_by=route.created_by,
        created_at=route.created_at,
        finalized_at=route.finalized_at,
        cancelled_at=route.cancelled_at,
    )


def route_stop_to_read(stop: RouteStop) -> RouteStopRead:
    return RouteStopRead(
        id=stop.id,
        stop_sequence=stop.stop_sequence or stop.stop_number or 0,
        order_id=stop.order_id,
        woo_order_id=stop.woo_order_id,
        woo_order_number=stop.woo_order_number,
        customer_name=stop.customer_name,
        customer_email=stop.customer_email,
        customer_phone=stop.customer_phone or stop.phone,
        shipping_summary=stop.shipping_summary,
        delivery_notes=stop.delivery_notes or stop.notes,
        internal_notes=stop.internal_notes,
        local_status=stop.local_status,
        stop_status=stop.stop_status or "planned",
        address_1=stop.address_1,
        address_2=stop.address_2,
        city=stop.city,
        state=stop.state,
        country=stop.country,
        zip=stop.zip,
        latitude=decimal_to_optional_float(stop.latitude),
        longitude=decimal_to_optional_float(stop.longitude),
        geocode_status=stop.geocode_status or "not_requested",
        geocode_provider=stop.geocode_provider,
        geocode_error=stop.geocode_error,
        order_total=decimal_to_float(stop.order.total) if stop.order else None,
        created_at=stop.created_at,
        updated_at=stop.updated_at,
    )


def map_stop_from_read(stop: RouteStopRead) -> RouteMapStop:
    address = ", ".join(part for part in [stop.address_1, stop.address_2, stop.city, stop.state, stop.zip, stop.country] if part)
    return RouteMapStop(
        stop_id=stop.id,
        stop_sequence=stop.stop_sequence,
        label=stop.customer_name or stop.woo_order_number or f"Stop {stop.stop_sequence}",
        address=address,
        latitude=stop.latitude,
        longitude=stop.longitude,
        geocode_status=stop.geocode_status or "not_requested",
    )


def order_to_candidate(order: Order) -> RouteCandidateRead:
    fulfilled_lines = [line for line in order.items if (line.quantity_fulfilled or Decimal("0")) > 0]
    warning = "Order is partially fulfilled." if order.local_status == "partially_fulfilled" else None
    return RouteCandidateRead(
        order_id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        local_status=order.local_status,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        customer_phone=order.customer_phone,
        shipping_summary=order.shipping_summary,
        order_total=decimal_to_float(order.total),
        date_created=order.date_created,
        date_modified=order.date_modified,
        fulfilled_line_count=len(fulfilled_lines),
        total_quantity_fulfilled=decimal_to_float(sum((line.quantity_fulfilled or Decimal("0")) for line in fulfilled_lines)),
        already_routed=order_has_active_route(order),
        route_warning=warning,
    )


def order_has_active_route(order: Order) -> bool:
    return any(stop.route and stop.route.status != "cancelled" for stop in order.route_stops)


def empty_preview_stop(sequence: int, order_id: int, errors: list[str]) -> RoutePreviewStop:
    return RoutePreviewStop(stop_sequence=sequence, order_id=order_id, fulfilled_line_count=0, total_quantity_fulfilled=0, status="invalid", errors=errors)


def next_route_number(db: Session, now: datetime) -> str:
    prefix = f"RT-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(Route.id)).where(Route.route_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def format_shipping_summary(summary: dict | None) -> str:
    if not summary:
        return ""
    return ", ".join(str(value) for value in summary.values() if value)


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value) if value is not None else 0


def decimal_to_optional_float(value: Decimal | int | float | None) -> float | None:
    return None if value is None else float(value)
