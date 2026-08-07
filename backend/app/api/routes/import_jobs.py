import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.imports import ImportJob, ImportPreview, ItemImportChange
from app.schemas.imports import ImportJobDetail, ImportJobRead
from app.services.items import CANONICAL_ITEM_COLUMNS
from app.services.item_enrichment import ENRICHMENT_COLUMNS
from app.services.locations import CANONICAL_LOCATION_COLUMNS
from app.services.auth import authenticated_actor
from app.services.item_import_workflow import field_specs_for, rollback_metadata_import

router = APIRouter(prefix="/import-jobs", tags=["import-jobs"])


@router.get("", response_model=list[ImportJobRead])
def list_import_jobs(
    outcome: str | None = Query(None),
    status: str | None = Query(None),
    item_imports_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ImportJob]:
    statement = select(ImportJob)
    if outcome:
        statement = statement.where(ImportJob.outcome == outcome)
    if status:
        statement = statement.where(ImportJob.status == status)
    if item_imports_only:
        statement = statement.where(ImportJob.outcome.in_(["add_items", "update_items", "starting_inventory"]))
    return list(db.scalars(statement.order_by(ImportJob.created_at.desc()).limit(limit)).all())


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
        if job.outcome in {"add_items", "update_items", "starting_inventory"}
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


@router.get("/{job_id}/changes")
def get_import_changes(job_id: int, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(ImportJob, job_id) is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    rows = db.scalars(select(ItemImportChange).where(ItemImportChange.import_job_id == job_id).order_by(ItemImportChange.item_id, ItemImportChange.id)).all()
    return [
        {
            "id": row.id,
            "item_id": row.item_id,
            "sku": row.sku,
            "field": row.field_name,
            "before": row.previous_value,
            "after": row.new_value,
            "source_filename": row.source_filename,
            "created_by": row.created_by,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/{job_id}/rollback")
def rollback_import(job_id: int, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return rollback_metadata_import(job, db, actor=actor)
