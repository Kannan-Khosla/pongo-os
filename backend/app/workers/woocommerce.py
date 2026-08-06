from __future__ import annotations

import logging
import os
import sys
import time

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.metric_warming import warm_next_requested_metric, warm_next_standard_metric
from app.services.report_jobs import process_next_report_job
from app.services.woocommerce_order_reconciliation import (
    ensure_automatic_order_sync_job,
    process_next_order_history_import,
    process_next_order_sync_job,
)
from app.services.woocommerce_stock_sync_jobs import ensure_daily_full_stock_sync_job, process_next_stock_sync_job

POLL_SECONDS = 5
logger = logging.getLogger(__name__)


def warm_metrics(settings) -> bool:
    try:
        return warm_next_requested_metric() or warm_next_standard_metric(settings)
    except Exception:
        logger.exception("Unable to warm standard dashboard metrics")
        return False


def run_cycle() -> bool:
    settings = get_settings()
    with SessionLocal() as db:
        ensure_automatic_order_sync_job(db, settings)
        ensure_daily_full_stock_sync_job(db, settings)
    order_job = process_next_order_sync_job(settings)
    if order_job is not None:
        return True
    # Operational writeback stays ahead of reports so a completed order cannot
    # sit behind a large PDF/CSV run in the queue.
    stock_job = process_next_stock_sync_job(settings)
    if stock_job is not None:
        return True
    report_job = process_next_report_job()
    if report_job is not None:
        return True
    history_job = process_next_order_history_import(settings)
    if history_job is not None:
        return True
    return bool(warm_metrics(settings))


def main() -> None:
    while True:
        if run_cycle():
            # A fresh interpreter after each job guarantees that retained Woo
            # payload memory is returned to the dyno before the next pass.
            os.execv(sys.executable, [sys.executable, "-m", "app.workers.woocommerce"])
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
