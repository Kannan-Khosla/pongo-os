import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.woocommerce import WooCommerceSyncError


SIGNATURE_FIELDS = (
    "remote_order_id",
    "remote_line_item_id",
    "remote_product_id",
    "remote_variation_id",
    "sku",
    "barcode",
    "error_message",
)


def sync_error_fingerprint(values: dict) -> str:
    normalized = json.dumps(
        [values.get(field) for field in SIGNATURE_FIELDS],
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def prune_sync_errors(db: Session) -> None:
    if not db.info.get("woo_sync_errors_pruned"):
        cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().woocommerce_sync_error_retention_days)
        with db.no_autoflush:
            db.execute(delete(WooCommerceSyncError).where(WooCommerceSyncError.created_at < cutoff))
        db.info["woo_sync_errors_pruned"] = True


def store_sync_error_once(db: Session, **values) -> bool:
    prune_sync_errors(db)
    values["fingerprint"] = sync_error_fingerprint(values)
    dialect = db.get_bind().dialect.name
    statement = postgresql_insert(WooCommerceSyncError) if dialect == "postgresql" else sqlite_insert(WooCommerceSyncError)
    result = db.execute(
        statement.values(**values).on_conflict_do_nothing(
            index_elements=["sync_run_id", "fingerprint"],
        ).returning(WooCommerceSyncError.id)
    )
    return result.scalar_one_or_none() is not None
