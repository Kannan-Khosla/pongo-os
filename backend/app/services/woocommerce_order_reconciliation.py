from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import case, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.woocommerce import WooCommerceSyncRun
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_orders import commit_remote_order_records

logger = logging.getLogger(__name__)

SCHEDULER_CREATED_BY = "server-order-reconciliation"
ORDER_JOB_SYNC_TYPE = "order_job"
SUCCESS_STATUSES = {"completed", "completed_with_errors"}
DEFAULT_STATUSES = ["processing", "on-hold", "pending", "completed", "failed", "cancelled", "refunded"]
ACTIVE_STATUSES = {"processing", "on-hold", "pending"}
BATCH_SIZE = 25
POSTGRES_ORDER_JOB_QUEUE_LOCK_KEY = int.from_bytes(b"PONGOQOJ", byteorder="big")
_PROCESS_LOCK = threading.Lock()


def reconciliation_is_configured(settings: Any) -> bool:
    return bool(
        getattr(settings, "woocommerce_base_url", "")
        and getattr(settings, "woocommerce_consumer_key", "")
        and getattr(settings, "woocommerce_consumer_secret", "")
    )


def reconciliation_should_start(settings: Any) -> bool:
    return bool(
        getattr(settings, "woocommerce_order_reconciliation_enabled", False)
        and str(getattr(settings, "app_env", "")).lower() not in {"test", "testing"}
        and not os.environ.get("PYTEST_CURRENT_TEST")
        and getattr(settings, "woocommerce_read_enabled", True)
    )


def enqueue_order_sync_job(
    db: Session,
    requested_by: str,
    *,
    automatic: bool = False,
    now: datetime | None = None,
) -> WooCommerceSyncRun:
    current_time = as_utc(now or datetime.now(timezone.utc))
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": POSTGRES_ORDER_JOB_QUEUE_LOCK_KEY})
    pending = db.scalars(
        select(WooCommerceSyncRun)
        .where(
            WooCommerceSyncRun.sync_type == ORDER_JOB_SYNC_TYPE,
            WooCommerceSyncRun.status.in_({"queued", "running"}),
        )
        .order_by(WooCommerceSyncRun.started_at, WooCommerceSyncRun.id)
    ).first()
    if pending is not None:
        if not automatic and pending.status == "queued" and pending.created_by == SCHEDULER_CREATED_BY:
            pending.created_by = requested_by[:120]
            pending.notes = "Manual order fetch requested; this job has priority."
            db.commit()
            db.refresh(pending)
        return pending

    job = WooCommerceSyncRun(
        sync_type=ORDER_JOB_SYNC_TYPE,
        status="queued",
        started_at=current_time,
        created_by=SCHEDULER_CREATED_BY if automatic else requested_by[:120],
        notes="Automatic two-minute reconciliation queued." if automatic else "Manual order fetch queued.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def ensure_automatic_order_sync_job(db: Session, settings: Any, *, now: datetime | None = None) -> WooCommerceSyncRun | None:
    settings = effective_woocommerce_settings(db, settings)
    if not reconciliation_should_start(settings) or not reconciliation_is_configured(settings):
        return None
    current_time = as_utc(now or datetime.now(timezone.utc))
    recover_stale_order_sync_jobs(db, settings, now=current_time)
    pending = db.scalars(
        select(WooCommerceSyncRun).where(
            WooCommerceSyncRun.sync_type == ORDER_JOB_SYNC_TYPE,
            WooCommerceSyncRun.status.in_({"queued", "running"}),
        )
    ).first()
    if pending is not None:
        return pending
    latest = latest_scheduler_run(db)
    interval = max(15, int(getattr(settings, "woocommerce_order_reconciliation_interval_seconds", 120)))
    latest_at = run_time(latest)
    if latest_at is not None and current_time - latest_at < timedelta(seconds=interval):
        return None
    return enqueue_order_sync_job(db, SCHEDULER_CREATED_BY, automatic=True, now=current_time)


def recover_stale_order_sync_jobs(db: Session, settings: Any, *, now: datetime | None = None) -> int:
    current_time = as_utc(now or datetime.now(timezone.utc))
    stale_seconds = max(900, int(getattr(settings, "woocommerce_order_reconciliation_stale_after_seconds", 300)))
    stale_before = current_time - timedelta(seconds=stale_seconds)
    stale_jobs = list(
        db.scalars(
            select(WooCommerceSyncRun).where(
                WooCommerceSyncRun.sync_type == ORDER_JOB_SYNC_TYPE,
                WooCommerceSyncRun.status == "running",
                WooCommerceSyncRun.started_at < stale_before,
            )
        ).all()
    )
    for job in stale_jobs:
        job.status = "queued"
        job.notes = "Recovered after the previous worker stopped before completing this job."
    if stale_jobs:
        db.commit()
    return len(stale_jobs)


def process_next_order_sync_job(
    settings: Any,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    client_factory: Callable[[Any], Any] = WooCommerceClient,
) -> dict[str, Any] | None:
    with session_factory() as db:
        recover_stale_order_sync_jobs(db, settings)
        priority = case((WooCommerceSyncRun.created_by == SCHEDULER_CREATED_BY, 1), else_=0)
        statement = (
            select(WooCommerceSyncRun)
            .where(
                WooCommerceSyncRun.sync_type == ORDER_JOB_SYNC_TYPE,
                WooCommerceSyncRun.status == "queued",
            )
            .order_by(priority, WooCommerceSyncRun.started_at, WooCommerceSyncRun.id)
        )
        if db.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = db.scalars(statement).first()
        if job is None:
            return None
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.completed_at = None
        job.notes = "WooCommerce order fetch is running."
        job_id = job.id
        db.commit()
    return run_order_reconciliation_once(
        settings,
        session_factory=session_factory,
        client_factory=client_factory,
        job_id=job_id,
    )


def run_order_reconciliation_once(
    settings: Any,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    client_factory: Callable[[Any], Any] = WooCommerceClient,
    now: datetime | None = None,
    job_id: int | None = None,
) -> dict[str, Any]:
    if not getattr(settings, "woocommerce_order_reconciliation_enabled", False):
        return {"status": "disabled"}
    if not getattr(settings, "woocommerce_read_enabled", True):
        return {"status": "not_configured"}
    if not _PROCESS_LOCK.acquire(blocking=False):
        return {"status": "skipped_overlap"}

    started_at = as_utc(now or datetime.now(timezone.utc))
    try:
        with session_factory() as db:
            effective_settings = effective_woocommerce_settings(db, settings)
            if not reconciliation_is_configured(effective_settings):
                if job_id is not None:
                    finish_order_sync_job(db, job_id, "failed", notes="WooCommerce credentials are not configured.")
                return {"status": "not_configured", "sync_run_id": job_id}
            if job_id is None:
                job = WooCommerceSyncRun(
                    sync_type=ORDER_JOB_SYNC_TYPE,
                    status="running",
                    started_at=started_at,
                    created_by=SCHEDULER_CREATED_BY,
                    notes="WooCommerce order fetch is running.",
                )
                db.add(job)
                db.commit()
                db.refresh(job)
                job_id = job.id
            else:
                job = db.get(WooCommerceSyncRun, job_id)
                if job is None:
                    return {"status": "failed", "sync_run_id": job_id, "error": "Order sync job was not found."}
            requested_by = job.created_by or SCHEDULER_CREATED_BY
            previous_success = latest_scheduler_run(db, SUCCESS_STATUSES, exclude_id=job.id)
            modified_after = reconciliation_cursor(effective_settings, started_at, previous_success)
            statuses = list(getattr(effective_settings, "order_reconciliation_statuses", None) or DEFAULT_STATUSES)
            force_active = requested_by != SCHEDULER_CREATED_BY or previous_success is None

        client = client_factory(effective_settings)
        totals = {
            "total_remote_records": 0,
            "created_count": 0,
            "updated_count": 0,
            "matched_count": 0,
            "skipped_count": 0,
            "conflict_count": 0,
            "error_count": 0,
        }
        batch_count = 0
        cursor_value = modified_after.isoformat().replace("+00:00", "Z")
        for status in statuses:
            page = 1
            status_cursor = None if status in ACTIVE_STATUSES and force_active else cursor_value
            while True:
                remote_orders = client.list_orders(
                    page=page,
                    per_page=BATCH_SIZE,
                    status=status,
                    modified_after=status_cursor,
                )
                if not remote_orders:
                    break
                with session_factory() as db:
                    sync_run, _summary = commit_remote_order_records(
                        db,
                        remote_orders,
                        statuses,
                        requested_by,
                    )
                    for key in totals:
                        totals[key] += int(getattr(sync_run, key))
                batch_count += 1
                if len(remote_orders) < BATCH_SIZE:
                    break
                page += 1

        final_status = "completed_with_errors" if totals["conflict_count"] or totals["error_count"] else "completed"
        with session_factory() as db:
            job = db.get(WooCommerceSyncRun, job_id)
            if job is None:
                raise RuntimeError("Order sync job disappeared before completion.")
            for key, value in totals.items():
                setattr(job, key, value)
            job.status = final_status
            job.completed_at = datetime.now(timezone.utc)
            job.notes = f"Remote scan completed in {batch_count} batch(es); local mapping issues remain visible on affected orders."
            db.commit()
            db.refresh(job)
            return {
                "status": job.status,
                "sync_run_id": job.id,
                "total_remote_records": job.total_remote_records,
                "error_count": job.error_count,
            }
    except Exception as error:
        message = str(error)[:1000] or error.__class__.__name__
        logger.error("WooCommerce server order reconciliation failed: %s", message)
        if job_id is not None:
            try:
                with session_factory() as db:
                    finish_order_sync_job(db, job_id, "failed", notes=message, error_count=1)
            except Exception:
                logger.exception("Could not persist the WooCommerce order reconciliation failure.")
        return {"status": "failed", "sync_run_id": job_id, "error": message}
    finally:
        _PROCESS_LOCK.release()


def finish_order_sync_job(
    db: Session,
    job_id: int,
    status: str,
    *,
    notes: str,
    error_count: int = 0,
) -> WooCommerceSyncRun | None:
    job = db.get(WooCommerceSyncRun, job_id)
    if job is None:
        return None
    job.status = status
    job.completed_at = datetime.now(timezone.utc)
    job.error_count = error_count
    job.notes = notes[:1000]
    db.commit()
    db.refresh(job)
    return job


def reconciliation_health(db: Session, settings: Any, *, running: bool = False, now: datetime | None = None) -> dict[str, Any]:
    enabled = bool(getattr(settings, "woocommerce_order_reconciliation_enabled", False))
    configured = reconciliation_is_configured(settings)
    read_enabled = bool(getattr(settings, "woocommerce_read_enabled", True))
    interval = max(15, int(getattr(settings, "woocommerce_order_reconciliation_interval_seconds", 120)))
    stale_after = max(interval * 2, int(getattr(settings, "woocommerce_order_reconciliation_stale_after_seconds", 300)))
    latest_attempt = latest_scheduler_run(db)
    latest_success = latest_scheduler_run(db, SUCCESS_STATUSES)
    latest_failure = latest_scheduler_run(db, {"failed"})
    current_time = as_utc(now or datetime.now(timezone.utc))
    success_at = run_time(latest_success)
    stale = bool(enabled and configured and read_enabled and (success_at is None or current_time - success_at > timedelta(seconds=stale_after)))
    latest_attempt_failed = bool(latest_attempt and latest_attempt.status == "failed")
    degraded = bool(latest_attempt and latest_attempt.status == "completed_with_errors")
    healthy = bool(enabled and configured and read_enabled and running and not stale and not latest_attempt_failed and not degraded)

    if not enabled:
        message = "Server order reconciliation is disabled."
    elif not configured:
        message = "Server order reconciliation is waiting for WooCommerce credentials."
    elif not read_enabled:
        message = "Server order reconciliation cannot run while WooCommerce reads are disabled."
    elif latest_attempt is None:
        message = "The first server order reconciliation is starting."
    elif latest_attempt_failed:
        message = "The last server order reconciliation failed."
    elif latest_attempt.status == "queued":
        message = "Order fetch is queued and waiting for the WooCommerce worker."
    elif not running:
        message = "WooCommerce worker has no recent heartbeat."
    elif degraded:
        message = f"Order fetch succeeded; {latest_attempt.error_count} local mapping issue(s) need review."
    elif stale:
        message = "Server order reconciliation is stale."
    else:
        message = "Server order reconciliation is healthy."

    return {
        "enabled": enabled,
        "running": running,
        "healthy": healthy,
        "degraded": degraded,
        "stale": stale,
        "interval_seconds": interval,
        "stale_after_seconds": stale_after,
        "statuses": list(getattr(settings, "order_reconciliation_statuses", None) or DEFAULT_STATUSES),
        "last_status": latest_attempt.status if latest_attempt else None,
        "error_count": latest_attempt.error_count if latest_attempt else 0,
        "last_attempt_at": run_time(latest_attempt),
        "last_success_at": success_at,
        "last_failure_at": run_time(latest_failure),
        "last_error": latest_attempt.notes if latest_attempt_failed or degraded else (latest_failure.notes if latest_failure else None),
        "message": message,
    }


def order_worker_is_recent(db: Session, settings: Any, *, now: datetime | None = None) -> bool:
    latest = latest_scheduler_run(db)
    if latest is None:
        return False
    current_time = as_utc(now or datetime.now(timezone.utc))
    stale_after = max(
        int(getattr(settings, "woocommerce_order_reconciliation_interval_seconds", 120)) * 3,
        int(getattr(settings, "woocommerce_order_reconciliation_stale_after_seconds", 300)),
    )
    return latest.status in {"running", *SUCCESS_STATUSES} and current_time - as_utc(latest.started_at) <= timedelta(seconds=stale_after)


def reconciliation_cursor(settings: Any, now: datetime, last_success: WooCommerceSyncRun | None) -> datetime:
    fallback = now - timedelta(hours=max(1, int(getattr(settings, "woocommerce_order_reconciliation_lookback_hours", 168))))
    if last_success is None:
        return fallback
    return max(fallback, as_utc(last_success.started_at) - timedelta(seconds=1))


def latest_scheduler_run(
    db: Session,
    statuses: set[str] | None = None,
    *,
    exclude_id: int | None = None,
) -> WooCommerceSyncRun | None:
    statement = select(WooCommerceSyncRun).where(WooCommerceSyncRun.sync_type == ORDER_JOB_SYNC_TYPE)
    if statuses:
        statement = statement.where(WooCommerceSyncRun.status.in_(statuses))
    if exclude_id is not None:
        statement = statement.where(WooCommerceSyncRun.id != exclude_id)
    return db.scalars(statement.order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc()).limit(1)).first()


def run_time(sync_run: WooCommerceSyncRun | None) -> datetime | None:
    if sync_run is None:
        return None
    return as_utc(sync_run.completed_at or sync_run.started_at)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
