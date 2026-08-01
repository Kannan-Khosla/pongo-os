from __future__ import annotations

import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.woocommerce import WooCommerceSyncError, WooCommerceSyncRun
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_orders import commit_remote_order_records
from app.services.operations_alerts import send_operations_alert
from app.services.woocommerce_access import effective_woocommerce_settings

logger = logging.getLogger(__name__)

SCHEDULER_CREATED_BY = "server-order-reconciliation"
POSTGRES_SCHEDULER_LOCK_KEY = int.from_bytes(b"PONGOREC", byteorder="big")
SUCCESS_STATUSES = {"completed"}
DEFAULT_STATUSES = ["processing", "on-hold", "pending", "completed", "failed", "cancelled", "refunded"]
ACTIVE_STATUSES = {"processing", "on-hold", "pending"}
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


async def run_order_reconciliation_scheduler(settings: Any, stop_event: asyncio.Event) -> None:
    current_settings = settings
    consecutive_failures = 0
    while not stop_event.is_set():
        interval = max(15, int(getattr(current_settings, "woocommerce_order_reconciliation_interval_seconds", 60)))
        result = await asyncio.to_thread(run_order_reconciliation_once, current_settings)
        if result.get("status") == "failed":
            consecutive_failures += 1
            threshold = int(getattr(current_settings, "operations_alert_failure_threshold", 3))
            if consecutive_failures == threshold:
                await asyncio.to_thread(
                    send_operations_alert,
                    current_settings,
                    "woocommerce_order_reconciliation_failed",
                    result.get("error") or "WooCommerce order reconciliation failed repeatedly.",
                    consecutive_failures=consecutive_failures,
                    sync_run_id=result.get("sync_run_id"),
                )
        elif result.get("status") not in {"skipped_overlap", "not_configured", "disabled"}:
            consecutive_failures = 0
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
        current_settings = get_settings()


def run_order_reconciliation_once(
    settings: Any,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    client_factory: Callable[[Any], Any] = WooCommerceClient,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not getattr(settings, "woocommerce_order_reconciliation_enabled", False):
        return {"status": "disabled"}
    if not getattr(settings, "woocommerce_read_enabled", True):
        return {"status": "not_configured"}
    if not _PROCESS_LOCK.acquire(blocking=False):
        return {"status": "skipped_overlap"}

    try:
        db = session_factory()
    except Exception as error:
        _PROCESS_LOCK.release()
        logger.exception("Could not open a database session for WooCommerce order reconciliation.")
        return {"status": "failed", "sync_run_id": None, "error": str(error)[:1000]}
    lease_acquired = False
    started_at = as_utc(now or datetime.now(timezone.utc))
    try:
        settings = effective_woocommerce_settings(db, settings)
        if not reconciliation_is_configured(settings):
            return {"status": "not_configured"}
        lease_acquired = acquire_scheduler_lease(db)
        if not lease_acquired:
            db.rollback()
            return {"status": "skipped_overlap"}

        last_success = latest_scheduler_run(db, SUCCESS_STATUSES)
        modified_after = reconciliation_cursor(settings, started_at, last_success)
        statuses = list(getattr(settings, "order_reconciliation_statuses", None) or DEFAULT_STATUSES)
        active_statuses = [status for status in statuses if status in ACTIVE_STATUSES]
        recently_changed_statuses = [status for status in statuses if status not in ACTIVE_STATUSES]
        client = client_factory(settings)
        remote_by_id: dict[int, dict[str, Any]] = {}
        if active_statuses:
            for order in client.fetch_all_orders(statuses=active_statuses, limit=None):
                remote_by_id[int(order["id"])] = order
        if recently_changed_statuses:
            for order in client.fetch_all_orders(
                statuses=recently_changed_statuses,
                limit=None,
                modified_after=modified_after.isoformat().replace("+00:00", "Z"),
            ):
                # The terminal query runs second so a cancellation/refund that
                # races the active-order query wins this reconciliation pass.
                remote_by_id[int(order["id"])] = order
        sync_run, summary = commit_remote_order_records(
            db,
            list(remote_by_id.values()),
            statuses,
            SCHEDULER_CREATED_BY,
        )
        return {
            "status": sync_run.status,
            "sync_run_id": sync_run.id,
            "total_remote_records": sync_run.total_remote_records,
        }
    except Exception as error:
        db.rollback()
        message = str(error)[:1000] or error.__class__.__name__
        failed_run = safe_record_failure(db, started_at, message)
        logger.error("WooCommerce server order reconciliation failed: %s", message)
        return {"status": "failed", "sync_run_id": failed_run.id if failed_run else None, "error": message}
    finally:
        try:
            release_scheduler_lease(db, lease_acquired)
        finally:
            try:
                db.close()
            finally:
                _PROCESS_LOCK.release()


def reconciliation_health(db: Session, settings: Any, *, running: bool = False, now: datetime | None = None) -> dict[str, Any]:
    enabled = bool(getattr(settings, "woocommerce_order_reconciliation_enabled", False))
    configured = reconciliation_is_configured(settings)
    read_enabled = bool(getattr(settings, "woocommerce_read_enabled", True))
    interval = max(15, int(getattr(settings, "woocommerce_order_reconciliation_interval_seconds", 60)))
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
    latest_attempt_error = latest_sync_error(db, latest_attempt)

    if not enabled:
        message = "Server order reconciliation is disabled."
    elif not configured:
        message = "Server order reconciliation is waiting for WooCommerce credentials."
    elif not read_enabled:
        message = "Server order reconciliation cannot run while WooCommerce reads are disabled."
    elif not running:
        message = "Server order reconciliation is not running."
    elif latest_attempt is None:
        message = "The first server order reconciliation is starting."
    elif latest_attempt_failed:
        message = "The last server order reconciliation failed."
    elif degraded:
        message = f"The last server order reconciliation completed with {latest_attempt.error_count} issue(s)."
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
        "last_error": latest_attempt_error or (latest_failure.notes if latest_failure else None),
        "message": message,
    }


def reconciliation_cursor(settings: Any, now: datetime, last_success: WooCommerceSyncRun | None) -> datetime:
    fallback = now - timedelta(hours=max(1, int(getattr(settings, "woocommerce_order_reconciliation_lookback_hours", 168))))
    if last_success is None:
        return fallback
    return max(fallback, run_time(last_success) - timedelta(minutes=5))


def latest_scheduler_run(db: Session, statuses: set[str] | None = None) -> WooCommerceSyncRun | None:
    statement = select(WooCommerceSyncRun).where(
        WooCommerceSyncRun.sync_type == "orders",
        WooCommerceSyncRun.created_by == SCHEDULER_CREATED_BY,
    )
    if statuses:
        statement = statement.where(WooCommerceSyncRun.status.in_(statuses))
    return db.scalars(statement.order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())).first()


def latest_sync_error(db: Session, sync_run: WooCommerceSyncRun | None) -> str | None:
    if sync_run is None:
        return None
    error = db.scalars(
        select(WooCommerceSyncError)
        .where(WooCommerceSyncError.sync_run_id == sync_run.id)
        .order_by(WooCommerceSyncError.created_at.desc(), WooCommerceSyncError.id.desc())
    ).first()
    return error.error_message if error else sync_run.notes


def record_failure(db: Session, started_at: datetime, message: str) -> WooCommerceSyncRun:
    safe_message = message[:1000] or "WooCommerce order reconciliation failed."
    sync_run = WooCommerceSyncRun(
        sync_type="orders",
        status="failed",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        created_by=SCHEDULER_CREATED_BY,
        error_count=1,
        notes=safe_message,
    )
    db.add(sync_run)
    db.flush()
    db.add(WooCommerceSyncError(sync_run_id=sync_run.id, error_message=safe_message))
    db.commit()
    db.refresh(sync_run)
    return sync_run


def safe_record_failure(db: Session, started_at: datetime, message: str) -> WooCommerceSyncRun | None:
    try:
        return record_failure(db, started_at, message)
    except Exception:
        db.rollback()
        logger.exception("Could not persist the WooCommerce order reconciliation failure.")
        return None


def acquire_scheduler_lease(db: Session) -> bool:
    if db.get_bind().dialect.name != "postgresql":
        return True
    return bool(db.scalar(text("SELECT pg_try_advisory_lock(:lock_key)"), {"lock_key": POSTGRES_SCHEDULER_LOCK_KEY}))


def release_scheduler_lease(db: Session, acquired: bool) -> None:
    if not acquired:
        return
    try:
        if db.get_bind().dialect.name != "postgresql":
            return
        db.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": POSTGRES_SCHEDULER_LOCK_KEY})
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not release the WooCommerce order reconciliation scheduler lease.")


def run_time(sync_run: WooCommerceSyncRun | None) -> datetime | None:
    if sync_run is None:
        return None
    return as_utc(sync_run.completed_at or sync_run.started_at)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
