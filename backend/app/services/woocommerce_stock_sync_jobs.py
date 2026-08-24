from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.models.inventory import InventoryItem
from app.models.woocommerce import WooStockSyncJob
from app.schemas.woocommerce import WooStockSyncJobListResponse, WooStockSyncJobRead, WooStockSyncRequest
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_writeback import sync_inventory_stock
from app.services.operations_alerts import send_operations_alert

ACTIVE_JOB_STATUSES = {"queued", "running", "cancelling"}
DAILY_FULL_STOCK_SYNC_REQUESTED_BY = "daily-midnight-stock-sync"
POSTGRES_STOCK_JOB_WORKER_LOCK_KEY = int.from_bytes(b"PONGOWBJ", byteorder="big")
logger = logging.getLogger(__name__)
_worker_health = {
    "last_attempt_at": None,
    "last_success_at": None,
    "last_failure_at": None,
    "error_count": 0,
    "last_error": None,
}


def create_stock_sync_job(db: Session, payload: WooStockSyncRequest) -> WooStockSyncJob:
    target_item_ids = normalized_target_item_ids(payload.item_ids)
    existing = db.scalar(select(WooStockSyncJob).where(WooStockSyncJob.idempotency_key == payload.idempotency_key))
    if existing:
        if (
            existing.force != payload.force
            or existing.chunk_size != payload.chunk_size
            or normalized_target_item_ids(existing.target_item_ids) != target_item_ids
        ):
            raise ValueError("Idempotency key was already used for a different stock sync request.")
        return existing
    total_statement = select(func.count(InventoryItem.id)).where(
        InventoryItem.active.is_(True),
        InventoryItem.non_inventory.is_not(True),
    )
    if target_item_ids is not None:
        total_statement = total_statement.where(InventoryItem.id.in_(target_item_ids))
    total = int(db.scalar(total_statement) or 0)
    job = WooStockSyncJob(
        idempotency_key=payload.idempotency_key,
        status="queued",
        force=payload.force,
        requested_by=payload.requested_by or "inventory-page",
        target_item_ids=target_item_ids,
        chunk_size=payload.chunk_size,
        total_items=total,
        errors=[],
        retry_item_ids=[],
        terminal_failed_item_ids=[],
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = db.scalar(select(WooStockSyncJob).where(WooStockSyncJob.idempotency_key == payload.idempotency_key))
        if existing is None:
            raise
        if (
            existing.force != payload.force
            or existing.chunk_size != payload.chunk_size
            or normalized_target_item_ids(existing.target_item_ids) != target_item_ids
        ):
            raise ValueError("Idempotency key was already used for a different stock sync request.") from exc
        return existing
    db.refresh(job)
    return job


def ensure_daily_full_stock_sync_job(db: Session, settings: Settings, *, now: datetime | None = None) -> WooStockSyncJob | None:
    if not getattr(settings, "woocommerce_daily_full_stock_sync_enabled", True) or str(settings.app_env).casefold() == "test":
        return None
    settings = effective_woocommerce_settings(db, settings)
    if getattr(settings, "woocommerce_read_only", True) or not getattr(settings, "woocommerce_writeback_enabled", False) or not getattr(settings, "woocommerce_allow_stock_write", False):
        return None
    try:
        local_now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(getattr(settings, "admin_timezone", "America/Edmonton")))
    except ZoneInfoNotFoundError:
        logger.error("Daily WooCommerce stock sync skipped because ADMIN_TIMEZONE is invalid.")
        return None
    previous = db.scalar(
        select(WooStockSyncJob)
        .where(WooStockSyncJob.requested_by == DAILY_FULL_STOCK_SYNC_REQUESTED_BY)
        .order_by(WooStockSyncJob.created_at.desc(), WooStockSyncJob.id.desc())
        .limit(1)
    )
    if previous is None and local_now.hour != 0:
        return None
    return create_stock_sync_job(
        db,
        WooStockSyncRequest(
            force=True,
            requested_by=DAILY_FULL_STOCK_SYNC_REQUESTED_BY,
            idempotency_key=f"daily-full-stock-{local_now.date().isoformat()}",
        ),
    )


def process_next_stock_sync_job(settings: Settings, *, db_factory=SessionLocal, client_factory=WooCommerceClient) -> WooStockSyncJob | None:
    with db_factory() as db:
        lock_connection = None
        try:
            if db.get_bind().dialect.name == "postgresql":
                lock_connection = db.get_bind().connect()
                if not lock_connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": POSTGRES_STOCK_JOB_WORKER_LOCK_KEY},
                ):
                    return None
            return _process_next_stock_sync_job(db, settings, client_factory)
        finally:
            if lock_connection is not None:
                try:
                    lock_connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": POSTGRES_STOCK_JOB_WORKER_LOCK_KEY},
                    )
                finally:
                    lock_connection.close()


def _process_next_stock_sync_job(db: Session, settings: Settings, client_factory) -> WooStockSyncJob | None:
    settings = effective_woocommerce_settings(db, settings)
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=getattr(settings, "woocommerce_stock_sync_job_stale_seconds", 900))
    job = db.scalar(
        select(WooStockSyncJob)
        .where(or_(
            WooStockSyncJob.status == "queued",
            (WooStockSyncJob.status == "running") & (WooStockSyncJob.updated_at < stale_before),
        ))
        .order_by(WooStockSyncJob.created_at, WooStockSyncJob.id)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = "running"
    job.started_at = job.started_at or now
    db.commit()
    db.refresh(job)
    retry_ids = list(job.retry_item_ids or [])
    if retry_ids:
        item_ids = retry_ids
    else:
        item_statement = select(InventoryItem.id).where(
            InventoryItem.active.is_(True),
            InventoryItem.non_inventory.is_not(True),
            InventoryItem.id > job.last_item_id,
        )
        if job.target_item_ids is not None:
            item_statement = item_statement.where(InventoryItem.id.in_(job.target_item_ids))
        item_ids = list(
            db.scalars(
                item_statement.order_by(InventoryItem.id).limit(job.chunk_size)
            ).all()
        )
        if item_ids:
            job.last_item_id = item_ids[-1]
            job.processed_items = min(job.total_items, job.processed_items + len(item_ids))
            # Absolute stock writes are retry-safe. Persist the in-flight chunk
            # before contacting Woo so a crashed worker can replay it.
            job.retry_item_ids = item_ids
            db.commit()
            db.refresh(job)
    if not item_ids:
        job.status = "completed_with_errors" if job.failed_count else "completed"
        job.completed_at = now
        db.commit()
        db.refresh(job)
        return job

    def cancellation_requested() -> bool:
        status = db.scalar(
            select(WooStockSyncJob.status)
            .where(WooStockSyncJob.id == job.id)
            .execution_options(populate_existing=True)
        )
        return status == "cancelling"

    try:
        result = sync_inventory_stock(
            db,
            settings,
            client_factory(settings),
            item_ids=item_ids,
            force=job.force,
            requested_by=job.requested_by or "stock-sync-job",
            should_cancel=cancellation_requested,
        )
        job = db.scalar(
            select(WooStockSyncJob)
            .where(WooStockSyncJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        cancelling = job.status == "cancelling" or result.status == "cancelled"
        if cancelling:
            job.sent_count += result.sent_count
            job.dry_run_count += result.dry_run_count
            if not retry_ids:
                job.skipped_unmapped_count += result.skipped_unmapped_count
                job.unchanged_count += result.unchanged_count
            terminal_failures = list(dict.fromkeys([*(job.terminal_failed_item_ids or []), *result.failed_item_ids]))
            job.terminal_failed_item_ids = terminal_failures
            job.failed_count = len(terminal_failures)
            if result.errors:
                job.errors = [*(job.errors or []), *result.errors][-100:]
                job.last_error = result.errors[-1]
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
            job.retry_item_ids = []
        elif result.status == "disabled":
            job.status = "paused"
            job.last_error = result.errors[0] if result.errors else "WooCommerce stock writeback is disabled."
        else:
            job.sent_count += result.sent_count
            job.dry_run_count += result.dry_run_count
            if not retry_ids:
                job.skipped_unmapped_count += result.skipped_unmapped_count
                job.unchanged_count += result.unchanged_count
            if result.failed_item_ids and job.retry_attempt < settings.woocommerce_stock_sync_max_retries:
                job.retry_item_ids = result.failed_item_ids
                job.retry_attempt += 1
            else:
                terminal_failures = list(dict.fromkeys([*(job.terminal_failed_item_ids or []), *result.failed_item_ids]))
                job.terminal_failed_item_ids = terminal_failures
                job.failed_count = len(terminal_failures)
                job.retry_item_ids = []
                job.retry_attempt = 0
            if result.errors:
                job.errors = [*(job.errors or []), *result.errors][-100:]
                job.last_error = result.errors[-1]
            if job.status == "running":
                job.status = "queued"
    except Exception as error:
        db.rollback()
        job = db.scalar(
            select(WooStockSyncJob)
            .where(WooStockSyncJob.id == job.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job.status == "cancelling":
            job.status = "cancelled"
            job.completed_at = datetime.now(timezone.utc)
        else:
            job.status = "paused"
            job.last_error = str(error)[:1000]
            job.errors = [*(job.errors or []), job.last_error][-100:]
    db.commit()
    db.refresh(job)
    return job


def resume_stock_sync_job(db: Session, job_id: int) -> WooStockSyncJob | None:
    job = db.scalar(select(WooStockSyncJob).where(WooStockSyncJob.id == job_id).with_for_update())
    if job is None:
        return None
    if job.status not in {"paused", "completed_with_errors"}:
        raise ValueError("Only paused or completed-with-errors jobs can be resumed.")
    if job.status == "completed_with_errors":
        job.retry_item_ids = list(job.terminal_failed_item_ids or [])
        job.terminal_failed_item_ids = []
        job.failed_count = 0
        job.retry_attempt = 0
    job.status = "queued"
    job.completed_at = None
    job.last_error = None
    db.commit()
    db.refresh(job)
    return job


def cancel_stock_sync_job(db: Session, job_id: int) -> WooStockSyncJob | None:
    job = db.scalar(select(WooStockSyncJob).where(WooStockSyncJob.id == job_id).with_for_update())
    if job is None:
        return None
    if job.status not in ACTIVE_JOB_STATUSES | {"paused"}:
        raise ValueError("Only active or paused jobs can be cancelled.")
    if job.status == "cancelling":
        return job
    if job.status == "running":
        job.status = "cancelling"
        job.completed_at = None
    else:
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def stock_sync_job_read(job: WooStockSyncJob) -> WooStockSyncJobRead:
    progress = 100.0 if job.total_items == 0 else min(100.0, round(job.processed_items * 100 / job.total_items, 1))
    return WooStockSyncJobRead(
        id=job.id,
        status=job.status,
        force=job.force,
        requested_by=job.requested_by,
        chunk_size=job.chunk_size,
        total_items=job.total_items,
        processed_items=job.processed_items,
        sent_count=job.sent_count,
        dry_run_count=job.dry_run_count,
        failed_count=job.failed_count,
        skipped_unmapped_count=job.skipped_unmapped_count,
        unchanged_count=job.unchanged_count,
        progress_percent=progress,
        errors=job.errors or [],
        last_error=job.last_error,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def list_stock_sync_jobs(db: Session, *, page: int = 1, page_size: int = 25) -> WooStockSyncJobListResponse:
    total = int(db.scalar(select(func.count(WooStockSyncJob.id))) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    jobs = list(
        db.scalars(
            select(WooStockSyncJob)
            .order_by(WooStockSyncJob.created_at.desc(), WooStockSyncJob.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return WooStockSyncJobListResponse(
        jobs=[stock_sync_job_read(job) for job in jobs],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(jobs),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


def unresolved_stock_sync_job_count(db: Session) -> int:
    return int(db.scalar(select(func.count(WooStockSyncJob.id)).where(or_(
        WooStockSyncJob.status == "paused",
        and_(WooStockSyncJob.status == "completed_with_errors", WooStockSyncJob.failed_count > 0),
    ))) or 0)


def normalized_target_item_ids(values: list[int] | None) -> list[int] | None:
    if values is None:
        return None
    return sorted(set(values))


def stock_sync_scheduler_should_start(settings: Settings) -> bool:
    return bool(settings.woocommerce_stock_sync_jobs_enabled and settings.app_env.casefold() != "test" and "PYTEST_CURRENT_TEST" not in os.environ)


async def run_stock_sync_job_scheduler(settings: Settings, stop_event: asyncio.Event) -> None:
    current_settings = settings
    while not stop_event.is_set():
        _worker_health["last_attempt_at"] = datetime.now(timezone.utc)
        try:
            job = await asyncio.to_thread(process_next_stock_sync_job, current_settings)
            if job is not None and job.status in {"paused", "completed_with_errors"}:
                message = job.last_error or f"WooCommerce stock-sync job {job.id} ended with {job.failed_count} unresolved item failure(s)."
                logger.error("WooCommerce stock-sync job %s requires review: %s", job.id, message)
                _worker_health["last_failure_at"] = datetime.now(timezone.utc)
                _worker_health["error_count"] = current_settings.operations_alert_failure_threshold
                _worker_health["last_error"] = message
                await asyncio.to_thread(
                    send_operations_alert,
                    current_settings,
                    "woo_stock_sync_job_requires_review",
                    message,
                    job_id=job.id,
                    status=job.status,
                    failed_count=job.failed_count,
                )
            else:
                _worker_health["last_success_at"] = datetime.now(timezone.utc)
                _worker_health["error_count"] = 0
                _worker_health["last_error"] = None
        except Exception as error:
            logger.exception("WooCommerce stock sync job scheduler failed.")
            _worker_health["last_failure_at"] = datetime.now(timezone.utc)
            _worker_health["error_count"] += 1
            _worker_health["last_error"] = str(error)[:1000]
            if _worker_health["error_count"] == current_settings.operations_alert_failure_threshold:
                await asyncio.to_thread(
                    send_operations_alert,
                    current_settings,
                    "woo_stock_sync_worker_failed",
                    "WooCommerce stock-sync worker repeatedly failed.",
                    error_count=_worker_health["error_count"],
                    last_error=_worker_health["last_error"],
                )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=current_settings.woocommerce_stock_sync_job_interval_seconds)
        except TimeoutError:
            pass
        current_settings = get_settings()


def stock_sync_worker_health(settings: Settings, *, running: bool, external_heartbeat: bool = False) -> dict:
    last_success = _worker_health["last_success_at"]
    stale_after = max(settings.woocommerce_stock_sync_job_interval_seconds * 3, 30)
    stale = not external_heartbeat and (last_success is None or (datetime.now(timezone.utc) - last_success).total_seconds() > stale_after)
    healthy = bool(settings.woocommerce_stock_sync_jobs_enabled and running and not stale and _worker_health["error_count"] < settings.operations_alert_failure_threshold)
    if healthy:
        message = "WooCommerce stock-sync worker is healthy."
    elif _worker_health["last_error"]:
        message = f"WooCommerce stock-sync worker failed: {_worker_health['last_error']}"
    elif not running:
        message = "WooCommerce stock-sync worker is not running."
    else:
        message = "WooCommerce stock-sync worker has no recent successful heartbeat."
    return {**_worker_health, "healthy": healthy, "stale": stale, "running": running, "message": message}
