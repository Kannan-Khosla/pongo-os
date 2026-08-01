from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.woocommerce import WooCommerceAccessModeChange

READ_ONLY = "read_only"
READ_WRITE = "read_write"
ACCESS_MODES = {READ_ONLY, READ_WRITE}


def configured_access_mode(settings: Settings) -> str:
    return READ_WRITE if settings.woocommerce_writeback_enabled and not settings.woocommerce_read_only else READ_ONLY


def latest_access_mode_change(db: Session) -> WooCommerceAccessModeChange | None:
    return db.scalar(select(WooCommerceAccessModeChange).order_by(WooCommerceAccessModeChange.id.desc()).limit(1))


def effective_woocommerce_settings(db: Session, settings: Settings | None = None) -> Settings:
    current = settings or get_settings()
    if not hasattr(current, "model_copy"):
        return current
    change = latest_access_mode_change(db)
    if change is None:
        return current
    writable = change.access_mode == READ_WRITE
    return current.model_copy(update={
        "woocommerce_read_enabled": True,
        "woocommerce_read_only": not writable,
        "woocommerce_writeback_enabled": writable,
        "woocommerce_writeback_dry_run": not writable,
        "woocommerce_staging_live_test_mode": writable,
        "woocommerce_allow_stock_write": writable,
        "woocommerce_production_stock_authority": "pongo" if writable else "disabled",
        "woocommerce_allow_order_status_write": writable,
        "woocommerce_allow_product_metadata_write": writable,
        "woocommerce_allow_customer_write": writable,
        "woocommerce_allow_coupon_write": writable,
        "woocommerce_allow_refund_write": writable,
        "woocommerce_allow_delete": writable,
        "woocommerce_order_reconciliation_enabled": True,
        "woocommerce_stock_sync_jobs_enabled": True,
    })


def change_access_mode(db: Session, access_mode: str, changed_by: str) -> WooCommerceAccessModeChange:
    if access_mode not in ACCESS_MODES:
        raise ValueError("WooCommerce access mode must be read_only or read_write.")
    current = latest_access_mode_change(db)
    if current and current.access_mode == access_mode:
        return current
    row = WooCommerceAccessModeChange(access_mode=access_mode, changed_by=changed_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
