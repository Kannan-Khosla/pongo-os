from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


RouteDirection = Literal["N", "S", "E", "W", "NE", "NW", "SE", "SW", "Central East", "Central West"]


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


class OpenOrderRoutePlanRequest(BaseModel):
    start_address: str = Field(
        default="5855 99 Street NW, Edmonton, AB",
        min_length=3,
        max_length=500,
    )
    driver_count: int = Field(default=1, ge=1, le=50)
    return_to_start: bool = False
    order_ids: list[int] | None = Field(default=None, max_length=5000)
    assignment_method: Literal["equal_time", "directions"] = "equal_time"
    order_directions: list["OpenOrderDirectionOverride"] = Field(default_factory=list, max_length=5000)
    direction_assignments: list["DriverDirectionAssignment"] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_driver_assignments(self):
        if any(assignment.driver_number > self.driver_count for assignment in self.direction_assignments):
            raise ValueError("Direction assignments must reference one of the requested drivers.")
        if self.order_ids is not None and len(set(self.order_ids)) != len(self.order_ids):
            raise ValueError("Each selected order may appear only once.")
        if len({assignment.driver_number for assignment in self.direction_assignments}) != len(self.direction_assignments):
            raise ValueError("Each driver may have only one direction assignment.")
        if any(len(set(assignment.directions)) != len(assignment.directions) for assignment in self.direction_assignments):
            raise ValueError("A driver's direction assignment may not contain duplicate zones.")
        if len({candidate.order_id for candidate in self.order_directions}) != len(self.order_directions):
            raise ValueError("Each order may have only one direction override.")
        return self


class OpenOrderDirectionOverride(BaseModel):
    order_id: int
    direction: RouteDirection


class DriverDirectionAssignment(BaseModel):
    driver_number: int = Field(ge=1, le=50)
    directions: list[RouteDirection] = Field(default_factory=list, max_length=10)


class OpenOrderRouteCandidate(BaseModel):
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    address: str
    postal_area: str | None = None
    direction: RouteDirection
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source: str | None = None


class OpenOrderRoutePlanStop(BaseModel):
    stop_sequence: int
    order_id: int
    woo_order_id: int | None = None
    woo_order_number: str | None = None
    local_status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    order_total: float | None = None
    address: str
    postal_area: str | None = None
    direction: RouteDirection
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source: str | None = None


class OpenOrderRouteExcludedOrder(BaseModel):
    order_id: int
    woo_order_number: str | None = None
    customer_name: str | None = None
    address: str | None = None
    postal_area: str | None = None
    direction: RouteDirection | None = None
    reason_code: str = "unavailable"
    reason: str


class GoogleMapsRouteLink(BaseModel):
    part_number: int
    label: str
    url: str
    stop_sequence_from: int | None = None
    stop_sequence_to: int | None = None
    stop_count: int = 0
    returns_to_start: bool = False


class DriverOpenOrderRoutePlan(BaseModel):
    driver_number: int
    driver_label: str
    stop_count: int
    estimated_duration_minutes: int = 0
    directions: list[RouteDirection] = Field(default_factory=list)
    stops: list[OpenOrderRoutePlanStop] = Field(default_factory=list)
    google_maps_links: list[GoogleMapsRouteLink] = Field(default_factory=list)


class OpenOrderRouteMapSummary(BaseModel):
    provider: str
    configured: bool
    coordinate_count: int = 0
    missing_coordinate_count: int = 0


class OpenOrderRoutePlanResponse(BaseModel):
    start_address: str
    requested_driver_count: int
    effective_driver_count: int
    total_open_orders: int
    available_order_count: int
    selected_order_count: int
    routable_order_count: int
    assigned_order_count: int
    unassigned_order_count: int
    excluded_order_count: int
    return_to_start: bool
    assignment_method: str
    estimate_basis: str
    total_estimated_duration_minutes: int = 0
    estimated_completion_minutes: int = 0
    zones: list[RouteDirection] = Field(default_factory=list)
    map: OpenOrderRouteMapSummary
    available_orders: list[OpenOrderRouteCandidate] = Field(default_factory=list)
    drivers: list[DriverOpenOrderRoutePlan] = Field(default_factory=list)
    excluded_orders: list[OpenOrderRouteExcludedOrder] = Field(default_factory=list)
    unassigned_orders: list[OpenOrderRouteExcludedOrder] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    start_address: str | None = None
    end_address: str | None = None
    total_stops: int
    total_distance: float | None = None
    estimated_duration_minutes: int | None = None
    map_provider: str | None = None
    optimization_status: str | None = None
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
