from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.reporting import ReportJob, ReportRun
from app.services.reporting import (
    DEFINITION_VERSION,
    REPORTS_BY_KEY,
    create_report_run_record,
    get_report_run,
    normalize_filters,
    persist_report_artifacts,
)

POSTGRES_REPORT_WORKER_LOCK_KEY = 8172620033
REPORT_JOB_STALE_AFTER = timedelta(minutes=15)
REPORT_JOB_MAX_ATTEMPTS = 3


def normalized_report_request(report_key: str, raw_filters: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    definition = REPORTS_BY_KEY.get(report_key)
    if not definition:
        raise KeyError(report_key)
    filters = normalize_filters(raw_filters or {}, definition["date_mode"])
    encoded = json.dumps(
        {"definition_version": DEFINITION_VERSION, "filters": filters, "report_key": report_key},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return filters, sha256(encoded).hexdigest()


def report_job_to_dict(job: ReportJob, *, deduplicated: bool = False) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "report_key": job.report_key,
        "status": job.status,
        "progress": job.progress,
        "run_id": job.run_id,
        "previous_run_id": job.previous_run_id,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "deduplicated": deduplicated,
    }


def enqueue_report_job(
    db: Session,
    report_key: str,
    raw_filters: dict[str, Any] | None,
    generated_by: str | None,
) -> tuple[ReportJob, bool]:
    filters, request_key = normalized_report_request(report_key, raw_filters)
    active = db.scalar(
        select(ReportJob)
        .where(ReportJob.request_key == request_key, ReportJob.status.in_({"queued", "running"}))
        .order_by(ReportJob.created_at, ReportJob.id)
    )
    if active is not None:
        return active, True
    previous_run_id = _latest_matching_run_id(db, report_key, filters)
    job = ReportJob(
        report_key=report_key,
        request_key=request_key,
        filters=filters,
        generated_by=generated_by,
        previous_run_id=previous_run_id,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active = db.scalar(
            select(ReportJob)
            .where(ReportJob.request_key == request_key, ReportJob.status.in_({"queued", "running"}))
            .order_by(ReportJob.created_at, ReportJob.id)
        )
        if active is None:
            raise
        return active, True
    db.refresh(job)
    return job, False


def get_report_job(db: Session, job_id: str) -> ReportJob | None:
    return db.get(ReportJob, job_id)


def latest_completed_report_run(
    db: Session,
    report_key: str,
    raw_filters: dict[str, Any] | None,
) -> ReportRun | None:
    filters, _ = normalized_report_request(report_key, raw_filters)
    run_id = _latest_matching_run_id(db, report_key, filters)
    return get_report_run(db, run_id) if run_id else None


def _latest_matching_run_id(db: Session, report_key: str, filters: dict[str, Any]) -> str | None:
    # ponytail: report runs are few; persist request_key on ReportRun if this scan becomes measurable.
    for run_id, stored_filters in db.execute(
        select(ReportRun.id, ReportRun.filters)
        .where(
            ReportRun.report_key == report_key,
            ReportRun.definition_version == DEFINITION_VERSION,
        )
        .order_by(ReportRun.generated_at.desc(), ReportRun.id.desc())
    ):
        if stored_filters == filters:
            return run_id
    return None


def process_next_report_job(*, db_factory=SessionLocal) -> ReportJob | None:
    with db_factory() as db:
        lock_connection = None
        try:
            if db.get_bind().dialect.name == "postgresql":
                lock_connection = db.get_bind().connect()
                if not lock_connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": POSTGRES_REPORT_WORKER_LOCK_KEY},
                ):
                    return None
            return _process_next_report_job(db)
        finally:
            if lock_connection is not None:
                try:
                    lock_connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": POSTGRES_REPORT_WORKER_LOCK_KEY},
                    )
                finally:
                    lock_connection.close()


def _process_next_report_job(db: Session) -> ReportJob | None:
    now = datetime.now(timezone.utc)
    stale_before = now - REPORT_JOB_STALE_AFTER
    job = db.scalar(
        select(ReportJob)
        .where(
            or_(
                ReportJob.status == "queued",
                (ReportJob.status == "running") & (ReportJob.updated_at < stale_before),
            )
        )
        .order_by(ReportJob.created_at, ReportJob.id)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    if job.attempts >= REPORT_JOB_MAX_ATTEMPTS:
        job.status = "failed"
        job.error = "Report generation stopped after repeated worker interruptions."
        job.completed_at = now
        db.commit()
        db.refresh(job)
        return job
    job.status = "running"
    job.progress = 10
    job.attempts += 1
    job.started_at = job.started_at or now
    job.error = None
    db.commit()
    db.refresh(job)
    try:
        run = create_report_run_record(db, job.report_key, job.filters, job.generated_by)
        persist_report_artifacts(run)
        job = db.scalar(select(ReportJob).where(ReportJob.id == job.id).with_for_update())
        job.run_id = run.id
        job.status = "completed"
        job.progress = 100
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as error:
        db.rollback()
        job = db.scalar(select(ReportJob).where(ReportJob.id == job.id).with_for_update())
        job.status = "failed"
        job.error = str(error)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
    db.refresh(job)
    return job
