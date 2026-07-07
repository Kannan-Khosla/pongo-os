import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models.imports import ImportJob
from app.schemas.imports import ImportJobDetail, ImportJobRead
from app.services.items import CANONICAL_ITEM_COLUMNS
from app.services.locations import CANONICAL_LOCATION_COLUMNS

router = APIRouter(prefix="/import-jobs", tags=["import-jobs"])


@router.get("", response_model=list[ImportJobRead])
def list_import_jobs(db: Session = Depends(get_db)) -> list[ImportJob]:
    return list(db.scalars(select(ImportJob).order_by(ImportJob.created_at.desc())).all())


@router.get("/{job_id}", response_model=ImportJobDetail)
def get_import_job(job_id: int, db: Session = Depends(get_db)) -> ImportJob:
    job = db.scalars(select(ImportJob).where(ImportJob.id == job_id).options(selectinload(ImportJob.errors))).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.get("/{job_id}/failed-rows")
def download_failed_rows(job_id: int, db: Session = Depends(get_db)) -> Response:
    job = db.scalars(select(ImportJob).where(ImportJob.id == job_id).options(selectinload(ImportJob.errors))).one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Import job not found")

    canonical_columns = CANONICAL_LOCATION_COLUMNS if job.import_type == "locations" else CANONICAL_ITEM_COLUMNS
    fieldnames = [*canonical_columns, "Error Message"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for error in job.errors:
        row = {column: (error.raw_row or {}).get(column, "") for column in canonical_columns}
        row["Error Message"] = error.error_message or ""
        writer.writerow(row)
    file_prefix = "locations-import" if job.import_type == "locations" else "items-import"

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_prefix}-{job_id}-failed-rows.csv"'},
    )
