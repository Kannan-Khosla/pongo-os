from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import case, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.orders import Order
from app.models.woocommerce import WooCommerceSyncRun
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.metric_cache import invalidate_metrics
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_orders import commit_remote_order_records

logger = logging.getLogger(__name__)

SCHEDULER_CREATED_BY = "server-order-reconciliation"
ORDER_JOB_SYNC_TYPE = "order_job"
ORDER_HISTORY_SYNC_TYPE = "order_history_v1"
SUCCESS_STATUSES = {"completed", "completed_with_errors"}
DEFAULT_STATUSES = ["processing", "on-hold", "pending", "completed", "failed", "cancelled", "refunded"]
ACTIVE_STATUSES = {"processing", "on-hold", "pending"}
HISTORY_STATUSES = ["any"]
BATCH_SIZE = 25
HISTORY_BATCH_SIZE = 100
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


def enqueue_order_history_import(
    db: Session,
    requested_by: str,
    settings: Any,
    *,
    now: datetime | None = None,
) -> WooCommerceSyncRun:
    effective_settings = effective_woocommerce_settings(db, settings)
    if not getattr(effective_settings, "woocommerce_read_enabled", True):
        raise ValueError("WooCommerce reads are disabled.")
    if not reconciliation_is_configured(effective_settings):
        raise ValueError("WooCommerce credentials are not configured.")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": POSTGRES_ORDER_JOB_QUEUE_LOCK_KEY + 1})
    latest = db.scalars(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.sync_type == ORDER_HISTORY_SYNC_TYPE)
        .order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
    ).first()
    source_url = str(getattr(effective_settings, "woocommerce_base_url", "")).rstrip("/")
    if latest is not None and latest.status in {"queued", "running"}:
        return latest
    if latest is not None and latest.status == "failed" and (latest.progress or {}).get("source_base_url") == source_url:
        progress = dict(latest.progress or {})
        progress["transport_retry_count"] = 0
        progress["last_error"] = None
        latest.progress = progress
        latest.status = "queued"
        latest.completed_at = None
        latest.notes = "Historical order import resumed from its last committed WooCommerce page."
        db.commit()
        db.refresh(latest)
        return latest

    current_time = as_utc(now or datetime.now(timezone.utc))
    job = WooCommerceSyncRun(
        sync_type=ORDER_HISTORY_SYNC_TYPE,
        status="queued",
        started_at=current_time,
        created_by=requested_by[:120],
        notes="Full read-only WooCommerce order history import queued.",
        progress={
            "source_base_url": source_url,
            "snapshot_before": current_time.isoformat().replace("+00:00", "Z"),
            "status_index": 0,
            "current_status": HISTORY_STATUSES[0],
            "next_page": 1,
            "batch_count": 0,
            "batch_size": HISTORY_BATCH_SIZE,
            "transport_retry_count": 0,
            "coverage_complete": False,
            "status_total_records": {},
            "status_total_pages": {},
            "seen_order_ids": [],
            "distinct_remote_records": 0,
            "earliest_remote_order_at": None,
            "latest_remote_order_at": None,
            "last_error": None,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def recover_stale_order_history_jobs(db: Session, settings: Any, *, now: datetime | None = None) -> int:
    current_time = as_utc(now or datetime.now(timezone.utc))
    stale_seconds = max(900, int(getattr(settings, "woocommerce_order_reconciliation_stale_after_seconds", 300)))
    recovered = 0
    for job in db.scalars(
        select(WooCommerceSyncRun).where(
            WooCommerceSyncRun.sync_type == ORDER_HISTORY_SYNC_TYPE,
            WooCommerceSyncRun.status == "running",
        )
    ).all():
        heartbeat = progress_datetime((job.progress or {}).get("heartbeat_at")) or as_utc(job.started_at)
        if current_time - heartbeat <= timedelta(seconds=stale_seconds):
            continue
        progress = dict(job.progress or {})
        progress["last_error"] = "Recovered after the previous worker stopped during this page."
        job.progress = progress
        job.status = "queued"
        job.notes = "Historical order import recovered at its last committed WooCommerce page."
        recovered += 1
    if recovered:
        db.commit()
    return recovered


def process_next_order_history_import(
    settings: Any,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    client_factory: Callable[[Any], Any] = WooCommerceClient,
) -> dict[str, Any] | None:
    with session_factory() as db:
        effective_settings = effective_woocommerce_settings(db, settings)
        recover_stale_order_history_jobs(db, effective_settings)
        statement = (
            select(WooCommerceSyncRun)
            .where(
                WooCommerceSyncRun.sync_type == ORDER_HISTORY_SYNC_TYPE,
                WooCommerceSyncRun.status == "queued",
            )
            .order_by(WooCommerceSyncRun.started_at, WooCommerceSyncRun.id)
        )
        if db.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        job = db.scalars(statement).first()
        if job is None:
            return None
        progress = dict(job.progress or {})
        progress["heartbeat_at"] = utc_iso(datetime.now(timezone.utc))
        job.progress = progress
        job.status = "running"
        job.completed_at = None
        job.notes = "Historical order import is reading one WooCommerce page."
        job_id = job.id
        db.commit()
    return run_order_history_import_batch(
        settings,
        job_id,
        session_factory=session_factory,
        client_factory=client_factory,
    )


def run_order_history_import_batch(
    settings: Any,
    job_id: int,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    client_factory: Callable[[Any], Any] = WooCommerceClient,
) -> dict[str, Any]:
    try:
        with session_factory() as db:
            effective_settings = effective_woocommerce_settings(db, settings)
            job = db.get(WooCommerceSyncRun, job_id)
            if job is None or job.sync_type != ORDER_HISTORY_SYNC_TYPE:
                return {"status": "failed", "sync_run_id": job_id, "error": "Historical order import job was not found."}
            if not getattr(effective_settings, "woocommerce_read_enabled", True):
                return fail_order_history_import(db, job, "WooCommerce reads are disabled.")
            if not reconciliation_is_configured(effective_settings):
                return fail_order_history_import(db, job, "WooCommerce credentials are not configured.")
            progress = dict(job.progress or {})
            source_url = str(getattr(effective_settings, "woocommerce_base_url", "")).rstrip("/")
            if progress.get("source_base_url") != source_url:
                return fail_order_history_import(db, job, "WooCommerce store changed after this history import began.")
            status_index = int(progress.get("status_index", 0))
            if status_index >= len(HISTORY_STATUSES):
                return finish_order_history_import(db, job, progress)
            status = HISTORY_STATUSES[status_index]
            page = max(1, int(progress.get("next_page", 1)))
            batch_size = max(1, min(100, int(progress.get("batch_size") or BATCH_SIZE)))
            snapshot_before = str(progress.get("snapshot_before") or "")
            requested_by = job.created_by or "historical-order-import"

        client = client_factory(effective_settings)
        remote_orders = client.list_orders(
            page=page,
            per_page=batch_size,
            status=status,
            before=snapshot_before,
        )
        total_pages, total_records = woo_pagination(getattr(client, "last_response_headers", {}))

        with session_factory() as db:
            job = db.get(WooCommerceSyncRun, job_id)
            if job is None:
                raise RuntimeError("Historical order import job disappeared.")
            progress = dict(job.progress or {})
            if remote_orders:
                seen_order_ids = {int(value) for value in progress.get("seen_order_ids") or []}
                seen_order_ids.update(
                    int(order["id"])
                    for order in remote_orders
                    if order.get("id") is not None
                )
                progress["seen_order_ids"] = sorted(seen_order_ids)
                progress["distinct_remote_records"] = len(seen_order_ids)
                requested_statuses = sorted({
                    str(order.get("status") or "").strip()
                    for order in remote_orders
                    if str(order.get("status") or "").strip()
                }) or DEFAULT_STATUSES
                page_run, _summary = commit_remote_order_records(
                    db,
                    remote_orders,
                    requested_statuses,
                    requested_by,
                    commit=False,
                    snapshot_only=True,
                )
                for key in (
                    "total_remote_records",
                    "created_count",
                    "updated_count",
                    "matched_count",
                    "skipped_count",
                    "conflict_count",
                    "error_count",
                ):
                    setattr(job, key, int(getattr(job, key) or 0) + int(getattr(page_run, key) or 0))
                update_history_date_coverage(progress, remote_orders)

            progress["batch_count"] = int(progress.get("batch_count", 0)) + 1
            progress["transport_retry_count"] = 0
            progress["last_error"] = None
            progress["heartbeat_at"] = utc_iso(datetime.now(timezone.utc))
            if total_records is not None:
                status_totals = dict(progress.get("status_total_records") or {})
                previous_total = status_totals.get(status)
                if previous_total is not None and int(previous_total) != total_records:
                    progress["pagination_changed"] = True
                else:
                    status_totals[status] = total_records
                progress["status_total_records"] = status_totals
            if total_pages is not None:
                status_pages = dict(progress.get("status_total_pages") or {})
                previous_pages = status_pages.get(status)
                if previous_pages is not None and int(previous_pages) != total_pages:
                    progress["pagination_changed"] = True
                else:
                    status_pages[status] = total_pages
                progress["status_total_pages"] = status_pages
            status_complete = page >= total_pages if total_pages is not None else len(remote_orders) < batch_size
            if status_complete:
                status_index += 1
                progress["status_index"] = status_index
                progress["next_page"] = 1
                progress["current_status"] = HISTORY_STATUSES[status_index] if status_index < len(HISTORY_STATUSES) else None
            else:
                progress["next_page"] = page + 1
                progress["current_status"] = status
            job.progress = progress
            if status_index >= len(HISTORY_STATUSES):
                return finish_order_history_import(db, job, progress)
            job.status = "queued"
            job.notes = f"Historical order page committed; next: {progress['current_status']} page {progress['next_page']}."
            db.commit()
            db.refresh(job)
            return history_job_result(job)
    except Exception as error:
        message = str(error)[:1000] or error.__class__.__name__
        logger.error("WooCommerce historical order import failed: %s", message)
        with session_factory() as db:
            job = db.get(WooCommerceSyncRun, job_id)
            if job is None:
                return {"status": "failed", "sync_run_id": job_id, "error": message}
            progress = dict(job.progress or {})
            attempts = int(progress.get("transport_retry_count", 0)) + 1
            progress["transport_retry_count"] = attempts
            progress["last_error"] = message
            progress["heartbeat_at"] = utc_iso(datetime.now(timezone.utc))
            job.progress = progress
            if attempts < 3:
                job.status = "queued"
                job.notes = f"Historical order page failed; automatic retry {attempts} of 3 is queued."
            else:
                job.status = "failed"
                job.error_count = int(job.error_count or 0) + 1
                job.completed_at = datetime.now(timezone.utc)
                job.notes = f"Historical order import paused after 3 failed attempts: {message}"[:1000]
            db.commit()
            db.refresh(job)
            return history_job_result(job)


def finish_order_history_import(db: Session, job: WooCommerceSyncRun, progress: dict[str, Any]) -> dict[str, Any]:
    status_totals = progress.get("status_total_records") or {}
    totals_verified = all(status in status_totals for status in HISTORY_STATUSES)
    expected_records = sum(int(status_totals[status]) for status in HISTORY_STATUSES) if totals_verified else None
    progress["expected_remote_records"] = expected_records
    progress["coverage_complete"] = bool(
        totals_verified
        and not progress.get("pagination_changed")
        and expected_records == int(job.total_remote_records or 0)
        and expected_records == int(progress.get("distinct_remote_records") or 0)
        and int(job.created_count or 0) + int(job.updated_count or 0) == int(job.total_remote_records or 0)
        and int(job.skipped_count or 0) == 0
    )
    if progress["coverage_complete"]:
        progress["source_absent_snapshot_count"] = reconcile_history_snapshot_presence(
            db,
            {int(value) for value in progress.get("seen_order_ids") or []},
        )
    progress["heartbeat_at"] = utc_iso(datetime.now(timezone.utc))
    job.progress = progress
    job.completed_at = datetime.now(timezone.utc)
    job.status = "completed_with_errors" if job.conflict_count or job.error_count else "completed"
    job.notes = (
        f"Read-only history scan completed in {progress.get('batch_count', 0)} page request(s); "
        f"{job.total_remote_records} order snapshot(s) covered."
    )
    db.commit()
    db.refresh(job)
    return history_job_result(job)


def reconcile_history_snapshot_presence(db: Session, seen_order_ids: set[int]) -> int:
    rows = db.execute(
        select(Order.woo_order_id, Order.historical_source_present).where(
            Order.is_historical_snapshot.is_(True),
            Order.woo_order_id.is_not(None),
        )
    ).all()
    current_ids = {int(order_id) for order_id, present in rows if present}
    historical_ids = {int(order_id) for order_id, _present in rows}
    target_ids = historical_ids & seen_order_ids
    removed_ids = current_ids - target_ids
    restored_ids = target_ids - current_ids
    for ids, present in ((removed_ids, False), (restored_ids, True)):
        values = list(ids)
        for offset in range(0, len(values), 500):
            db.execute(
                update(Order)
                .where(Order.is_historical_snapshot.is_(True), Order.woo_order_id.in_(values[offset:offset + 500]))
                .values(historical_source_present=present)
            )
    if removed_ids or restored_ids:
        invalidate_metrics(db)
    return len(removed_ids)


def fail_order_history_import(db: Session, job: WooCommerceSyncRun, message: str) -> dict[str, Any]:
    progress = dict(job.progress or {})
    progress["last_error"] = message
    progress["coverage_complete"] = False
    job.progress = progress
    job.status = "failed"
    job.error_count = int(job.error_count or 0) + 1
    job.completed_at = datetime.now(timezone.utc)
    job.notes = message[:1000]
    db.commit()
    db.refresh(job)
    return history_job_result(job)


def history_job_result(job: WooCommerceSyncRun) -> dict[str, Any]:
    progress = dict(job.progress or {})
    progress.pop("seen_order_ids", None)
    return {
        "status": job.status,
        "sync_run_id": job.id,
        "total_remote_records": job.total_remote_records,
        "created_count": job.created_count,
        "updated_count": job.updated_count,
        "error_count": job.error_count,
        "progress": progress,
    }


def update_history_date_coverage(progress: dict[str, Any], remote_orders: list[dict[str, Any]]) -> None:
    dates = [
        parsed
        for order in remote_orders
        if (parsed := progress_datetime(order.get("date_created_gmt") or order.get("date_created"))) is not None
    ]
    if not dates:
        return
    earliest = min(dates)
    latest = max(dates)
    current_earliest = progress_datetime(progress.get("earliest_remote_order_at"))
    current_latest = progress_datetime(progress.get("latest_remote_order_at"))
    progress["earliest_remote_order_at"] = utc_iso(min(earliest, current_earliest) if current_earliest else earliest)
    progress["latest_remote_order_at"] = utc_iso(max(latest, current_latest) if current_latest else latest)


def order_history_coverage(db: Session, settings: Any) -> dict[str, Any]:
    source_url = str(getattr(settings, "woocommerce_base_url", "")).rstrip("/")
    runs = list(
        db.scalars(
            select(WooCommerceSyncRun)
            .where(WooCommerceSyncRun.sync_type == ORDER_HISTORY_SYNC_TYPE)
            .order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
            .limit(20)
        ).all()
    )
    latest = runs[0] if runs else None
    verified = next(
        (
            run
            for run in runs
            if (run.progress or {}).get("coverage_complete")
            and (run.progress or {}).get("source_base_url") == source_url
            and run.status in SUCCESS_STATUSES
        ),
        None,
    )
    visible_order_clause = or_(Order.is_historical_snapshot.is_(False), Order.historical_source_present.is_(True))
    count, earliest, latest_date = db.execute(
        select(func.count(Order.id), func.min(Order.date_created), func.max(Order.date_created)).where(visible_order_clause)
    ).one()
    distinct_dates = db.scalar(select(func.count(func.distinct(func.date(Order.date_created)))).where(visible_order_clause)) or 0
    snapshot_count = db.scalar(
        select(func.count(Order.id)).where(
            Order.is_historical_snapshot.is_(True),
            Order.historical_source_present.is_(True),
        )
    ) or 0
    source_absent_count = db.scalar(
        select(func.count(Order.id)).where(
            Order.is_historical_snapshot.is_(True),
            Order.historical_source_present.is_(False),
        )
    ) or 0
    return {
        "verified_complete": verified is not None,
        "latest_status": latest.status if latest else None,
        "latest_job_id": latest.id if latest else None,
        "verified_at": utc_iso(verified.completed_at) if verified and verified.completed_at else None,
        "local_order_count": int(count or 0),
        "historical_snapshot_count": int(snapshot_count),
        "source_absent_snapshot_count": int(source_absent_count),
        "distinct_order_dates": int(distinct_dates),
        "earliest_order_at": utc_iso(earliest) if earliest else None,
        "latest_order_at": utc_iso(latest_date) if latest_date else None,
        "source_matches": bool(latest and (latest.progress or {}).get("source_base_url") == source_url),
    }


def latest_order_history_run(db: Session) -> WooCommerceSyncRun | None:
    return db.scalars(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.sync_type == ORDER_HISTORY_SYNC_TYPE)
        .order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
        .limit(1)
    ).first()


def progress_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return as_utc(parsed)


def woo_pagination(headers: dict[str, Any]) -> tuple[int | None, int | None]:
    normalized = {str(key).casefold(): value for key, value in (headers or {}).items()}
    try:
        total_pages = int(normalized["x-wp-totalpages"])
        total_records = int(normalized["x-wp-total"])
    except (KeyError, TypeError, ValueError):
        return None, None
    return max(total_pages, 0), max(total_records, 0)


def utc_iso(value: datetime) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


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
            # Active orders are a small operational set and must be reconciled
            # in full; relying on Woo's modified cursor can miss a pickable order.
            status_cursor = None if status in ACTIVE_STATUSES else cursor_value
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
