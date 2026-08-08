import csv
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.cycle_counts import CycleCount
from app.schemas.cycle_counts import (
    CycleCountCommitResponse,
    CycleCountDetail,
    CycleCountListResponse,
    CycleCountPreviewResponse,
    CycleCountRequest,
)
from app.services.cycle_counts import (
    CYCLE_COUNT_EXPORT_COLUMNS,
    build_cycle_count_preview,
    commit_cycle_count,
    cycle_count_line_to_export_row,
    cycle_count_to_detail,
    cycle_count_to_read,
)
from app.services.auth import authenticated_actor

router = APIRouter(prefix="/cycle-counts", tags=["cycle-counts"])


@router.post("/preview", response_model=CycleCountPreviewResponse)
def preview_cycle_count(payload: CycleCountRequest, db: Session = Depends(get_db)) -> CycleCountPreviewResponse:
    return build_cycle_count_preview(payload, db)


@router.post("/commit", response_model=CycleCountCommitResponse)
def commit_cycle_count_endpoint(payload: CycleCountRequest, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> CycleCountCommitResponse:
    count, movement_count, totals, warnings = commit_cycle_count(payload.model_copy(update={"created_by": actor}), db)
    return CycleCountCommitResponse(
        cycle_count_id=count.id,
        count_number=count.count_number,
        status=count.status,
        total_lines=len(count.lines),
        adjustment_lines=totals["adjustment_lines"],
        total_positive_variance=float(totals["total_positive_variance"]),
        total_negative_variance=float(totals["total_negative_variance"]),
        total_absolute_variance=float(totals["total_absolute_variance"]),
        total_variance_value=float(totals["total_variance_value"]),
        created_movements=movement_count,
        warnings=warnings,
    )


@router.get("", response_model=CycleCountListResponse)
def list_cycle_counts(
    status: str | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    count_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> CycleCountListResponse:
    predicates = []
    if status:
        predicates.append(CycleCount.status == status)
    if warehouse:
        predicates.append(CycleCount.warehouse == warehouse)
    if inventory_location:
        predicates.append(CycleCount.inventory_location == inventory_location)
    if count_type:
        predicates.append(CycleCount.count_type == count_type)
    if date_from:
        predicates.append(CycleCount.created_at >= date_from)
    if date_to:
        predicates.append(CycleCount.created_at <= date_to)
    if created_by:
        predicates.append(CycleCount.created_by == created_by)
    total = int(db.scalar(select(func.count(CycleCount.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    counts = list(
        db.scalars(
            select(CycleCount)
            .where(*predicates)
            .options(selectinload(CycleCount.lines))
            .order_by(CycleCount.created_at.desc(), CycleCount.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return CycleCountListResponse(
        cycle_counts=[cycle_count_to_read(count) for count in counts],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(counts),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/{cycle_count_id}", response_model=CycleCountDetail)
def get_cycle_count(cycle_count_id: int, db: Session = Depends(get_db)) -> CycleCountDetail:
    count = db.scalars(select(CycleCount).where(CycleCount.id == cycle_count_id).options(selectinload(CycleCount.lines))).one_or_none()
    if count is None:
        raise HTTPException(status_code=404, detail="Cycle count not found")
    return cycle_count_to_detail(count)


@router.get("/{cycle_count_id}/export")
def export_cycle_count(cycle_count_id: int, db: Session = Depends(get_db)) -> Response:
    count = db.scalars(select(CycleCount).where(CycleCount.id == cycle_count_id).options(selectinload(CycleCount.lines))).one_or_none()
    if count is None:
        raise HTTPException(status_code=404, detail="Cycle count not found")
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CYCLE_COUNT_EXPORT_COLUMNS)
    writer.writeheader()
    for line in count.lines:
        writer.writerow(cycle_count_line_to_export_row(count, line))
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="pongo-cycle-count-{count.count_number}.csv"'},
    )
