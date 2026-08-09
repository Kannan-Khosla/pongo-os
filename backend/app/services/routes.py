from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from urllib.parse import urlencode

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.models.orders import Order, OrderItem
from app.models.routes import Route, RouteStop
from app.schemas.routes import (
    DriverOpenOrderRoutePlan,
    GoogleMapsRouteLink,
    OpenOrderRouteExcludedOrder,
    OpenOrderRoutePlanRequest,
    OpenOrderRoutePlanResponse,
    OpenOrderRoutePlanStop,
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
from app.services.order_workflow import COMPLETED_LOCAL_STATUSES, operational_order_clause

ROUTE_ELIGIBLE_STATUSES = {"completed", "fulfilled", "partially_fulfilled"}
DEFAULT_ROUTE_START_ADDRESS = "5855 99 Street NW, Edmonton, AB"
GOOGLE_MAPS_DIRECTIONS_URL = "https://www.google.com/maps/dir/"
GOOGLE_MAPS_MOBILE_DELIVERY_STOPS_PER_LINK = 4
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


def plan_open_order_routes(db: Session, payload: OpenOrderRoutePlanRequest) -> OpenOrderRoutePlanResponse:
    closed_local_statuses = COMPLETED_LOCAL_STATUSES | {"cancelled", "canceled", "failed", "refunded"}
    orders = list(
        db.scalars(
            select(Order)
            .where(
                operational_order_clause(),
                ~func.coalesce(Order.completion_status, "").in_(("completed", "completed_without_picking")),
                ~func.coalesce(Order.local_status, "").in_(tuple(closed_local_statuses)),
            )
            .order_by(Order.date_created.asc().nullslast(), Order.id.asc())
        ).all()
    )

    routable: list[tuple[Order, str, str]] = []
    excluded: list[OpenOrderRouteExcludedOrder] = []
    for order in orders:
        address = order_shipping_address(order)
        if not order.shipping_address_1 or not (order.shipping_city or order.shipping_zip):
            excluded.append(
                OpenOrderRouteExcludedOrder(
                    order_id=order.id,
                    woo_order_number=order.woo_order_number,
                    customer_name=order.customer_name,
                    reason="A street address plus city or postal code is required.",
                )
            )
            continue
        routable.append((order, address, order_postal_area(order)))

    routable.sort(
        key=lambda row: (
            row[2],
            normalize_postal_code(row[0].shipping_zip),
            (row[0].shipping_city or "").casefold(),
            (row[0].shipping_address_1 or "").casefold(),
            row[0].id,
        )
    )
    effective_driver_count = min(payload.driver_count, len(routable)) if routable else 0
    warnings: list[str] = []
    if excluded:
        warnings.append(f"{len(excluded)} open order(s) were excluded because their delivery address is incomplete.")
    if routable and payload.driver_count > len(routable):
        warnings.append(
            f"Only {len(routable)} driver route(s) were created because there are {len(routable)} routable open order(s)."
        )

    drivers: list[DriverOpenOrderRoutePlan] = []
    for driver_index, driver_orders in enumerate(split_balanced(routable, effective_driver_count), start=1):
        stops = [
            OpenOrderRoutePlanStop(
                stop_sequence=stop_sequence,
                order_id=order.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                local_status=order.local_status,
                customer_name=order.customer_name,
                customer_phone=order.shipping_phone or order.customer_phone,
                address=address,
                postal_area=postal_area or None,
            )
            for stop_sequence, (order, address, postal_area) in enumerate(driver_orders, start=1)
        ]
        links = build_google_maps_route_links(
            start_address=payload.start_address.strip() or DEFAULT_ROUTE_START_ADDRESS,
            stops=stops,
            return_to_start=payload.return_to_start,
        )
        delivery_link_count = sum(1 for link in links if not link.returns_to_start)
        if delivery_link_count > 1:
            warnings.append(
                f"Driver {driver_index} is split into {delivery_link_count} Google Maps parts so every link works reliably on iPhone and Android."
            )
        drivers.append(
            DriverOpenOrderRoutePlan(
                driver_number=driver_index,
                driver_label=f"Driver {driver_index}",
                stop_count=len(stops),
                stops=stops,
                google_maps_links=links,
            )
        )

    return OpenOrderRoutePlanResponse(
        start_address=payload.start_address.strip() or DEFAULT_ROUTE_START_ADDRESS,
        requested_driver_count=payload.driver_count,
        effective_driver_count=effective_driver_count,
        total_open_orders=len(orders),
        routable_order_count=len(routable),
        excluded_order_count=len(excluded),
        return_to_start=payload.return_to_start,
        assignment_method="balanced_by_postal_area",
        drivers=drivers,
        excluded_orders=excluded,
        warnings=warnings,
    )


def order_shipping_address(order: Order) -> str:
    return ", ".join(
        part.strip()
        for part in [
            order.shipping_address_1,
            order.shipping_address_2,
            order.shipping_address_3,
            order.shipping_city,
            order.shipping_state,
            order.shipping_zip,
            order.shipping_country,
        ]
        if part and part.strip()
    )


def normalize_postal_code(value: str | None) -> str:
    return "".join((value or "").upper().split())


def order_postal_area(order: Order) -> str:
    postal_code = normalize_postal_code(order.shipping_zip)
    if postal_code:
        return postal_code[:3]
    return (order.shipping_city or "").strip().upper()


def split_balanced(rows: list, group_count: int) -> list[list]:
    if group_count <= 0:
        return []
    base_size, extra = divmod(len(rows), group_count)
    groups = []
    cursor = 0
    for group_index in range(group_count):
        group_size = base_size + (1 if group_index < extra else 0)
        groups.append(rows[cursor : cursor + group_size])
        cursor += group_size
    return groups


def build_google_maps_route_links(
    *,
    start_address: str,
    stops: list[OpenOrderRoutePlanStop],
    return_to_start: bool,
) -> list[GoogleMapsRouteLink]:
    links: list[GoogleMapsRouteLink] = []
    origin = start_address
    for offset in range(0, len(stops), GOOGLE_MAPS_MOBILE_DELIVERY_STOPS_PER_LINK):
        stop_group = stops[offset : offset + GOOGLE_MAPS_MOBILE_DELIVERY_STOPS_PER_LINK]
        destination = stop_group[-1].address
        parameters = {
            "api": "1",
            "origin": origin,
            "destination": destination,
            "travelmode": "driving",
        }
        if len(stop_group) > 1:
            parameters["waypoints"] = "|".join(stop.address for stop in stop_group[:-1])
        part_number = len(links) + 1
        links.append(
            GoogleMapsRouteLink(
                part_number=part_number,
                label=f"Stops {stop_group[0].stop_sequence}–{stop_group[-1].stop_sequence}",
                url=f"{GOOGLE_MAPS_DIRECTIONS_URL}?{urlencode(parameters)}",
                stop_sequence_from=stop_group[0].stop_sequence,
                stop_sequence_to=stop_group[-1].stop_sequence,
                stop_count=len(stop_group),
            )
        )
        origin = destination

    if return_to_start and stops:
        links.append(
            GoogleMapsRouteLink(
                part_number=len(links) + 1,
                label="Return to starting location",
                url=f"{GOOGLE_MAPS_DIRECTIONS_URL}?{urlencode({'api': '1', 'origin': origin, 'destination': start_address, 'travelmode': 'driving'})}",
                stop_sequence_from=stops[-1].stop_sequence,
                stop_sequence_to=None,
                stop_count=0,
                returns_to_start=True,
            )
        )
    return links


def list_route_candidates(
    db: Session,
    route_date: date | None = None,
    local_status: str | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> RouteCandidateListResponse:
    active_route_exists = (
        select(RouteStop.id)
        .join(Route, Route.id == RouteStop.route_id)
        .where(
            RouteStop.order_id == Order.id,
            or_(Route.status.is_(None), Route.status != "cancelled"),
        )
        .exists()
    )
    predicates = [
        Order.local_status.in_(ROUTE_ELIGIBLE_STATUSES),
        Order.is_historical_snapshot.is_(False),
        ~active_route_exists,
    ]
    if route_date:
        day_start = datetime(route_date.year, route_date.month, route_date.day, tzinfo=timezone.utc)
        predicates.extend((Order.date_created >= day_start, Order.date_created < day_start + timedelta(days=1)))
    if local_status:
        predicates.append(Order.local_status == local_status)
    if customer_email:
        predicates.append(func.lower(func.coalesce(Order.customer_email, "")).contains(customer_email.casefold(), autoescape=True))
    if woo_order_number:
        predicates.append(func.lower(func.coalesce(Order.woo_order_number, "")).contains(woo_order_number.casefold(), autoescape=True))
    if search:
        search_text = (
            func.coalesce(Order.woo_order_number, "")
            + " "
            + func.coalesce(Order.customer_name, "")
            + " "
            + func.coalesce(Order.customer_email, "")
            + " "
            + func.coalesce(Order.customer_phone, "")
        )
        predicates.append(func.lower(search_text).contains(search.casefold(), autoescape=True))

    total = int(db.scalar(select(func.count(Order.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    orders = list(
        db.scalars(
            select(Order)
            .where(*predicates)
            .options(selectinload(Order.items))
            .order_by(Order.date_created.asc().nullslast(), Order.woo_order_number.asc().nullslast(), Order.id.asc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    candidates = [order_to_candidate(order, already_routed=False) for order in orders]
    return RouteCandidateListResponse(
        total_candidates=total,
        candidates=candidates,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(candidates),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


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
        if order.is_historical_snapshot:
            errors.append("Historical reporting snapshots are not eligible for routing.")
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


def list_routes_page(
    db: Session,
    status: str | None = None,
    route_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    driver_name: str | None = None,
    vehicle_name: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Route], int, int, int]:
    predicates = []
    if status:
        predicates.append(Route.status == status)
    if route_date:
        predicates.append(Route.route_date == route_date)
    if date_from:
        predicates.append(or_(Route.route_date.is_(None), Route.route_date >= date_from))
    if date_to:
        predicates.append(or_(Route.route_date.is_(None), Route.route_date <= date_to))
    if driver_name:
        predicates.append(func.lower(func.coalesce(Route.driver_name, "")).contains(driver_name.casefold(), autoescape=True))
    if vehicle_name:
        predicates.append(func.lower(func.coalesce(Route.vehicle_name, "")).contains(vehicle_name.casefold(), autoescape=True))
    if search:
        search_text = (
            func.coalesce(Route.route_number, "")
            + " "
            + func.coalesce(Route.route_name, "")
            + " "
            + func.coalesce(Route.driver_name, "")
            + " "
            + func.coalesce(Route.vehicle_name, "")
        )
        predicates.append(func.lower(search_text).contains(search.casefold(), autoescape=True))

    total = int(db.scalar(select(func.count(Route.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    routes = list(
        db.scalars(
            select(Route)
            .where(*predicates)
            .options(selectinload(Route.stops))
            .order_by(Route.route_date.desc().nullslast(), Route.created_at.desc(), Route.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return routes, total, effective_page, total_pages


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


def order_to_candidate(order: Order, *, already_routed: bool | None = None) -> RouteCandidateRead:
    line_quantities = [max(line.quantity_fulfilled or Decimal("0"), line.quantity_picked or Decimal("0")) for line in order.items]
    fulfilled_lines = [quantity for quantity in line_quantities if quantity > 0]
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
        total_quantity_fulfilled=decimal_to_float(sum(fulfilled_lines, Decimal("0"))),
        already_routed=order_has_active_route(order) if already_routed is None else already_routed,
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
