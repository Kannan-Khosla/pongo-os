from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.allocations import AllocationCommitResponse, AllocationDetail, AllocationExceptionListResponse, AllocationListResponse, AllocationPreviewResponse, AllocationRequest, AutoAllocationQueueResponse
from app.services.allocations import allocation_to_read, commit_allocation, export_allocation_csv, get_allocation_detail, list_allocation_exception_lines, list_allocations, preview_allocation
from app.services.order_workflow import auto_allocate_processing_orders_fifo

router = APIRouter(prefix="/allocations", tags=["allocations"])


@router.post("/preview", response_model=AllocationPreviewResponse)
def preview_allocation_request(payload: AllocationRequest, db: Session = Depends(get_db)) -> AllocationPreviewResponse:
    return preview_allocation(db, payload)


@router.post("/commit", response_model=AllocationCommitResponse)
def commit_allocation_request(payload: AllocationRequest, db: Session = Depends(get_db)) -> AllocationCommitResponse:
    return commit_allocation(db, payload)


@router.post("/auto/commit", response_model=AutoAllocationQueueResponse)
def commit_fifo_auto_allocation(db: Session = Depends(get_db)) -> AutoAllocationQueueResponse:
    return AutoAllocationQueueResponse.model_validate(auto_allocate_processing_orders_fifo(db, source="manual-fifo-reconcile", commit=True))


@router.get("/exceptions", response_model=AllocationExceptionListResponse)
def list_allocation_exceptions(
    search: str | None = None,
    warehouse: str | None = None,
    ordered_from: date | None = None,
    ordered_to: date | None = None,
    include_fully_allocated: bool = False,
    db: Session = Depends(get_db),
) -> AllocationExceptionListResponse:
    return list_allocation_exception_lines(
        db,
        search=search,
        warehouse=warehouse,
        ordered_from=ordered_from,
        ordered_to=ordered_to,
        include_fully_allocated=include_fully_allocated,
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
    db: Session = Depends(get_db),
) -> AllocationListResponse:
    allocations = list_allocations(db, status=status, allocation_type=allocation_type, order_id=order_id, woo_order_id=woo_order_id, woo_order_number=woo_order_number, date_from=date_from, date_to=date_to, created_by=created_by)
    return AllocationListResponse(allocations=[allocation_to_read(allocation) for allocation in allocations], total=len(allocations))


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
