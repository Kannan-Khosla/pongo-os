import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.imports import ImportJob, ImportPreview, ItemImportChange
from app.schemas.imports import ImportChangeListResponse, ImportChangeRead, ImportJobDetail, ImportJobListResponse, ImportJobRead
from app.services.items import CANONICAL_ITEM_COLUMNS
from app.services.item_enrichment import ENRICHMENT_COLUMNS
from app.services.locations import CANONICAL_LOCATION_COLUMNS
from app.services.auth import authenticated_actor
from app.services.item_import_workflow import field_specs_for, rollback_metadata_import

router = APIRouter(prefix="/import-jobs", tags=["import-jobs"])


@router.get("", response_model=list[ImportJobRead] | ImportJobListResponse)
def list_import_jobs(
    outcome: str | None = Query(None),
    status: str | None = Query(None),
    item_imports_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ImportJob] | ImportJobListResponse:
    predicates = []
    if outcome:
        predicates.append(ImportJob.outcome == outcome)
    if status:
        predicates.append(ImportJob.status == status)
    if item_imports_only:
        predicates.append(ImportJob.outcome.in_(["add_items", "update_items", "update_stock", "starting_inventory"]))
    ordering = (ImportJob.created_at.desc(), ImportJob.id.desc())
    if page is None and page_size is None:
        return list(db.scalars(select(ImportJob).where(*predicates).order_by(*ordering).limit(limit)).all())

    requested_page = page or 1
    requested_page_size = page_size or 50
    total = int(db.scalar(select(func.count(ImportJob.id)).where(*predicates)) or 0)
    total_pages = (total + requested_page_size - 1) // requested_page_size if total else 0
    effective_page = min(requested_page, max(total_pages, 1))
    jobs = list(
        db.scalars(
            select(ImportJob)
            .where(*predicates)
            .order_by(*ordering)
            .offset((effective_page - 1) * requested_page_size)
            .limit(requested_page_size)
        ).all()
    )
    return ImportJobListResponse(
        jobs=[ImportJobRead.model_validate(job) for job in jobs],
        total=total,
        page=effective_page,
        page_size=requested_page_size,
        total_pages=total_pages,
        returned_count=len(jobs),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.get("/{job_id}", response_model=ImportJobDetail)
def get_import_job(job_id: int, db: Session = Depends(get_db)) -> ImportJob:
    job = db.scalars(select(ImportJob).where(ImportJob.id == job_id).options(selectinload(ImportJob.errors))).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.get("/{job_id}/source-file")
def download_source_file(job_id: int, db: Session = Depends(get_db)) -> Response:
    job = db.get(ImportJob, job_id)
    if job is None or not job.preview_id:
        raise HTTPException(status_code=404, detail="Source file not available")
    preview = db.get(ImportPreview, job.preview_id)
    if preview is None:
        raise HTTPException(status_code=404, detail="Source file not available")
    return Response(content=preview.source_file_text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{preview.file_name}"'})


@router.get("/{job_id}/failed-rows")
def download_failed_rows(job_id: int, db: Session = Depends(get_db)) -> Response:
    job = db.scalars(select(ImportJob).where(ImportJob.id == job_id).options(selectinload(ImportJob.errors))).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    canonical_columns = (
        [spec["label"] for spec in field_specs_for(job.outcome)]
        if job.outcome in {"add_items", "update_items", "update_stock", "starting_inventory"}
        else (ENRICHMENT_COLUMNS if str(job.import_type or "").startswith("items_enrichment") else (CANONICAL_LOCATION_COLUMNS if job.import_type == "locations" else CANONICAL_ITEM_COLUMNS))
    )
    fieldnames = [*canonical_columns, "Error Code", "Error Field", "Error Message", "Suggested action"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for error in job.errors:
        row = {column: (error.raw_row or {}).get(column, "") for column in canonical_columns}
        row["Error Code"] = error.error_code or ""
        row["Error Field"] = error.field_name or ""
        row["Error Message"] = error.error_message or ""
        row["Suggested action"] = error.suggested_action or ""
        writer.writerow(row)
    file_prefix = "items-enrichment" if str(job.import_type or "").startswith("items_enrichment") else ("locations-import" if job.import_type == "locations" else "items-import")

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_prefix}-{job_id}-failed-rows.csv"'},
    )


@router.get("/{job_id}/changes", response_model=ImportChangeListResponse)
def get_import_changes(
    job_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ImportChangeListResponse:
    if db.get(ImportJob, job_id) is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    predicates = [ItemImportChange.import_job_id == job_id]
    total = int(db.scalar(select(func.count(ItemImportChange.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    rows = list(
        db.scalars(
            select(ItemImportChange)
            .where(*predicates)
            .order_by(ItemImportChange.item_id.asc(), ItemImportChange.id.asc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    changes = [
        ImportChangeRead(
            id=row.id,
            item_id=row.item_id,
            sku=row.sku,
            field=row.field_name,
            before=row.previous_value,
            after=row.new_value,
            source_filename=row.source_filename,
            created_by=row.created_by,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ImportChangeListResponse(
        changes=changes,
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(changes),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


@router.post("/{job_id}/rollback")
def rollback_import(job_id: int, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return rollback_metadata_import(job, db, actor=actor)
