from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.picks import PickCommitRequest, PickCommitResponse, PickDetail, PickListResponse, PickPreviewResponse, PickRequest, PickScanCommitRequest, PickScanRequest, PickScanResponse, PickScannerOrder
from app.services.picks import commit_pick, commit_scan, export_pick_csv, get_pick_detail, get_scanner_order, list_picks_page, pick_to_read, preview_pick, preview_scan
from app.services.auth import authenticated_actor
from app.services.stock_mutation_guard import IdempotencyConflict

router = APIRouter(prefix="/picks", tags=["picks"])


@router.post("/preview", response_model=PickPreviewResponse)
def preview_pick_request(payload: PickRequest, db: Session = Depends(get_db)) -> PickPreviewResponse:
    return preview_pick(db, payload)


@router.post("/commit", response_model=PickCommitResponse)
def commit_pick_request(payload: PickCommitRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> PickCommitResponse:
    try:
        return commit_pick(db, payload.model_copy(update={"created_by": actor}))
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/orders/{order_id}/scanner", response_model=PickScannerOrder)
def get_pick_scanner_order(order_id: int, db: Session = Depends(get_db)) -> PickScannerOrder:
    order = get_scanner_order(db, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/orders/{order_id}/scan/preview", response_model=PickScanResponse)
def preview_pick_scan(order_id: int, payload: PickScanRequest, db: Session = Depends(get_db)) -> PickScanResponse:
    result = preview_scan(db, order_id, payload)
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.post("/orders/{order_id}/scan/commit", response_model=PickScanResponse)
def commit_pick_scan(order_id: int, payload: PickScanCommitRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> PickScanResponse:
    try:
        result = commit_scan(db, order_id, payload.model_copy(update={"created_by": actor}))
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@router.get("", response_model=PickListResponse)
def list_pick_records(
    status: str | None = None,
    pick_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PickListResponse:
    picks, total, effective_page, total_pages = list_picks_page(
        db,
        page=page,
        page_size=page_size,
        status=status,
        pick_type=pick_type,
        order_id=order_id,
        woo_order_id=woo_order_id,
        woo_order_number=woo_order_number,
        date_from=date_from,
        date_to=date_to,
        created_by=created_by,
    )
    return PickListResponse(
        picks=[pick_to_read(pick) for pick in picks],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(picks),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/{pick_id}", response_model=PickDetail)
def get_pick_record(pick_id: int, db: Session = Depends(get_db)) -> PickDetail:
    pick = get_pick_detail(db, pick_id)
    if pick is None:
        raise HTTPException(status_code=404, detail="Pick not found")
    return pick


@router.get("/{pick_id}/export")
def export_pick_record(pick_id: int, db: Session = Depends(get_db)) -> Response:
    csv_text = export_pick_csv(db, pick_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Pick not found")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-pick-export.csv"'},
    )
