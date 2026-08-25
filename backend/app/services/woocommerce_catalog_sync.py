from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from sqlalchemy import String, cast, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.inventory import InventoryItem, InventoryLocation
from app.models.woocommerce import WooCatalogSyncRow, WooCommerceSyncRun, WooItemMapping
from app.schemas.woocommerce import (
    WooCatalogSyncRowListResponse,
    WooCatalogSyncRowRead,
    WooCatalogSyncRunRead,
)
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.location_inventory import set_opening_balance
from app.services.woocommerce_sync import (
    NormalizedWooRecord,
    attach_woo_mapping,
    create_item_from_woo,
    ensure_mapping_record,
    normalize_key,
    normalize_remote_record,
)


CATALOG_SYNC_TYPE = "catalog"
CATALOG_ACTIVE_STATUSES = {
    "queued",
    "fetching_products",
    "fetching_variations",
    "matching",
    "applying",
    "waiting_retry",
    "paused",
    "cancelling",
}
CATALOG_WORKER_STATUSES = CATALOG_ACTIVE_STATUSES - {"paused", "cancelling"}
CATALOG_RESUMABLE_STATUSES = {"paused", "failed"}
CATALOG_RESOLUTION_STATUSES = CATALOG_RESUMABLE_STATUSES | {"completed_with_attention", "queued"}
POSTGRES_CATALOG_WORKER_LOCK_KEY = int.from_bytes(b"PONGOCAT", byteorder="big")
POSTGRES_CATALOG_ENQUEUE_LOCK_KEY = int.from_bytes(b"PONGOCQ", byteorder="big")
CATALOG_PAGE_SIZE = 100
CATALOG_APPLY_BATCH_SIZE = 100
CATALOG_MAX_ATTEMPTS = 3
CATALOG_STAGE_RETENTION_DAYS = 30
CATALOG_FULL_RECONCILIATION_DAYS = 7


def enqueue_catalog_sync(
    db: Session,
    *,
    created_by: str,
    request_key: str | None = None,
) -> tuple[WooCommerceSyncRun, bool]:
    request_key = (request_key or uuid4().hex).strip()
    if not request_key or len(request_key) > 120:
        raise ValueError("Idempotency-Key must contain 1 to 120 characters.")
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": POSTGRES_CATALOG_ENQUEUE_LOCK_KEY})
    existing = db.scalar(
        select(WooCommerceSyncRun).where(
            WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
            WooCommerceSyncRun.request_key == request_key,
        )
    )
    if existing is not None:
        return existing, True
    active = db.scalar(
        select(WooCommerceSyncRun)
        .where(
            WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
            WooCommerceSyncRun.status.in_(CATALOG_ACTIVE_STATUSES),
        )
        .order_by(WooCommerceSyncRun.started_at, WooCommerceSyncRun.id)
        .with_for_update(skip_locked=True)
    )
    if active is not None:
        return active, True
    now = datetime.now(timezone.utc)
    completed_runs = list(db.scalars(
        select(WooCommerceSyncRun)
        .where(
            WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
            WooCommerceSyncRun.completed_at.is_not(None),
            WooCommerceSyncRun.status.in_(("completed", "completed_with_attention")),
        )
        .order_by(WooCommerceSyncRun.completed_at.desc(), WooCommerceSyncRun.id.desc())
        .limit(100)
    ).all())
    latest_completed = completed_runs[0] if completed_runs else None
    latest_full = next(
        (candidate for candidate in completed_runs if (candidate.progress or {}).get("scan_mode", "full") == "full"),
        None,
    )
    latest_full_at = parse_datetime(latest_full.completed_at) if latest_full is not None else None
    scan_mode = (
        "full"
        if latest_full_at is None or now - latest_full_at >= timedelta(days=CATALOG_FULL_RECONCILIATION_DAYS)
        else "delta"
    )
    progress = {
        "stage": "queued",
        "scan_id": uuid4().hex,
        "scan_started_at": now.isoformat(),
        "scan_mode": scan_mode,
        "scan_pass": scan_mode,
        "scan_complete": False,
        "next_product_page": 1,
        "processed_records": 0,
        "unchanged_count": 0,
        "message": "Catalog sync is queued.",
    }
    if scan_mode == "delta" and latest_completed is not None:
        progress["incremental_cursor_at"] = latest_completed.completed_at.isoformat()
    run = WooCommerceSyncRun(
        sync_type=CATALOG_SYNC_TYPE,
        status="queued",
        created_by=created_by,
        request_key=request_key,
        progress=progress,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(WooCommerceSyncRun)
            .where(
                WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
                or_(
                    WooCommerceSyncRun.request_key == request_key,
                    WooCommerceSyncRun.status.in_(CATALOG_ACTIVE_STATUSES),
                ),
            )
            .order_by(WooCommerceSyncRun.started_at, WooCommerceSyncRun.id)
        )
        if existing is None:
            raise
        return existing, True
    db.refresh(run)
    return run, False


def get_catalog_sync(db: Session, sync_run_id: int) -> WooCommerceSyncRun | None:
    return db.scalar(
        select(WooCommerceSyncRun).where(
            WooCommerceSyncRun.id == sync_run_id,
            WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
        )
    )


def current_catalog_sync(db: Session) -> WooCommerceSyncRun | None:
    return db.scalar(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE)
        .order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
        .limit(1)
    )


def catalog_sync_run_read(run: WooCommerceSyncRun, *, deduplicated: bool = False) -> WooCatalogSyncRunRead:
    progress = run.progress or {}
    total = run.total_remote_records or 0
    processed = int(progress.get("processed_records") or 0)
    terminal = run.status in {"completed", "completed_with_attention", "failed", "cancelled"}
    if terminal:
        percent = 100.0
    elif progress.get("stage") in {"applying", "matching"} and total:
        percent = min(99.0, round(50 + (processed * 50 / total), 1))
    elif progress.get("stage") in {"queued", "fetching_products", "fetching_variations"}:
        if progress.get("scan_pass") == "delta":
            percent = 49.0
        else:
            total_pages = max(safe_int(progress.get("product_total_pages")) or 1, 1)
            page = safe_int(progress.get("active_product_page")) or safe_int(progress.get("next_product_page")) or 1
            completed_pages = max(page - 1, 0)
            page_fraction = 0.0
            if progress.get("active_product_page"):
                parents = list(progress.get("pending_variation_parent_keys") or [])
                if parents:
                    parent_index = min(max(safe_int(progress.get("variation_parent_index")) or 0, 0), len(parents))
                    page_fraction = 0.5 + (0.5 * parent_index / len(parents))
                else:
                    page_fraction = 1.0
            percent = min(49.0, round(50 * (completed_pages + page_fraction) / total_pages, 1))
    else:
        percent = 0.0
    next_retry_at = parse_datetime(progress.get("next_retry_at"))
    return WooCatalogSyncRunRead(
        id=run.id,
        status=run.status,
        stage=str(progress.get("stage") or run.status),
        created_by=run.created_by,
        started_at=run.started_at,
        completed_at=run.completed_at,
        updated_at=run.updated_at,
        attempt_count=run.attempt_count,
        next_retry_at=next_retry_at,
        total_remote_records=total,
        processed_records=processed,
        created_count=run.created_count,
        updated_count=run.updated_count,
        matched_count=run.matched_count,
        unchanged_count=int(progress.get("unchanged_count") or 0),
        skipped_count=run.skipped_count,
        conflict_count=run.conflict_count,
        error_count=run.error_count,
        progress_percent=percent,
        message=str(progress.get("message") or run.notes or ""),
        can_resume=run.status in CATALOG_RESUMABLE_STATUSES,
        can_cancel=run.status in CATALOG_ACTIVE_STATUSES - {"cancelling"},
        can_resolve=(
            run.status in CATALOG_RESUMABLE_STATUSES | {"completed_with_attention"}
            or (run.status == "queued" and run.conflict_count > 0)
        ),
        deduplicated=deduplicated,
    )


def catalog_row_read(row: WooCatalogSyncRow) -> WooCatalogSyncRowRead:
    return WooCatalogSyncRowRead(
        id=row.id,
        sync_run_id=row.sync_run_id,
        remote_type=row.remote_type,
        woo_product_id=row.woo_product_id,
        woo_variation_id=row.woo_variation_id,
        sku=row.sku,
        barcode=row.barcode,
        product_name=row.product_name,
        status=row.status,
        action=row.action,
        local_item_id=row.local_item_id,
        message=row.message,
        resolution_action=row.resolution_action,
        resolution_item_id=row.resolution_item_id,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_catalog_rows(
    db: Session,
    sync_run_id: int,
    *,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> WooCatalogSyncRowListResponse:
    predicates = [WooCatalogSyncRow.sync_run_id == sync_run_id]
    if status:
        predicates.append(WooCatalogSyncRow.status == status)
    if search and search.strip():
        term = f"%{search.strip()}%"
        predicates.append(or_(
            WooCatalogSyncRow.sku.ilike(term),
            WooCatalogSyncRow.barcode.ilike(term),
            WooCatalogSyncRow.product_name.ilike(term),
            cast(WooCatalogSyncRow.woo_product_id, String).ilike(term),
            cast(WooCatalogSyncRow.woo_variation_id, String).ilike(term),
        ))
    total = int(db.scalar(select(func.count(WooCatalogSyncRow.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    rows = list(db.scalars(
        select(WooCatalogSyncRow)
        .where(*predicates)
        .order_by(WooCatalogSyncRow.id)
        .offset((effective_page - 1) * page_size)
        .limit(page_size)
    ).all())
    return WooCatalogSyncRowListResponse(
        rows=[catalog_row_read(row) for row in rows],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(rows),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


def resume_catalog_sync(db: Session, sync_run_id: int) -> WooCommerceSyncRun | None:
    run = db.scalar(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.id == sync_run_id, WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE)
        .with_for_update()
    )
    if run is None:
        return None
    if run.status == "queued":
        return run
    if run.status not in CATALOG_RESUMABLE_STATUSES:
        raise ValueError("Only paused or failed catalog syncs can be resumed.")
    progress = dict(run.progress or {})
    progress.pop("next_retry_at", None)
    progress["message"] = "Catalog sync is queued to resume."
    run.status = "queued"
    run.completed_at = None
    run.attempt_count = 0
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def cancel_catalog_sync(db: Session, sync_run_id: int) -> WooCommerceSyncRun | None:
    run = db.scalar(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.id == sync_run_id, WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE)
        .with_for_update()
    )
    if run is None:
        return None
    if run.status == "cancelled":
        return run
    if run.status not in CATALOG_ACTIVE_STATUSES:
        raise ValueError("Only an active catalog sync can be cancelled.")
    progress = dict(run.progress or {})
    progress.update({"stage": "cancelled", "message": "Catalog sync was cancelled."})
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def resolve_catalog_row(
    db: Session,
    sync_run_id: int,
    row_id: int,
    *,
    action: str,
    item_id: int | None,
    actor: str,
) -> WooCatalogSyncRow | None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": POSTGRES_CATALOG_ENQUEUE_LOCK_KEY})
    row = db.scalar(
        select(WooCatalogSyncRow)
        .where(WooCatalogSyncRow.id == row_id, WooCatalogSyncRow.sync_run_id == sync_run_id)
        .with_for_update()
    )
    if row is None:
        return None
    if action == "link" and item_id is None:
        raise ValueError("item_id is required when linking a catalog row.")
    if action != "link" and item_id is not None:
        raise ValueError("item_id is only accepted for a link resolution.")
    if row.resolution_action is not None and row.status != "needs_attention":
        if row.resolution_action == action and row.resolution_item_id == item_id:
            return row
        raise ValueError("This catalog row was already resolved differently.")
    if row.status != "needs_attention":
        raise ValueError("Only rows needing attention can be resolved.")
    other_active = db.scalar(select(WooCommerceSyncRun.id).where(
        WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
        WooCommerceSyncRun.id != sync_run_id,
        WooCommerceSyncRun.status.in_(CATALOG_ACTIVE_STATUSES),
    ).with_for_update(skip_locked=True))
    if other_active is not None:
        raise ValueError("Finish or cancel the active catalog sync before resolving a row from this run.")
    record = None if action == "skip" else normalized_row(row)
    if record is not None and record.parent_container:
        raise ValueError("Variable parent containers cannot be mapped or created as inventory items.")
    if action == "link" and record is not None:
        item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id).with_for_update())
        if item is None:
            raise ValueError("The selected inventory item no longer exists.")
        conflict = target_conflict(db, item, record)
        if conflict:
            raise ValueError(conflict)
    elif action == "create" and record is not None:
        hard_item, conflict = hard_identity_match(db, record)
        if conflict:
            raise ValueError(conflict)
        if hard_item is not None:
            raise ValueError("This WooCommerce identity already belongs to an inventory item; link that item instead.")
    now = datetime.now(timezone.utc)
    row.resolution_action = action
    row.resolution_item_id = item_id
    row.resolved_by = actor
    row.resolved_at = now
    row.status = "staged"
    row.action = "pending"
    row.message = f"Resolution '{action}' queued by {actor}."
    run = db.scalar(select(WooCommerceSyncRun).where(WooCommerceSyncRun.id == sync_run_id).with_for_update())
    if run is None or run.sync_type != CATALOG_SYNC_TYPE:
        raise ValueError("Catalog sync run no longer exists.")
    if run.status not in CATALOG_RESOLUTION_STATUSES:
        raise ValueError("This catalog sync is not ready for attention resolution.")
    progress = dict(run.progress or {})
    progress.update({"stage": "applying", "message": "Resolved catalog rows are queued to apply."})
    run.status = "queued"
    run.completed_at = None
    run.progress = progress
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise ValueError("Another catalog sync became active. Retry this resolution after it finishes.") from error
    db.refresh(row)
    return row


def process_next_catalog_sync(
    settings: Settings,
    *,
    db_factory=SessionLocal,
    client_factory=WooCommerceClient,
    manage_client: bool = True,
) -> WooCommerceSyncRun | None:
    with db_factory() as db:
        lock_connection = None
        try:
            if db.get_bind().dialect.name == "postgresql":
                lock_connection = db.get_bind().connect()
                if not lock_connection.scalar(
                    text("SELECT pg_try_advisory_lock(:lock_key)"),
                    {"lock_key": POSTGRES_CATALOG_WORKER_LOCK_KEY},
                ):
                    return None
            run = claim_catalog_sync(db)
            if run is None:
                return None
            effective_settings = effective_woocommerce_settings(db, settings)
            db.commit()  # Never hold a database transaction across Woo HTTP.
            client = client_factory(effective_settings)
            try:
                open_client = getattr(client, "open", None)
                if callable(open_client):
                    open_client()
                return run_catalog_sync(db, run.id, client)
            finally:
                if manage_client:
                    close_client = getattr(client, "close", None)
                    if callable(close_client):
                        close_client()
        finally:
            if lock_connection is not None:
                try:
                    lock_connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_key)"),
                        {"lock_key": POSTGRES_CATALOG_WORKER_LOCK_KEY},
                    )
                finally:
                    lock_connection.close()


def claim_catalog_sync(db: Session) -> WooCommerceSyncRun | None:
    run = db.scalar(
        select(WooCommerceSyncRun)
        .where(
            WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
            WooCommerceSyncRun.status.in_(CATALOG_WORKER_STATUSES),
        )
        .order_by(WooCommerceSyncRun.started_at, WooCommerceSyncRun.id)
        .with_for_update(skip_locked=True)
    )
    if run is None:
        return None
    progress = dict(run.progress or {})
    if run.status == "waiting_retry":
        retry_at = parse_datetime(progress.get("next_retry_at"))
        if retry_at and retry_at > datetime.now(timezone.utc):
            db.rollback()
            return None
    stage = str(progress.get("stage") or "queued")
    run.status = "fetching_products" if stage == "queued" else stage
    progress["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    progress["message"] = "Catalog sync worker started."
    progress.pop("next_retry_at", None)
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def run_catalog_sync(db: Session, sync_run_id: int, client: WooCommerceClient) -> WooCommerceSyncRun:
    try:
        run = require_catalog_run(db, sync_run_id)
        stage = str((run.progress or {}).get("stage") or "queued")
        if stage in {"queued", "fetching_products", "fetching_variations"}:
            return fetch_catalog_step(db, run, client)
        if run.status == "cancelled":
            return run
        if stage == "matching":
            progress = dict(run.progress or {})
            progress.update({"stage": "applying", "message": "Catalog capture is complete; safe matches are ready to apply."})
            run.status = "applying"
            run.progress = progress
            db.commit()
            db.refresh(run)
            return run
        if stage == "applying":
            apply_catalog_rows(db, sync_run_id)
            remaining = int(db.scalar(select(func.count(WooCatalogSyncRow.id)).where(
                WooCatalogSyncRow.sync_run_id == sync_run_id,
                WooCatalogSyncRow.status == "staged",
            )) or 0)
            return require_catalog_run(db, sync_run_id) if remaining else finalize_catalog_sync(db, sync_run_id)
        return run
    except WooCommerceClientError as error:
        db.rollback()
        return record_catalog_failure(
            db,
            sync_run_id,
            error,
            retry_after=client.last_response_headers.get("retry-after"),
        )
    except Exception as error:
        db.rollback()
        return record_catalog_failure(db, sync_run_id, error)


def fetch_catalog_step(db: Session, run: WooCommerceSyncRun, client: WooCommerceClient) -> WooCommerceSyncRun:
    if run.status == "cancelled":
        return run
    progress = dict(run.progress or {})
    pending_parents = list(progress.get("pending_variation_parent_keys") or [])
    parent_index = int(progress.get("variation_parent_index") or 0)
    if progress.get("active_product_page") and parent_index < len(pending_parents):
        return fetch_variation_page(db, run, client, pending_parents, parent_index)
    if progress.get("active_product_page"):
        return finish_product_page(db, run)
    return fetch_product_page(db, run, client)


def fetch_product_page(db: Session, run: WooCommerceSyncRun, client: WooCommerceClient) -> WooCommerceSyncRun:
    progress = dict(run.progress or {})
    page = int(progress.get("next_product_page") or 1)
    scan_pass = str(progress.get("scan_pass") or "full")
    run.status = "fetching_products"
    progress.update({
        "stage": "fetching_products",
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"Reconciling WooCommerce changes, page {page}."
            if scan_pass == "delta"
            else f"Fetching WooCommerce catalog page {page}."
        ),
    })
    run.progress = progress
    db.commit()

    request_options: dict[str, Any] = {"orderby": "id", "order": "asc"}
    if scan_pass == "delta":
        cursor_at = (
            parse_datetime(progress.get("incremental_cursor_at"))
            or parse_datetime(progress.get("scan_started_at"))
            or run.started_at
        )
        request_options["modified_after"] = (cursor_at - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    products = client.list_products(page=page, per_page=CATALOG_PAGE_SIZE, statuses=["any"], **request_options)
    has_more = client_page_has_more(client, page, len(products), CATALOG_PAGE_SIZE)
    response_headers = getattr(client, "last_response_headers", {})
    product_total_pages = safe_int(response_headers.get("x-wp-totalpages")) or page + int(has_more)
    product_total_records = safe_int(response_headers.get("x-wp-total"))
    if catalog_cancelled(db, run.id):
        return require_catalog_run(db, run.id)
    pending_parents: list[str] = []
    for index, product in enumerate(products):
        parent = product.get("type") == "variable"
        row = stage_catalog_record(
            db,
            run.id,
            page,
            index,
            {"product": product, "variation": None, "parent_container": parent, "scan_pass": scan_pass},
        )
        if parent and row.woo_product_id is not None:
            pending_parents.append(row.remote_key)
    run = require_catalog_run(db, run.id, lock=True)
    progress = dict(run.progress or {})
    progress.update({
        "active_product_page": page,
        "active_product_page_has_more": has_more,
        f"{scan_pass}_product_total_pages": max(product_total_pages, page),
        "pending_variation_parent_keys": pending_parents,
        "variation_parent_index": 0,
        "next_variation_page": 1,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "message": f"Catalog page {page} was staged.",
    })
    if product_total_records is not None:
        progress[f"{scan_pass}_product_total_records"] = product_total_records
    if scan_pass == "full":
        progress["product_total_pages"] = max(product_total_pages, page)
        if product_total_records is not None:
            progress["product_total_records"] = product_total_records
    run.total_remote_records = catalog_row_count(db, run.id)
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def fetch_variation_page(
    db: Session,
    run: WooCommerceSyncRun,
    client: WooCommerceClient,
    pending_parents: list[str],
    parent_index: int,
) -> WooCommerceSyncRun:
    progress = dict(run.progress or {})
    parent_row = db.scalar(select(WooCatalogSyncRow).where(
        WooCatalogSyncRow.sync_run_id == run.id,
        WooCatalogSyncRow.remote_key == pending_parents[parent_index],
    ))
    if parent_row is None or parent_row.woo_product_id is None:
        raise ValueError("Staged variable parent disappeared before its variations were fetched.")
    parent_product = dict((parent_row.raw_payload or {}).get("product") or {})
    product_id = parent_row.woo_product_id
    variation_page = int(progress.get("next_variation_page") or 1)
    run.status = "fetching_variations"
    progress.update({
        "stage": "fetching_variations",
        "current_parent_product_id": product_id,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "message": f"Fetching variations for product {product_id}, page {variation_page}.",
    })
    run.progress = progress
    db.commit()

    variations = client.list_product_variations(
        product_id,
        page=variation_page,
        per_page=CATALOG_PAGE_SIZE,
        orderby="id",
        order="asc",
    )
    has_more = client_page_has_more(client, variation_page, len(variations), CATALOG_PAGE_SIZE)
    if catalog_cancelled(db, run.id):
        return require_catalog_run(db, run.id)
    product_page = int(progress.get("active_product_page") or 1)
    scan_pass = str(progress.get("scan_pass") or "full")
    for index, variation in enumerate(variations):
        stage_catalog_record(
            db,
            run.id,
            product_page,
            index,
            {"product": parent_product, "variation": variation, "scan_pass": scan_pass},
        )
    run = require_catalog_run(db, run.id, lock=True)
    progress = dict(run.progress or {})
    if has_more:
        progress["next_variation_page"] = variation_page + 1
    else:
        progress["variation_parent_index"] = parent_index + 1
        progress["next_variation_page"] = 1
        progress.pop("current_parent_product_id", None)
    progress["heartbeat_at"] = datetime.now(timezone.utc).isoformat()
    progress["message"] = f"Variation page {variation_page} for product {product_id} was staged."
    run.total_remote_records = catalog_row_count(db, run.id)
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def finish_product_page(db: Session, run: WooCommerceSyncRun) -> WooCommerceSyncRun:
    progress = dict(run.progress or {})
    page = int(progress["active_product_page"])
    has_more = bool(progress.get("active_product_page_has_more"))
    progress.update({
        "next_product_page": page + 1,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    })
    for key in (
        "active_product_page",
        "active_product_page_has_more",
        "pending_variation_parent_keys",
        "variation_parent_index",
        "next_variation_page",
        "current_parent_product_id",
    ):
        progress.pop(key, None)
    if has_more:
        run.status = "fetching_products"
        progress.update({"stage": "fetching_products", "message": f"Catalog page {page} completed; continuing."})
    elif progress.get("scan_pass") != "delta":
        run.status = "fetching_products"
        progress.update({
            "stage": "fetching_products",
            "scan_pass": "delta",
            "next_product_page": 1,
            "message": "Full catalog captured; reconciling products changed during the scan.",
        })
    else:
        if progress.get("scan_mode", "full") == "full":
            record_missing_remote_identities(db, run.id)
        run.status = "matching"
        progress.update({
            "stage": "matching",
            "scan_complete": True,
            "delta_complete": True,
            "message": (
                "WooCommerce catalog and final change reconciliation captured; matching local items."
                if progress.get("scan_mode", "full") == "full"
                else "New and changed WooCommerce products captured; matching local items."
            ),
        })
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def stage_catalog_record(db: Session, sync_run_id: int, page: int, index: int, remote: dict[str, Any]) -> WooCatalogSyncRow:
    raw = remote if isinstance(remote, dict) else {"invalid": repr(remote)}
    remote_key = catalog_remote_key(raw, page, index)
    row = db.scalar(select(WooCatalogSyncRow).where(
        WooCatalogSyncRow.sync_run_id == sync_run_id,
        WooCatalogSyncRow.remote_key == remote_key,
    ))
    try:
        record = normalize_remote_record(
            raw.get("product") or {},
            raw.get("variation"),
            parent_container=bool(raw.get("parent_container")),
        )
        values = {
            "remote_type": record.remote_type,
            "woo_product_id": record.woo_product_id,
            "woo_variation_id": record.woo_variation_id,
            "sku": record.sku or None,
            "normalized_sku": normalize_key(record.sku) or None,
            "barcode": record.barcode or None,
            "product_name": record.name or None,
            "raw_payload": raw,
        }
    except Exception as error:
        product = raw.get("product") if isinstance(raw.get("product"), dict) else {}
        variation = raw.get("variation") if isinstance(raw.get("variation"), dict) else {}
        values = {
            "remote_type": "malformed",
            "woo_product_id": safe_int(product.get("id")),
            "woo_variation_id": safe_int(variation.get("id")),
            "sku": str((variation or product).get("sku") or "") or None,
            "normalized_sku": normalize_key((variation or product).get("sku")) or None,
            "barcode": None,
            "product_name": str((variation or product).get("name") or product.get("name") or "") or None,
            "raw_payload": raw,
            "status": "needs_attention",
            "action": "attention",
            "message": f"WooCommerce returned a malformed catalog record: {str(error)[:500]}",
        }
    if row is None:
        row = WooCatalogSyncRow(sync_run_id=sync_run_id, remote_key=remote_key, **values)
        db.add(row)
    elif row.status in {"staged", "needs_attention"} and row.resolution_action is None:
        for key, value in values.items():
            setattr(row, key, value)
        if "status" not in values:
            row.status = "staged"
            row.action = "pending"
            row.message = None
    return row


def apply_catalog_rows(db: Session, sync_run_id: int) -> None:
    sku_counts = Counter(
        sku for sku in db.scalars(
            select(WooCatalogSyncRow.normalized_sku).where(
                WooCatalogSyncRow.sync_run_id == sync_run_id,
                WooCatalogSyncRow.remote_type.in_({"simple", "variation"}),
                WooCatalogSyncRow.normalized_sku.is_not(None),
            )
        ).all() if sku
    )
    duplicate_remote_skus = {sku for sku, count in sku_counts.items() if count > 1}
    run = require_catalog_run(db, sync_run_id)
    if run.status == "cancelled":
        return
    rows = list(db.scalars(
        select(WooCatalogSyncRow)
        .where(WooCatalogSyncRow.sync_run_id == sync_run_id, WooCatalogSyncRow.status == "staged")
        .order_by(WooCatalogSyncRow.id)
        .limit(CATALOG_APPLY_BATCH_SIZE)
    ).all())
    for row in rows:
        savepoint = db.begin_nested()
        try:
            apply_catalog_row(db, row, duplicate_remote_skus)
            savepoint.commit()
        except Exception as error:
            prior_resolution = row.resolution_action
            prior_actor = row.resolved_by
            savepoint.rollback()
            row = db.get(WooCatalogSyncRow, row.id)
            row.status = "needs_attention"
            row.action = "attention"
            prefix = f"Resolution '{prior_resolution}' by {prior_actor} failed. " if prior_resolution else ""
            row.message = (prefix + str(error))[:1000]
            row.resolution_action = None
            row.resolution_item_id = None
    db.flush()
    update_catalog_counts(db, run)
    progress = dict(run.progress or {})
    progress.update({
        "stage": "applying",
        "processed_records": outcome_row_count(db, sync_run_id),
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "message": "Applied one safe catalog batch.",
    })
    run.progress = progress
    db.commit()


def apply_catalog_row(db: Session, row: WooCatalogSyncRow, duplicate_remote_skus: set[str]) -> None:
    if row.resolution_action == "skip":
        row.status = "skipped"
        row.action = "skipped"
        row.message = f"Explicitly skipped by {row.resolved_by}."
        return
    record = normalized_row(row)
    if record.parent_container or record.remote_type == "variable":
        row.status = "skipped"
        row.action = "context"
        row.message = "Variable parent retained as catalog context; variations are inventory units."
        return
    if record.remote_type not in {"simple", "variation"}:
        raise ValueError(f"Unsupported WooCommerce product type '{record.remote_type}' needs attention.")
    hard_item, hard_conflict = hard_identity_match(db, record)
    if hard_conflict:
        raise ValueError(hard_conflict)
    if hard_item is None and not record.sku and row.resolution_action is None:
        raise ValueError("WooCommerce item has no SKU and needs an explicit Link or Create decision.")
    item: InventoryItem | None
    match_kind: str
    if row.resolution_action == "create":
        if hard_item is not None:
            raise ValueError("WooCommerce identity already belongs to an inventory item; explicit create was not applied.")
        item, match_kind = None, "create"
    elif row.resolution_action == "link":
        item = db.scalar(select(InventoryItem).where(InventoryItem.id == row.resolution_item_id).with_for_update())
        if item is None:
            raise ValueError("Resolved inventory item no longer exists.")
        conflict = target_conflict(db, item, record)
        if conflict:
            raise ValueError(conflict)
        match_kind = "link"
    elif hard_item is not None:
        item, match_kind = hard_item, "identity"
    else:
        if record.sku and normalize_key(record.sku) in duplicate_remote_skus:
            raise ValueError(f"Duplicate WooCommerce SKU '{record.sku}' needs an explicit resolution.")
        sku_items = unique_sku_matches(db, record.sku)
        if len(sku_items) > 1:
            raise ValueError(f"Duplicate local SKU '{record.sku}' needs an explicit resolution.")
        item = sku_items[0] if sku_items else None
        if item is not None:
            conflict = target_conflict(db, item, record)
            if conflict:
                raise ValueError(conflict)
            match_kind = "link"
        else:
            match_kind = "create"

    if item is not None:
        item = db.scalar(
            select(InventoryItem)
            .where(InventoryItem.id == item.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item is None:
            raise ValueError("Matched inventory item no longer exists.")

    synced_at = datetime.now(timezone.utc)
    if item is None:
        item = create_item_from_woo(record, synced_at)
        db.add(item)
        db.flush()
        ensure_mapping_record(db, item, record)
        opening_stock = record.stock_quantity if record.manage_stock and record.stock_quantity is not None else Decimal("0")
        if opening_stock < 0:
            raise ValueError("WooCommerce stock is negative and cannot be used as Pongo opening stock.")
        if opening_stock > 0:
            location = db.scalar(
                select(InventoryLocation)
                .where(InventoryLocation.active.is_(True))
                .order_by(InventoryLocation.is_default.desc(), InventoryLocation.id)
            )
            run = db.get(WooCommerceSyncRun, row.sync_run_id)
            set_opening_balance(
                db,
                item.id,
                in_stock=opening_stock,
                allocated=Decimal("0"),
                warehouse=(location.warehouse if location else None) or "Main Warehouse",
                inventory_location=((location.location_code or location.location_name) if location else None) or "UNASSIGNED",
                idempotency_key=f"woo-catalog:{row.sync_run_id}:{row.id}",
                created_by=run.created_by if run else "system",
                reference_type="woocommerce_catalog_sync",
                reference_id=row.id,
                reason="Opening stock imported from WooCommerce",
                commit=False,
            )
        row.status = "created"
        row.action = "created"
        row.message = f"Created with WooCommerce opening stock {opening_stock:g} and mapped to WooCommerce."
    else:
        seeded_barcode = not item.barcode and bool(record.barcode)
        changed = woo_snapshot_changed(item, record) or seeded_barcode
        if seeded_barcode:
            item.barcode = record.barcode
        attach_woo_mapping(item, record, synced_at)
        ensure_mapping_record(db, item, record)
        row.local_item_id = item.id
        if match_kind == "link":
            row.status = "linked"
            row.action = "linked"
            row.message = "Linked by exact unique SKU; local item fields and stock were preserved."
        elif changed:
            row.status = "updated"
            row.action = "updated"
            row.message = "Refreshed WooCommerce-owned snapshot fields; local item fields and stock were preserved."
        else:
            row.status = "unchanged"
            row.action = "unchanged"
            row.message = "Existing WooCommerce identity is already current."
    row.local_item_id = item.id


def hard_identity_match(db: Session, record: NormalizedWooRecord) -> tuple[InventoryItem | None, str | None]:
    if record.woo_variation_id is None:
        mappings = list(db.scalars(select(WooItemMapping).where(
            WooItemMapping.woo_product_id == record.woo_product_id,
            WooItemMapping.woo_variation_id.is_(None),
            WooItemMapping.active.is_(True),
        )).all())
    else:
        mappings = list(db.scalars(select(WooItemMapping).where(
            WooItemMapping.woo_variation_id == record.woo_variation_id,
            WooItemMapping.active.is_(True),
        )).all())
        if any(mapping.woo_product_id != record.woo_product_id for mapping in mappings):
            return None, "WooCommerce variation ID is mapped under a different parent product."
    if len(mappings) > 1:
        return None, "Multiple active mappings exist for this WooCommerce identity."
    if record.woo_variation_id is None:
        embedded = list(db.scalars(select(InventoryItem).where(
            InventoryItem.woo_product_id == record.woo_product_id,
            InventoryItem.woo_variation_id.is_(None),
        )).all())
    else:
        variation_matches = list(db.scalars(select(InventoryItem).where(
            InventoryItem.woo_variation_id == record.woo_variation_id,
        )).all())
        if any(item.woo_product_id != record.woo_product_id for item in variation_matches):
            return None, "WooCommerce variation ID is attached to a different parent product."
        embedded = variation_matches
    if len(embedded) > 1:
        return None, "WooCommerce identity is embedded in multiple inventory items."
    mapped = db.get(InventoryItem, mappings[0].item_id) if mappings else None
    direct = embedded[0] if embedded else None
    if mapped is not None and direct is not None and mapped.id != direct.id:
        return None, "Explicit mapping and embedded WooCommerce identity point to different inventory items."
    return mapped or direct, None


def target_conflict(db: Session, item: InventoryItem, record: NormalizedWooRecord) -> str | None:
    if item.non_inventory:
        return "Non-inventory records cannot be linked to a sellable WooCommerce inventory unit."
    local_identity = (item.woo_product_id, item.woo_variation_id)
    remote_identity = (record.woo_product_id, record.woo_variation_id)
    if item.woo_product_id is not None and local_identity != remote_identity:
        return "Selected inventory item is already attached to a different WooCommerce identity."
    item_mappings = list(db.scalars(select(WooItemMapping).where(
        WooItemMapping.item_id == item.id,
        WooItemMapping.active.is_(True),
    )).all())
    if any((mapping.woo_product_id, mapping.woo_variation_id) != remote_identity for mapping in item_mappings):
        return "Selected inventory item already has a different active WooCommerce mapping."
    remote_item, conflict = hard_identity_match(db, record)
    if conflict:
        return conflict
    if remote_item is not None and remote_item.id != item.id:
        return "WooCommerce identity already belongs to another inventory item."
    return None


def unique_sku_matches(db: Session, sku: str | None) -> list[InventoryItem]:
    if not sku:
        return []
    return list(db.scalars(select(InventoryItem).where(
        func.lower(func.trim(InventoryItem.sku)) == normalize_key(sku)
    )).all())


def woo_snapshot_changed(item: InventoryItem, record: NormalizedWooRecord) -> bool:
    fields = {
        "woo_product_id": record.woo_product_id,
        "woo_variation_id": record.woo_variation_id,
        "woo_product_type": record.remote_type,
        "woo_name": record.name,
        "woo_parent_name": record.parent_name if record.woo_variation_id is not None else None,
        "woo_variation_attributes": record.variation_attributes or None,
        "woo_permalink": record.permalink,
        "woo_status": record.status,
        "woo_manage_stock": record.manage_stock,
        "woo_stock_status": record.stock_status,
        "woo_stock_quantity_snapshot": record.stock_quantity,
    }
    return any(getattr(item, key, None) != value for key, value in fields.items())


def normalized_row(row: WooCatalogSyncRow) -> NormalizedWooRecord:
    raw = row.raw_payload or {}
    return normalize_remote_record(
        raw.get("product") or {},
        raw.get("variation"),
        parent_container=bool(raw.get("parent_container")),
    )


def catalog_remote_key(remote: dict[str, Any], page: int, index: int) -> str:
    product = remote.get("product") if isinstance(remote.get("product"), dict) else {}
    variation = remote.get("variation") if isinstance(remote.get("variation"), dict) else {}
    product_id = safe_int(product.get("id"))
    variation_id = safe_int(variation.get("id"))
    if product_id is not None and variation_id is not None:
        return f"variation:{product_id}:{variation_id}"
    if product_id is not None:
        return f"product:{product_id}"
    digest = sha256(json.dumps(remote, sort_keys=True, default=str).encode()).hexdigest()[:24]
    return f"malformed:{page}:{index}:{digest}"


def update_catalog_counts(db: Session, run: WooCommerceSyncRun) -> None:
    counts = dict(db.execute(
        select(WooCatalogSyncRow.status, func.count(WooCatalogSyncRow.id))
        .where(WooCatalogSyncRow.sync_run_id == run.id)
        .group_by(WooCatalogSyncRow.status)
    ).all())
    run.created_count = int(counts.get("created", 0))
    run.updated_count = int(counts.get("updated", 0))
    run.matched_count = int(counts.get("linked", 0))
    run.skipped_count = int(counts.get("skipped", 0))
    run.conflict_count = int(counts.get("needs_attention", 0))
    run.error_count = int(counts.get("failed", 0))
    progress = dict(run.progress or {})
    progress["unchanged_count"] = int(counts.get("unchanged", 0))
    progress["created_item_ids"] = list(db.scalars(
        select(WooCatalogSyncRow.local_item_id)
        .where(
            WooCatalogSyncRow.sync_run_id == run.id,
            WooCatalogSyncRow.status == "created",
            WooCatalogSyncRow.local_item_id.is_not(None),
        )
        .distinct()
    ).all())
    run.progress = progress


def outcome_row_count(db: Session, sync_run_id: int) -> int:
    return int(db.scalar(select(func.count(WooCatalogSyncRow.id)).where(
        WooCatalogSyncRow.sync_run_id == sync_run_id,
        WooCatalogSyncRow.status != "staged",
    )) or 0)


def finalize_catalog_sync(db: Session, sync_run_id: int) -> WooCommerceSyncRun:
    run = require_catalog_run(db, sync_run_id, lock=True)
    if run.status == "cancelled":
        return run
    update_catalog_counts(db, run)
    unresolved = run.conflict_count + run.error_count
    run.status = "completed_with_attention" if unresolved else "completed"
    run.completed_at = datetime.now(timezone.utc)
    progress = dict(run.progress or {})
    progress.update({
        "stage": run.status,
        "processed_records": run.total_remote_records,
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "message": (
            f"Catalog sync completed with {unresolved} row{'s' if unresolved != 1 else ''} needing attention."
            if unresolved
            else "Catalog sync completed."
        ),
    })
    progress.pop("next_retry_at", None)
    run.progress = progress
    prune_catalog_stage_rows(db)
    db.commit()
    db.refresh(run)
    return run


def record_catalog_failure(
    db: Session,
    sync_run_id: int,
    error: Exception,
    *,
    retry_after: str | None = None,
) -> WooCommerceSyncRun:
    run = require_catalog_run(db, sync_run_id, lock=True)
    if run.status == "cancelled":
        return run
    message = error.message if isinstance(error, WooCommerceClientError) else str(error)
    status_code = error.status_code if isinstance(error, WooCommerceClientError) else None
    retryable = status_code == 429 or (status_code is not None and status_code >= 500)
    if status_code is None:
        lowered = message.casefold()
        retryable = "timed out" in lowered or "request failed" in lowered or not isinstance(error, WooCommerceClientError)
    run.attempt_count += 1
    progress = dict(run.progress or {})
    progress["worker_error_count"] = int(progress.get("worker_error_count") or 0) + 1
    if retryable and run.attempt_count < CATALOG_MAX_ATTEMPTS:
        delay = retry_after_seconds(retry_after) or (5, 15, 45)[run.attempt_count - 1]
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        run.status = "waiting_retry"
        progress.update({
            "next_retry_at": retry_at.isoformat(),
            "message": f"WooCommerce is temporarily unavailable. Retrying automatically in {delay} seconds.",
        })
    else:
        run.status = "paused"
        progress.update({
            "message": f"Catalog sync paused: {message[:500]}",
        })
        progress.pop("next_retry_at", None)
    run.notes = message[:2000]
    run.progress = progress
    db.commit()
    db.refresh(run)
    return run


def prune_catalog_stage_rows(db: Session, *, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=CATALOG_STAGE_RETENTION_DAYS)
    result = db.execute(
        delete(WooCatalogSyncRow).where(
            WooCatalogSyncRow.updated_at < cutoff,
            WooCatalogSyncRow.status.not_in({"needs_attention", "staged"}),
            WooCatalogSyncRow.resolution_action.is_(None),
        ).execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def record_missing_remote_identities(db: Session, sync_run_id: int) -> int:
    seen = set(db.execute(select(
        WooCatalogSyncRow.woo_product_id,
        WooCatalogSyncRow.woo_variation_id,
    ).where(
        WooCatalogSyncRow.sync_run_id == sync_run_id,
        WooCatalogSyncRow.remote_type.in_({"simple", "variation"}),
    )).all())
    local_identities: dict[tuple[int, int, int | None], str] = {}
    for mapping in db.scalars(select(WooItemMapping).where(WooItemMapping.active.is_(True))).all():
        local_identities[(mapping.item_id, mapping.woo_product_id, mapping.woo_variation_id)] = "active mapping"
    for item in db.scalars(select(InventoryItem).where(InventoryItem.woo_product_id.is_not(None))).all():
        local_identities.setdefault((item.id, item.woo_product_id, item.woo_variation_id), "embedded identity")

    created = 0
    for (item_id, product_id, variation_id), source in local_identities.items():
        if (product_id, variation_id) in seen:
            continue
        remote_key = f"missing:{item_id}:{product_id}:{variation_id or 0}"
        row = db.scalar(select(WooCatalogSyncRow).where(
            WooCatalogSyncRow.sync_run_id == sync_run_id,
            WooCatalogSyncRow.remote_key == remote_key,
        ))
        if row is None:
            row = WooCatalogSyncRow(
                sync_run_id=sync_run_id,
                remote_key=remote_key,
                remote_type="missing_remote",
                woo_product_id=product_id,
                woo_variation_id=variation_id,
                local_item_id=item_id,
                raw_payload={"missing_remote_identity": True, "source": source},
            )
            db.add(row)
            created += 1
        row.status = "needs_attention"
        row.action = "attention"
        row.message = "Previously linked WooCommerce identity was not returned by the completed full scan; the mapping was preserved for manual review."
    return created


def require_catalog_run(db: Session, sync_run_id: int, *, lock: bool = False) -> WooCommerceSyncRun:
    statement = select(WooCommerceSyncRun).where(
        WooCommerceSyncRun.id == sync_run_id,
        WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
    )
    if lock:
        statement = statement.with_for_update()
    run = db.scalar(statement.execution_options(populate_existing=True))
    if run is None:
        raise ValueError("Catalog sync run not found.")
    return run


def catalog_cancelled(db: Session, sync_run_id: int) -> bool:
    db.expire_all()
    status = db.scalar(select(WooCommerceSyncRun.status).where(
        WooCommerceSyncRun.id == sync_run_id,
        WooCommerceSyncRun.sync_type == CATALOG_SYNC_TYPE,
    ))
    return status == "cancelled"


def catalog_row_count(db: Session, sync_run_id: int) -> int:
    return int(db.scalar(select(func.count(WooCatalogSyncRow.id)).where(
        WooCatalogSyncRow.sync_run_id == sync_run_id,
    )) or 0)


def client_page_has_more(client: WooCommerceClient, page: int, returned_count: int, page_size: int) -> bool:
    page_has_more = getattr(client, "page_has_more", None)
    if callable(page_has_more):
        return bool(page_has_more(page, returned_count, page_size))
    total_pages = getattr(client, "last_response_headers", {}).get("x-wp-totalpages")
    try:
        return page < int(total_pages) if total_pages is not None else returned_count == page_size
    except (TypeError, ValueError):
        return returned_count == page_size


def retry_after_seconds(value: str | None, *, now: datetime | None = None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value.strip())
    except (TypeError, ValueError, AttributeError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = max(1, int((retry_at - (now or datetime.now(timezone.utc))).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return None
    return max(1, min(seconds, 3600))


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
