from datetime import date, datetime

from pydantic import BaseModel, Field


class RouteCandidateRead(BaseModel):
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    shipping_summary: dict | None = None
    order_total: float | None = None
    date_created: datetime | None = None
    date_modified: datetime | None = None
    fulfilled_line_count: int
    total_quantity_fulfilled: float
    already_routed: bool = False
    route_warning: str | None = None


class RouteCandidateListResponse(BaseModel):
    total_candidates: int
    candidates: list[RouteCandidateRead]
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class RouteRequest(BaseModel):
    route_date: date
    route_name: str | None = None
    driver_name: str | None = None
    vehicle_name: str | None = None
    order_ids: list[int] = Field(default_factory=list)
    created_by: str | None = "system"
    notes: str | None = None


class RoutePreviewStop(BaseModel):
    stop_sequence: int
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    shipping_summary: dict | None = None
    fulfilled_line_count: int
    total_quantity_fulfilled: float
    status: str
    warnings: list[str] = []
    errors: list[str] = []


class RoutePreviewDetail(BaseModel):
    route_date: date
    route_name: str | None = None
    driver_name: str | None = None
    vehicle_name: str | None = None
    estimated_stop_count: int
    stops: list[RoutePreviewStop] = []


class RoutePreviewResponse(BaseModel):
    total_orders: int
    valid_orders: int
    invalid_orders: int
    warning_count: int
    errors: list[str] = []
    warnings: list[str] = []
    preview_route: RoutePreviewDetail


class RouteCommitResponse(BaseModel):
    route_id: int | None = None
    route_number: str | None = None
    status: str
    route_date: date | None = None
    route_name: str | None = None
    total_stops: int
    warnings: list[str] = []
    errors: list[str] = []


class RouteStopRead(BaseModel):
    id: int
    stop_sequence: int
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    shipping_summary: dict | None = None
    delivery_notes: str | None = None
    internal_notes: str | None = None
    local_status: str | None = None
    stop_status: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geocode_status: str | None = None
    geocode_provider: str | None = None
    geocode_error: str | None = None
    order_total: float | None = None
    created_at: datetime
    updated_at: datetime


class RouteRead(BaseModel):
    id: int
    route_number: str
    status: str
    route_date: date | None = None
    route_name: str | None = None
    driver_name: str | None = None
    vehicle_name: str | None = None
    total_stops: int
    created_by: str | None = None
    created_at: datetime
    finalized_at: datetime | None = None
    cancelled_at: datetime | None = None


class RouteDetail(RouteRead):
    notes: str | None = None
    stops: list[RouteStopRead]


class RouteListResponse(BaseModel):
    routes: list[RouteRead]
    total: int
    page: int = 1
    page_size: int = 50
    total_pages: int = 0
    returned_count: int = 0
    has_previous: bool = False
    has_next: bool = False


class RouteUpdateRequest(BaseModel):
    route_name: str | None = None
    driver_name: str | None = None
    vehicle_name: str | None = None
    route_date: date | None = None
    notes: str | None = None


class RouteReorderRequest(BaseModel):
    ordered_stop_ids: list[int]


class RouteStopUpdateRequest(BaseModel):
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    zip: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    delivery_notes: str | None = None
    internal_notes: str | None = None


class RouteMapStop(BaseModel):
    stop_id: int
    stop_sequence: int
    label: str
    address: str
    latitude: float | None = None
    longitude: float | None = None
    geocode_status: str | None = None


class RouteMapPayload(BaseModel):
    route: RouteRead
    stops: list[RouteMapStop]
    missing_coordinates_count: int
    provider_config_public: dict


class RouteProviderPreviewResponse(BaseModel):
    status: str
    provider: str
    message: str
    stops: list[RouteMapStop] = []
    warnings: list[str] = []
