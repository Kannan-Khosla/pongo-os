from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.inventory import InventoryItem
from app.models.orders import Order, OrderItem
from app.models.woocommerce import WooItemMapping, WooWritebackQueue
from app.schemas.woocommerce import (
    WooWritebackOrderStatusPreviewRequest,
    WooWritebackPreviewResponse,
    WooWritebackQueueCreateRequest,
    WooWritebackQueueListResponse,
    WooWritebackQueueRead,
    WooStockSyncResponse,
    WooWritebackStockPreviewRequest,
)
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError

ALLOWED_OPERATION_TYPES = {"update_product_stock", "update_variation_stock", "update_order_status"}
ORDER_STATUS_ALLOWLIST = {"pending", "processing", "on-hold", "completed", "cancelled"}


def sync_inventory_stock(
    db: Session,
    settings: Settings,
    client: WooCommerceClient,
    *,
    item_ids: list[int] | set[int] | None = None,
    force: bool = False,
    requested_by: str = "inventory-page",
    should_cancel: Callable[[], bool] | None = None,
) -> WooStockSyncResponse:
    statement = select(InventoryItem).where(InventoryItem.active.is_(True), InventoryItem.non_inventory.is_not(True)).order_by(InventoryItem.id)
    if item_ids is not None:
        selected_ids = list(dict.fromkeys(item_ids))
        if not selected_ids:
            return stock_sync_response("no_changes", force, 0, 0, 0, 0, 0, 0, 0)
        statement = statement.where(InventoryItem.id.in_(selected_ids))
    items = list(db.scalars(statement).all())
    attach_order_line_mappings(db, items)
    mapped = [item for item in items if item.woo_product_id]
    skipped_unmapped = len(items) - len(mapped)
    targets = mapped if force else [item for item in mapped if stock_snapshot_changed(item)]
    unchanged = len(mapped) - len(targets)

    if not stock_writeback_enabled(settings):
        return stock_sync_response(
            "disabled",
            force,
            len(items),
            len(targets),
            0,
            0,
            0,
            skipped_unmapped,
            unchanged,
            errors=["WooCommerce stock writeback is not enabled for this environment."],
        )
    if not targets:
        return stock_sync_response("no_changes", force, len(items), 0, 0, 0, 0, skipped_unmapped, unchanged)

    sent_count = 0
    dry_run_count = 0
    failed_count = 0
    failed_item_ids: list[int] = []
    queue_ids: list[int] = []
    errors: list[str] = []
    cancelled = False
    # ponytail: Sequential sends preserve the existing per-item queue/audit trail; move this loop to a worker only if full-catalog requests exceed deployment limits.
    for item in targets:
        if should_cancel and should_cancel():
            cancelled = True
            break
        try:
            preview = preview_stock_writeback(
                db,
                settings,
                client,
                WooWritebackStockPreviewRequest(item_id=item.id, fetch_live=False),
            )
            if preview is None or not preview.woo_product_id:
                raise ValueError("Inventory item is not linked to WooCommerce.")
            queue = create_queue_item(
                db,
                settings,
                WooWritebackQueueCreateRequest(
                    operation_type=preview.operation_type,
                    entity_type=preview.entity_type,
                    entity_id=preview.entity_id,
                    woo_entity_id=preview.woo_entity_id,
                    woo_product_id=preview.woo_product_id,
                    woo_variation_id=preview.woo_variation_id,
                    payload_json=preview.payload_json,
                    preview_json=preview.preview_json,
                    requested_by=requested_by,
                ),
            )
            queue_ids.append(queue.id)
            approve_queue_item(db, queue.id, approved_by=requested_by)
            result = send_queue_item(db, client, settings, queue.id)
            if result and result.status == "sent":
                sent_count += 1
            elif result and result.status == "dry_run":
                dry_run_count += 1
            else:
                failed_count += 1
                failed_item_ids.append(item.id)
                if len(errors) < 20:
                    errors.append(f"{item.sku or item.id}: {(result.error_message if result else None) or 'WooCommerce stock update failed.'}")
        except Exception as error:
            failed_count += 1
            failed_item_ids.append(item.id)
            if len(errors) < 20:
                errors.append(f"{item.sku or item.id}: {error}")

    if cancelled:
        status = "cancelled"
    elif failed_count and (sent_count or dry_run_count):
        status = "partial"
    elif failed_count:
        status = "failed"
    elif dry_run_count and not sent_count:
        status = "dry_run"
    else:
        status = "sent"
    return stock_sync_response(
        status,
        force,
        len(items),
        len(targets),
        sent_count,
        dry_run_count,
        failed_count,
        skipped_unmapped,
        unchanged,
        queue_ids=queue_ids,
        errors=errors,
        failed_item_ids=failed_item_ids,
    )


def stock_snapshot_changed(item: InventoryItem) -> bool:
    return item.woo_stock_quantity_snapshot is None or Decimal(str(item.sellable or 0)) != Decimal(str(item.woo_stock_quantity_snapshot))


def attach_order_line_mappings(db: Session, items: list[InventoryItem]) -> None:
    unmapped = [item for item in items if not item.woo_product_id]
    if not unmapped:
        return
    candidates: dict[int, set[tuple[int, int | None]]] = {}
    rows = db.execute(
        select(OrderItem.inventory_item_id, OrderItem.woo_product_id, OrderItem.woo_variation_id)
        .where(
            OrderItem.inventory_item_id.in_([item.id for item in unmapped]),
            OrderItem.woo_product_id.is_not(None),
            OrderItem.matched_status == "matched",
        )
        .distinct()
    ).all()
    for item_id, product_id, variation_id in rows:
        candidates.setdefault(item_id, set()).add((product_id, variation_id or None))
    changed = False
    for item in unmapped:
        matches = candidates.get(item.id, set())
        if len(matches) == 1:
            item.woo_product_id, item.woo_variation_id = next(iter(matches))
            item.woo_product_type = "variation" if item.woo_variation_id else "simple"
            item.woo_sync_status = "mapped_from_order"
            changed = True
    if changed:
        db.commit()


def stock_writeback_enabled(settings: Settings) -> bool:
    return bool(
        getattr(settings, "woocommerce_writeback_enabled", False)
        and not getattr(settings, "woocommerce_read_only", True)
        and getattr(settings, "woocommerce_allow_stock_write", False)
    )


def stock_sync_response(
    status: str,
    force: bool,
    requested_count: int,
    candidate_count: int,
    sent_count: int,
    dry_run_count: int,
    failed_count: int,
    skipped_unmapped_count: int,
    unchanged_count: int,
    *,
    queue_ids: list[int] | None = None,
    errors: list[str] | None = None,
    failed_item_ids: list[int] | None = None,
) -> WooStockSyncResponse:
    return WooStockSyncResponse(
        status=status,
        mode="all" if force else "changed",
        requested_count=requested_count,
        candidate_count=candidate_count,
        sent_count=sent_count,
        dry_run_count=dry_run_count,
        failed_count=failed_count,
        skipped_unmapped_count=skipped_unmapped_count,
        unchanged_count=unchanged_count,
        queue_ids=queue_ids or [],
        errors=errors or [],
        failed_item_ids=failed_item_ids or [],
    )


def sync_completed_order_status(
    db: Session,
    settings: Settings,
    client: WooCommerceClient,
    order_id: int,
    requested_by: str | None = None,
) -> WooWritebackQueue:
    preview = preview_order_status_writeback(
        db,
        settings,
        client,
        WooWritebackOrderStatusPreviewRequest(order_id=order_id, proposed_status="completed", fetch_live=False),
    )
    if preview is None:
        raise ValueError("Local order was not found for WooCommerce completion writeback.")
    if not preview.woo_order_id:
        raise ValueError("Order is not linked to a WooCommerce order.")
    queue = create_queue_item(
        db,
        settings,
        WooWritebackQueueCreateRequest(
            operation_type=preview.operation_type,
            entity_type=preview.entity_type,
            entity_id=preview.entity_id,
            woo_entity_id=preview.woo_entity_id,
            woo_order_id=preview.woo_order_id,
            payload_json=preview.payload_json,
            preview_json=preview.preview_json,
            requested_by=requested_by or "order-completion",
        ),
    )
    approve_queue_item(db, queue.id, approved_by=requested_by or "order-completion")
    sent = send_queue_item(db, client, settings, queue.id)
    if sent is None:
        raise ValueError("WooCommerce completion writeback queue item disappeared before send.")
    return sent


def preview_stock_writeback(db: Session, settings: Settings, client: WooCommerceClient, payload: WooWritebackStockPreviewRequest) -> WooWritebackPreviewResponse | None:
    item = find_item(db, item_id=payload.item_id, sku=payload.sku)
    if item is None:
        return None
    validate_item_mapping(db, item)
    woo_entity_id = item.woo_variation_id or item.woo_product_id
    proposed = Decimal(str(payload.proposed_stock_quantity)) if payload.proposed_stock_quantity is not None else item.sellable
    operation_type = "update_variation_stock" if item.woo_variation_id else "update_product_stock"
    endpoint_path = product_stock_path(item)
    body = {
        "manage_stock": True,
        "stock_quantity": float(proposed),
        "stock_status": "instock" if proposed > 0 else "outofstock",
    }
    if payload.proposed_stock_status:
        body["stock_status"] = payload.proposed_stock_status.strip().lower()
    request_payload = {
        "method": "PATCH",
        "path": endpoint_path,
        "body": body,
    }
    live_woo = None
    live_error = None
    if payload.fetch_live and item.woo_product_id:
        try:
            live_woo = client.get_product_variation(item.woo_product_id, item.woo_variation_id) if item.woo_variation_id else client.get_product(item.woo_product_id)
        except WooCommerceClientError as error:
            live_error = error.message
    preview = {
        "item_id": item.id,
        "sku": item.sku,
        "description": item.description,
        "woo_product_id": item.woo_product_id,
        "woo_variation_id": item.woo_variation_id,
        "current_local_stock": decimal_to_float(item.in_stock),
        "current_local_allocated": decimal_to_float(item.allocated),
        "current_local_sellable": decimal_to_float(item.sellable),
        "woo_stock_snapshot": decimal_to_float(item.woo_stock_quantity_snapshot),
        "woo_stock_status": item.woo_stock_status,
        "live_woo_stock": live_woo.get("stock_quantity") if live_woo else None,
        "live_woo_stock_status": live_woo.get("stock_status") if live_woo else None,
        "proposed_woo_stock": decimal_to_float(proposed),
        "proposed_stock_status": body.get("stock_status"),
        "method": "PATCH",
        "path": endpoint_path,
    }
    warnings = []
    if live_error:
        warnings.append(f"Live Woo stock check failed: {live_error}")
    return WooWritebackPreviewResponse(
        operation_type=operation_type,
        entity_type="inventory_item",
        entity_id=item.id,
        woo_entity_id=woo_entity_id,
        woo_product_id=item.woo_product_id,
        woo_variation_id=item.woo_variation_id,
        payload_json=request_payload,
        preview_json=preview,
        environment=settings.woocommerce_environment,
        dry_run=settings.woocommerce_writeback_dry_run,
        warnings=warnings,
    )


def preview_order_status_writeback(db: Session, settings: Settings, client: WooCommerceClient, payload: WooWritebackOrderStatusPreviewRequest) -> WooWritebackPreviewResponse | None:
    order = find_order(db, order_id=payload.order_id, woo_order_id=payload.woo_order_id)
    if order is None:
        return None
    proposed_status = payload.proposed_status.strip().lower()
    request_payload = {
        "method": "PUT",
        "path": f"/wp-json/wc/v3/orders/{order.woo_order_id}",
        "body": {"status": proposed_status},
    }
    warnings = []
    if proposed_status not in ORDER_STATUS_ALLOWLIST:
        warnings.append("Proposed WooCommerce order status is not in the local status allowlist.")
    if not order.woo_order_id:
        warnings.append("Local order is not linked to a WooCommerce order.")
    live_woo = None
    live_error = None
    if payload.fetch_live and order.woo_order_id:
        try:
            live_woo = client.get_order(order.woo_order_id)
        except WooCommerceClientError as error:
            live_error = error.message
    if live_error:
        warnings.append(f"Live Woo order check failed: {live_error}")
    preview = {
        "order_id": order.id,
        "woo_order_id": order.woo_order_id,
        "woo_order_number": order.woo_order_number or order.order_number,
        "customer_name": order.customer_name,
        "current_local_status": order.local_status,
        "current_woo_status": order.woo_status or order.status,
        "live_woo_status": live_woo.get("status") if live_woo else None,
        "proposed_status": proposed_status,
        "method": "PUT",
        "path": request_payload["path"],
    }
    return WooWritebackPreviewResponse(
        operation_type="update_order_status",
        entity_type="order",
        entity_id=order.id,
        woo_entity_id=order.woo_order_id,
        woo_order_id=order.woo_order_id,
        payload_json=request_payload,
        preview_json=preview,
        environment=settings.woocommerce_environment,
        dry_run=settings.woocommerce_writeback_dry_run,
        warnings=warnings,
    )


def create_queue_item(db: Session, settings: Settings, payload: WooWritebackQueueCreateRequest) -> WooWritebackQueue:
    validate_queue_payload(payload)
    row = WooWritebackQueue(
        operation_type=payload.operation_type,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        woo_entity_id=payload.woo_entity_id,
        woo_product_id=payload.woo_product_id,
        woo_variation_id=payload.woo_variation_id,
        woo_order_id=payload.woo_order_id,
        payload_json=payload.payload_json,
        status="pending",
        environment=settings.woocommerce_environment,
        dry_run=settings.woocommerce_writeback_dry_run,
        allowed_host=settings.woocommerce_allowed_host or None,
        preview_json=payload.preview_json,
        requested_by=payload.requested_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_queue(db: Session, status: str | None = None) -> WooWritebackQueueListResponse:
    statement = select(WooWritebackQueue).order_by(WooWritebackQueue.created_at.desc(), WooWritebackQueue.id.desc())
    if status:
        statement = statement.where(WooWritebackQueue.status == status)
    rows = list(db.scalars(statement).all())
    return WooWritebackQueueListResponse(queue=[queue_to_read(row) for row in rows], total=len(rows))


def get_queue_item(db: Session, queue_id: int) -> WooWritebackQueue | None:
    return db.get(WooWritebackQueue, queue_id)


def approve_queue_item(db: Session, queue_id: int, approved_by: str | None = None) -> WooWritebackQueue | None:
    row = db.get(WooWritebackQueue, queue_id)
    if row is None:
        return None
    if row.status in {"pending", "failed"}:
        validate_queue_mapping(db, row)
        row.status = "approved"
        row.approved_by = approved_by
        row.approved_at = datetime.now(timezone.utc)
        row.error_message = None
        db.commit()
        db.refresh(row)
    return row


def cancel_queue_item(db: Session, queue_id: int) -> WooWritebackQueue | None:
    row = db.get(WooWritebackQueue, queue_id)
    if row is None:
        return None
    if row.status in {"pending", "approved", "failed"}:
        row.status = "cancelled"
        db.commit()
        db.refresh(row)
    return row


def send_queue_item(db: Session, client: WooCommerceClient, settings: Settings, queue_id: int) -> WooWritebackQueue | None:
    row = db.get(WooWritebackQueue, queue_id)
    if row is None:
        return None
    if row.status != "approved":
        if row.status == "pending":
            row.status = "failed"
            row.error_message = "Writeback must be approved before send."
            db.commit()
            db.refresh(row)
        return row
    try:
        validate_queue_mapping(db, row)
    except ValueError as error:
        row.status = "failed"
        row.error_message = str(error)
        db.commit()
        db.refresh(row)
        return row
    if settings.woocommerce_writeback_dry_run or row.dry_run:
        row.status = "dry_run"
        row.sent_at = datetime.now(timezone.utc)
        row.response_json = {"dry_run": True, "message": "Dry-run blocked live WooCommerce send. No WooCommerce request was made."}
        db.commit()
        db.refresh(row)
        return row
    try:
        method = str(row.payload_json.get("method") or "PATCH").upper()
        path = str(row.payload_json.get("path") or "")
        body = row.payload_json.get("body") or {}
        if row.operation_type == "update_order_status" and method == "PATCH":
            method = "PUT"
            row.payload_json = {**row.payload_json, "method": "PUT"}
        response = client.guarded_write(row.operation_type, method, path, body)
        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)
        row.response_json = response
        row.error_message = None
        apply_successful_snapshot_update(db, row, response)
    except WooCommerceClientError as error:
        row.status = "failed"
        row.error_message = f"{error.message} (HTTP {error.status_code})" if error.status_code else error.message
    db.commit()
    db.refresh(row)
    return row


def validate_queue_payload(payload: WooWritebackQueueCreateRequest) -> None:
    if payload.operation_type not in ALLOWED_OPERATION_TYPES:
        raise ValueError("Writeback operation is not allowlisted.")
    method = str(payload.payload_json.get("method") or "").upper()
    if method == "DELETE":
        raise ValueError("WooCommerce DELETE is blocked.")
    if payload.operation_type == "update_order_status":
        proposed = str((payload.payload_json.get("body") or {}).get("status") or "").strip().lower()
        if proposed not in ORDER_STATUS_ALLOWLIST:
            raise ValueError("Order status is not allowlisted.")
    if payload.operation_type in {"update_product_stock", "update_variation_stock"} and "stock_quantity" not in (payload.payload_json.get("body") or {}):
        raise ValueError("Stock writeback payload must include stock_quantity.")


def validate_item_mapping(db: Session, item: InventoryItem) -> WooItemMapping | None:
    if item.woo_product_type == "variation" and (item.woo_product_id is None or item.woo_variation_id is None):
        raise ValueError("woo_variation_mapping_incomplete: variation requires parent Product ID and Variation ID.")
    if item.woo_variation_id is not None and item.woo_product_id is None:
        raise ValueError("woo_variation_mapping_incomplete: variation requires parent Product ID and Variation ID.")
    if item.woo_product_id is None:
        raise ValueError("woo_mapping_missing: item has no Woo Product ID.")
    if item.woo_variation_id is None and item.woo_product_type == "variable":
        raise ValueError("woo_mapping_conflict: variable parent containers cannot receive stock writeback.")
    if not item.active:
        raise ValueError("woo_mapping_missing: item mapping is inactive.")

    item_mappings = list(db.scalars(select(WooItemMapping).where(WooItemMapping.item_id == item.id, WooItemMapping.active.is_(True))).all())
    exact = [mapping for mapping in item_mappings if (mapping.woo_product_id, mapping.woo_variation_id) == (item.woo_product_id, item.woo_variation_id)]
    if item_mappings and (len(item_mappings) != 1 or len(exact) != 1):
        raise ValueError("woo_mapping_conflict: item has ambiguous active mappings.")

    remote_mappings = list(db.scalars(select(WooItemMapping).where(
        WooItemMapping.woo_product_id == item.woo_product_id,
        WooItemMapping.woo_variation_id.is_(None) if item.woo_variation_id is None else WooItemMapping.woo_variation_id == item.woo_variation_id,
        WooItemMapping.active.is_(True),
    )).all())
    if remote_mappings and (len(remote_mappings) != 1 or remote_mappings[0].item_id != item.id):
        raise ValueError("woo_mapping_conflict: Woo target is assigned to another or multiple active local items.")
    field_matches = list(db.scalars(select(InventoryItem).where(
        InventoryItem.woo_product_id == item.woo_product_id,
        InventoryItem.woo_variation_id.is_(None) if item.woo_variation_id is None else InventoryItem.woo_variation_id == item.woo_variation_id,
    )).all())
    if len(field_matches) != 1 or field_matches[0].id != item.id:
        raise ValueError("woo_mapping_conflict: Woo identity fields are duplicated locally.")
    if item.in_stock is None:
        raise ValueError("woo_mapping_conflict: local absolute stock quantity is unavailable.")
    return exact[0] if exact else None


def validate_queue_mapping(db: Session, row: WooWritebackQueue) -> None:
    if row.operation_type not in {"update_product_stock", "update_variation_stock"}:
        return
    item = db.get(InventoryItem, row.entity_id)
    if item is None:
        raise ValueError("woo_mapping_missing: local item no longer exists.")
    validate_item_mapping(db, item)
    expected_operation = "update_variation_stock" if item.woo_variation_id is not None else "update_product_stock"
    expected_path = product_stock_path(item)
    actual_path = str((row.payload_json or {}).get("path") or "")
    if row.operation_type != expected_operation or row.woo_product_id != item.woo_product_id or row.woo_variation_id != item.woo_variation_id or actual_path != expected_path:
        raise ValueError("woo_writeback_target_stale: queue target does not agree with the current mapping; revalidate it before approval.")


def revalidate_queue_item(db: Session, client: WooCommerceClient, settings: Settings, queue_id: int) -> WooWritebackQueue | None:
    row = db.get(WooWritebackQueue, queue_id)
    if row is None:
        return None
    if row.status not in {"pending", "failed"}:
        raise ValueError("Only pending or failed writebacks can be revalidated; successful history is immutable.")
    if row.operation_type not in {"update_product_stock", "update_variation_stock"}:
        raise ValueError("Only stock writebacks can be mapping-revalidated.")
    preview = preview_stock_writeback(db, settings, client, WooWritebackStockPreviewRequest(item_id=row.entity_id, fetch_live=False))
    if preview is None:
        raise ValueError("woo_mapping_missing: local item no longer exists.")
    row.operation_type = preview.operation_type
    row.woo_entity_id = preview.woo_entity_id
    row.woo_product_id = preview.woo_product_id
    row.woo_variation_id = preview.woo_variation_id
    row.payload_json = preview.payload_json
    row.preview_json = preview.preview_json
    row.environment = settings.woocommerce_environment
    row.dry_run = settings.woocommerce_writeback_dry_run
    row.allowed_host = settings.woocommerce_allowed_host or None
    row.status = "pending"
    row.error_message = None
    row.approved_by = None
    row.approved_at = None
    row.response_json = None
    db.commit()
    db.refresh(row)
    return row


def find_item(db: Session, item_id: int | None = None, sku: str | None = None) -> InventoryItem | None:
    if item_id:
        return db.get(InventoryItem, item_id)
    if sku:
        matches = list(db.scalars(select(InventoryItem).where(InventoryItem.sku == sku).order_by(InventoryItem.id).limit(2)).all())
        if len(matches) > 1:
            raise ValueError(f"duplicate_sku_conflict: multiple local items use SKU {sku!r}; writeback was blocked.")
        return matches[0] if matches else None
    return None


def find_order(db: Session, order_id: int | None = None, woo_order_id: int | None = None) -> Order | None:
    if order_id:
        return db.get(Order, order_id)
    if woo_order_id:
        return db.scalars(select(Order).where(Order.woo_order_id == woo_order_id)).first()
    return None


def product_stock_path(item: InventoryItem) -> str:
    if item.woo_product_id and item.woo_variation_id:
        return f"/wp-json/wc/v3/products/{item.woo_product_id}/variations/{item.woo_variation_id}"
    return f"/wp-json/wc/v3/products/{item.woo_product_id or 0}"


def queue_to_read(row: WooWritebackQueue) -> WooWritebackQueueRead:
    return WooWritebackQueueRead(
        id=row.id,
        operation_type=row.operation_type,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        woo_entity_id=row.woo_entity_id,
        woo_product_id=row.woo_product_id,
        woo_variation_id=row.woo_variation_id,
        woo_order_id=row.woo_order_id,
        payload_json=row.payload_json,
        status=row.status,
        environment=row.environment,
        dry_run=row.dry_run,
        allowed_host=row.allowed_host,
        preview_json=row.preview_json,
        response_json=row.response_json,
        error_message=row.error_message,
        requested_by=row.requested_by,
        approved_by=row.approved_by,
        created_at=row.created_at,
        approved_at=row.approved_at,
        sent_at=row.sent_at,
        updated_at=row.updated_at,
    )


def decimal_to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def apply_successful_snapshot_update(db: Session, row: WooWritebackQueue, response: dict[str, Any]) -> None:
    if row.operation_type in {"update_product_stock", "update_variation_stock"}:
        item = db.get(InventoryItem, row.entity_id)
        if item:
            body = row.payload_json.get("body") or {}
            if "stock_quantity" in response:
                item.woo_stock_quantity_snapshot = Decimal(str(response["stock_quantity"]))
            elif "stock_quantity" in body:
                item.woo_stock_quantity_snapshot = Decimal(str(body["stock_quantity"]))
            if response.get("stock_status") or body.get("stock_status"):
                item.woo_stock_status = response.get("stock_status") or body.get("stock_status")
            item.woo_sync_status = "writeback_sent"
            item.woo_last_synced_at = datetime.now(timezone.utc)
    if row.operation_type == "update_order_status":
        order = db.get(Order, row.entity_id)
        if order:
            next_status = response.get("status") or (row.payload_json.get("body") or {}).get("status")
            order.woo_status = next_status
            order.status = next_status
            order.sync_status = "writeback_sent"
            order.last_synced_at = datetime.now(timezone.utc)
