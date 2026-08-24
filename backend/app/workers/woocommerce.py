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
from app.services.woocommerce_subscriptions import process_subscription_sync_if_due
from app.services.woocommerce_catalog_sync import process_next_catalog_sync
from app.services.woocommerce_client import WooCommerceClient

POLL_SECONDS = 5
logger = logging.getLogger(__name__)
_catalog_client: WooCommerceClient | None = None
_catalog_client_fingerprint: tuple[str, str, str] | None = None
_catalog_step_completed = False


def pooled_catalog_client(settings) -> WooCommerceClient:
    global _catalog_client, _catalog_client_fingerprint
    fingerprint = (
        settings.woocommerce_base_url,
        settings.woocommerce_consumer_key,
        settings.woocommerce_consumer_secret,
    )
    if _catalog_client is None or _catalog_client_fingerprint != fingerprint:
        if _catalog_client is not None:
            _catalog_client.close()
        _catalog_client = WooCommerceClient(settings).open()
        _catalog_client_fingerprint = fingerprint
    return _catalog_client


def warm_metrics(settings) -> bool:
    try:
        return warm_next_requested_metric() or warm_next_standard_metric(settings)
    except Exception:
        logger.exception("Unable to warm standard dashboard metrics")
        return False


def run_cycle() -> bool:
    global _catalog_step_completed
    _catalog_step_completed = False
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
    if process_subscription_sync_if_due(settings):
        return True
    # Catalog sync deliberately yields after one durable page/batch and stays
    # behind live orders, stock writeback, and subscription snapshots.
    catalog_job = process_next_catalog_sync(
        settings,
        client_factory=pooled_catalog_client,
        manage_client=False,
    )
    if catalog_job is not None:
        _catalog_step_completed = True
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
            if _catalog_step_completed:
                # Keep the Woo HTTP pool alive, but begin a new fair-priority
                # cycle before taking the next bounded catalog step.
                continue
            # A fresh interpreter after each job guarantees that retained Woo
            # payload memory is returned to the dyno before the next pass.
            os.execv(sys.executable, [sys.executable, "-m", "app.workers.woocommerce"])
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
