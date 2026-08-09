from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.routes import OpenOrderRoutePlanRequest, OpenOrderRoutePlanResponse, RouteCandidateListResponse, RouteCommitResponse, RouteDetail, RouteListResponse, RouteMapPayload, RoutePreviewResponse, RouteProviderPreviewResponse, RouteReorderRequest, RouteRequest, RouteStopUpdateRequest, RouteUpdateRequest
from app.services.routes import (
    cancel_route,
    commit_route,
    commit_route_geocode,
    commit_route_optimization,
    export_route_csv,
    finalize_route,
    get_route_detail,
    get_route_map_payload,
    list_route_candidates,
    list_routes_page,
    plan_open_order_routes,
    preview_route,
    preview_route_geocode,
    preview_route_optimization,
    reorder_route_stops,
    route_to_read,
    update_route_metadata,
    update_route_stop,
)
from app.services.auth import authenticated_actor

router = APIRouter(prefix="/routes", tags=["routes"])


@router.post("/open-orders/plan", response_model=OpenOrderRoutePlanResponse)
def plan_open_order_delivery_routes(
    payload: OpenOrderRoutePlanRequest,
    db: Session = Depends(get_db),
) -> OpenOrderRoutePlanResponse:
    return plan_open_order_routes(db, payload)


@router.get("/candidates", response_model=RouteCandidateListResponse)
def route_candidates(
    route_date: date | None = None,
    local_status: str | None = None,
    customer_email: str | None = None,
    woo_order_number: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RouteCandidateListResponse:
    return list_route_candidates(
        db,
        route_date=route_date,
        local_status=local_status,
        customer_email=customer_email,
        woo_order_number=woo_order_number,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("/preview", response_model=RoutePreviewResponse)
def preview_route_request(payload: RouteRequest, db: Session = Depends(get_db)) -> RoutePreviewResponse:
    return preview_route(db, payload)


@router.post("/commit", response_model=RouteCommitResponse)
def commit_route_request(payload: RouteRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> RouteCommitResponse:
    return commit_route(db, payload.model_copy(update={"created_by": actor}))


@router.get("", response_model=RouteListResponse)
def list_route_records(
    status: str | None = None,
    route_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    driver_name: str | None = None,
    vehicle_name: str | None = None,
    search: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> RouteListResponse:
    routes, total, effective_page, total_pages = list_routes_page(
        db,
        status=status,
        route_date=route_date,
        date_from=date_from,
        date_to=date_to,
        driver_name=driver_name,
        vehicle_name=vehicle_name,
        search=search,
        page=page,
        page_size=page_size,
    )
    return RouteListResponse(
        routes=[route_to_read(route) for route in routes],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(routes),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/{route_id}", response_model=RouteDetail)
def get_route_record(route_id: int, db: Session = Depends(get_db)) -> RouteDetail:
    route = get_route_detail(db, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.patch("/{route_id}", response_model=RouteDetail)
def update_route_record(route_id: int, payload: RouteUpdateRequest, db: Session = Depends(get_db)) -> RouteDetail:
    route = update_route_metadata(db, route_id, payload)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.post("/{route_id}/stops/reorder", response_model=RouteDetail)
def reorder_route_record_stops(route_id: int, payload: RouteReorderRequest, db: Session = Depends(get_db)) -> RouteDetail:
    route, errors = reorder_route_stops(db, route_id, payload)
    if errors:
        raise HTTPException(status_code=400, detail=errors[0])
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.patch("/{route_id}/stops/{stop_id}", response_model=RouteDetail)
def update_route_record_stop(route_id: int, stop_id: int, payload: RouteStopUpdateRequest, db: Session = Depends(get_db)) -> RouteDetail:
    route = update_route_stop(db, route_id, stop_id, payload)
    if route is None:
        raise HTTPException(status_code=404, detail="Route stop not found")
    return route


@router.get("/{route_id}/map", response_model=RouteMapPayload)
def get_route_record_map(route_id: int, db: Session = Depends(get_db)) -> RouteMapPayload:
    payload = get_route_map_payload(db, route_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return payload


@router.post("/{route_id}/geocode/preview", response_model=RouteProviderPreviewResponse)
def preview_route_record_geocode(route_id: int, db: Session = Depends(get_db)) -> RouteProviderPreviewResponse:
    payload = preview_route_geocode(db, route_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return payload


@router.post("/{route_id}/geocode/commit", response_model=RouteProviderPreviewResponse)
def commit_route_record_geocode(route_id: int, db: Session = Depends(get_db)) -> RouteProviderPreviewResponse:
    payload = commit_route_geocode(db, route_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return payload


@router.post("/{route_id}/optimize/preview", response_model=RouteProviderPreviewResponse)
def preview_route_record_optimization(route_id: int, db: Session = Depends(get_db)) -> RouteProviderPreviewResponse:
    payload = preview_route_optimization(db, route_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return payload


@router.post("/{route_id}/optimize/commit", response_model=RouteProviderPreviewResponse)
def commit_route_record_optimization(route_id: int, db: Session = Depends(get_db)) -> RouteProviderPreviewResponse:
    payload = commit_route_optimization(db, route_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return payload


@router.get("/{route_id}/export")
def export_route_record(route_id: int, db: Session = Depends(get_db)) -> Response:
    csv_text = export_route_csv(db, route_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return Response(content=csv_text, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="pongo-route-export.csv"'})


@router.post("/{route_id}/finalize", response_model=RouteCommitResponse)
def finalize_route_record(route_id: int, db: Session = Depends(get_db)) -> RouteCommitResponse:
    result = finalize_route(db, route_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return result


@router.post("/{route_id}/cancel", response_model=RouteCommitResponse)
def cancel_route_record(route_id: int, db: Session = Depends(get_db)) -> RouteCommitResponse:
    result = cancel_route(db, route_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return result
