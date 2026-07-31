from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.fulfillments import FulfillmentCommitResponse, FulfillmentDetail, FulfillmentListResponse, FulfillmentPreviewResponse, FulfillmentRequest
from app.services.fulfillments import commit_fulfillment, export_fulfillment_csv, fulfillment_to_read, get_fulfillment_detail, list_fulfillments, preview_fulfillment
from app.services.auth import authenticated_actor

router = APIRouter(prefix="/fulfillments", tags=["fulfillments"])


@router.post("/preview", response_model=FulfillmentPreviewResponse)
def preview_fulfillment_request(payload: FulfillmentRequest, db: Session = Depends(get_db)) -> FulfillmentPreviewResponse:
    return preview_fulfillment(db, payload)


@router.post("/commit", response_model=FulfillmentCommitResponse)
def commit_fulfillment_request(payload: FulfillmentRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> FulfillmentCommitResponse:
    return commit_fulfillment(db, payload.model_copy(update={"created_by": actor}))


@router.get("", response_model=FulfillmentListResponse)
def list_fulfillment_records(
    status: str | None = None,
    fulfillment_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
    db: Session = Depends(get_db),
) -> FulfillmentListResponse:
    fulfillments = list_fulfillments(db, status=status, fulfillment_type=fulfillment_type, order_id=order_id, woo_order_id=woo_order_id, woo_order_number=woo_order_number, date_from=date_from, date_to=date_to, created_by=created_by)
    return FulfillmentListResponse(fulfillments=[fulfillment_to_read(fulfillment) for fulfillment in fulfillments], total=len(fulfillments))


@router.get("/{fulfillment_id}", response_model=FulfillmentDetail)
def get_fulfillment_record(fulfillment_id: int, db: Session = Depends(get_db)) -> FulfillmentDetail:
    fulfillment = get_fulfillment_detail(db, fulfillment_id)
    if fulfillment is None:
        raise HTTPException(status_code=404, detail="Fulfillment not found")
    return fulfillment


@router.get("/{fulfillment_id}/export")
def export_fulfillment_record(fulfillment_id: int, db: Session = Depends(get_db)) -> Response:
    csv_text = export_fulfillment_csv(db, fulfillment_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Fulfillment not found")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-fulfillment-export.csv"'},
    )
