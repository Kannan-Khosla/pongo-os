from __future__ import annotations

import os
import sys
import time

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.woocommerce_order_reconciliation import ensure_automatic_order_sync_job, process_next_order_sync_job
from app.services.woocommerce_stock_sync_jobs import process_next_stock_sync_job

POLL_SECONDS = 5


def run_cycle() -> bool:
    settings = get_settings()
    with SessionLocal() as db:
        ensure_automatic_order_sync_job(db, settings)
    order_job = process_next_order_sync_job(settings)
    if order_job is not None:
        return True
    stock_job = process_next_stock_sync_job(settings)
    return stock_job is not None


def main() -> None:
    while True:
        if run_cycle():
            # A fresh interpreter after each job guarantees that retained Woo
            # payload memory is returned to the dyno before the next pass.
            os.execv(sys.executable, [sys.executable, "-m", "app.workers.woocommerce"])
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
