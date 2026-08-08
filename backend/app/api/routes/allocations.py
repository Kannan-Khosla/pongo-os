from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.allocations import AllocationCommitResponse, AllocationDetail, AllocationExceptionListResponse, AllocationListResponse, AllocationPreviewResponse, AllocationRequest, AutoAllocationQueueResponse
from app.services.allocations import allocation_to_read, commit_allocation, export_allocation_csv, export_allocation_exceptions_csv, get_allocation_detail, list_allocation_exception_lines, list_allocations_page, preview_allocation
from app.services.auth import authenticated_actor
from app.services.order_workflow import auto_allocate_processing_orders_fifo

router = APIRouter(prefix="/allocations", tags=["allocations"])


@router.post("/preview", response_model=AllocationPreviewResponse)
def preview_allocation_request(payload: AllocationRequest, db: Session = Depends(get_db)) -> AllocationPreviewResponse:
    return preview_allocation(db, payload)


@router.post("/commit", response_model=AllocationCommitResponse)
def commit_allocation_request(payload: AllocationRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> AllocationCommitResponse:
    return commit_allocation(db, payload.model_copy(update={"created_by": actor}))


@router.post("/auto/commit", response_model=AutoAllocationQueueResponse)
def commit_fifo_auto_allocation(db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> AutoAllocationQueueResponse:
    return AutoAllocationQueueResponse.model_validate(auto_allocate_processing_orders_fifo(db, source=actor, commit=True))


@router.get("/exceptions", response_model=AllocationExceptionListResponse)
def list_allocation_exceptions(
    search: str | None = None,
    warehouse: str | None = None,
    ordered_from: date | None = None,
    ordered_to: date | None = None,
    include_fully_allocated: bool = False,
    view: Literal["orders", "items"] = "orders",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    item_id: int | None = Query(default=None, ge=1),
    unmatched_line_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> AllocationExceptionListResponse:
    if item_id is not None and unmatched_line_id is not None:
        raise HTTPException(status_code=422, detail="Only one allocation item-group selector may be provided")
    return list_allocation_exception_lines(
        db,
        search=search,
        warehouse=warehouse,
        ordered_from=ordered_from,
        ordered_to=ordered_to,
        include_fully_allocated=include_fully_allocated,
        view=view,
        page=page,
        page_size=page_size,
        item_id=item_id,
        unmatched_line_id=unmatched_line_id,
    )


@router.get("/exceptions/export")
def export_allocation_exceptions(
    search: str | None = None,
    warehouse: str | None = None,
    ordered_from: date | None = None,
    ordered_to: date | None = None,
    include_fully_allocated: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    csv_text = export_allocation_exceptions_csv(
        db,
        search=search,
        warehouse=warehouse,
        ordered_from=ordered_from,
        ordered_to=ordered_to,
        include_fully_allocated=include_fully_allocated,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-allocation-exceptions.csv"'},
    )


@router.get("", response_model=AllocationListResponse)
def list_allocation_records(
    status: str | None = None,
    allocation_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> AllocationListResponse:
    allocations, total, effective_page, total_pages = list_allocations_page(
        db,
        page=page,
        page_size=page_size,
        status=status,
        allocation_type=allocation_type,
        order_id=order_id,
        woo_order_id=woo_order_id,
        woo_order_number=woo_order_number,
        date_from=date_from,
        date_to=date_to,
        created_by=created_by,
    )
    return AllocationListResponse(
        allocations=[allocation_to_read(allocation) for allocation in allocations],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(allocations),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/{allocation_id}", response_model=AllocationDetail)
def get_allocation_record(allocation_id: int, db: Session = Depends(get_db)) -> AllocationDetail:
    allocation = get_allocation_detail(db, allocation_id)
    if allocation is None:
        raise HTTPException(status_code=404, detail="Allocation not found")
    return allocation


@router.get("/{allocation_id}/export")
def export_allocation_record(allocation_id: int, db: Session = Depends(get_db)) -> Response:
    csv_text = export_allocation_csv(db, allocation_id)
    if csv_text is None:
        raise HTTPException(status_code=404, detail="Allocation not found")
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="pongo-allocation-export.csv"'},
    )
