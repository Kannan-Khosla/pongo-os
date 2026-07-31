from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryAuditEvent, InventoryItem
from app.models.orders import OrderItem
from app.models.woocommerce import WooCommerceSyncError, WooItemMapping
from app.services.order_workflow import auto_allocate_processing_orders_fifo
from app.schemas.woocommerce import (
    WooRemapCandidate,
    WooRemapCandidateListResponse,
    WooRemapCommitRequest,
    WooRemapCommitResponse,
    WooRemapItemSummary,
    WooRemapMappingListResponse,
    WooRemapMappingRead,
    WooRemapPreviewRequest,
    WooRemapPreviewResponse,
    WooRemapRemoteSummary,
)

SAFE_MESSAGE = "This only changes local mapping metadata. It will not change WooCommerce or inventory quantities."


def list_remap_candidates(db: Session, search: str | None = None, limit: int = 100) -> WooRemapCandidateListResponse:
    limit = max(1, min(limit, 250))
    remotes = remote_rows_from_items(db) + remote_rows_from_sync_errors(db)
    seen: set[tuple[int, int | None]] = set()
    candidates: list[WooRemapCandidate] = []
    for remote in remotes:
        key = (remote.woo_product_id, remote.woo_variation_id)
        if key in seen:
            continue
        seen.add(key)
        if search and search.casefold() not in " ".join(str(v or "") for v in [remote.woo_product_id, remote.woo_variation_id, remote.woo_sku, remote.woo_name]).casefold():
            continue
        mapping = active_mapping_for_remote(db, remote.woo_product_id, remote.woo_variation_id)
        candidates.append(WooRemapCandidate(remote=remote, current_mapping=mapping_to_read(mapping) if mapping else None, suggested_items=suggest_items(db, remote)))
        if len(candidates) >= limit:
            break
    return WooRemapCandidateListResponse(candidates=candidates, total=len(candidates))


def preview_remap(db: Session, payload: WooRemapPreviewRequest) -> WooRemapPreviewResponse | None:
    item = db.get(InventoryItem, payload.item_id)
    if item is None:
        return None
    remote = remote_summary(db, payload.woo_product_id, payload.woo_variation_id)
    current = active_mapping_for_remote(db, payload.woo_product_id, payload.woo_variation_id)
    warnings: list[str] = []
    errors: list[str] = []
    if current and current.item_id != item.id:
        errors.append("Woo record is already mapped to a different local item.")
    if item.woo_product_id and (item.woo_product_id != payload.woo_product_id or item.woo_variation_id != payload.woo_variation_id):
        errors.append("Selected local item already has a different Woo identity.")
    active_item_mappings = list(db.scalars(select(WooItemMapping).where(WooItemMapping.item_id == item.id, WooItemMapping.active.is_(True))).all())
    if any((mapping.woo_product_id, mapping.woo_variation_id) != (payload.woo_product_id, payload.woo_variation_id) for mapping in active_item_mappings):
        errors.append("Selected local item already has a different active mapping.")
    remote_items = list(db.scalars(select(InventoryItem).where(
        InventoryItem.woo_product_id == payload.woo_product_id,
        InventoryItem.woo_variation_id.is_(None) if payload.woo_variation_id is None else InventoryItem.woo_variation_id == payload.woo_variation_id,
    )).all())
    if any(remote_item.id != item.id for remote_item in remote_items):
        errors.append("Woo identity fields are already assigned to another local item.")
    if not item.active:
        errors.append("Inactive local items cannot be remapped automatically.")
    if payload.woo_variation_id is None and any(remote_item.woo_product_type == "variable" for remote_item in remote_items):
        errors.append("Variable parent containers cannot be mapped as stock-tracked simple items.")
    if payload.woo_variation_id is not None and payload.woo_product_id <= 0:
        errors.append("A variation requires a valid parent Woo Product ID.")
    if remote.woo_sku:
        sku_matches = list(db.scalars(select(InventoryItem).where(InventoryItem.sku == remote.woo_sku)).all())
        if len(sku_matches) > 1:
            errors.append("Duplicate local SKU requires manual cleanup before remapping.")
        elif sku_matches and sku_matches[0].id != item.id:
            warnings.append("Remote SKU belongs to a different local item; confirm the selected exception carefully.")
    return WooRemapPreviewResponse(
        remote=remote,
        item=item_to_summary(item),
        current_mapping=mapping_to_read(current) if current else None,
        proposed_mapping={"item_id": item.id, "woo_product_id": payload.woo_product_id, "woo_variation_id": payload.woo_variation_id, "mapping_source": "remap"},
        warnings=warnings,
        errors=errors,
        safe_message=SAFE_MESSAGE,
    )


def commit_remap(db: Session, payload: WooRemapCommitRequest) -> WooRemapCommitResponse | None:
    preview = preview_remap(db, payload)
    if preview is None:
        return None
    if preview.errors:
        raise ValueError(" ".join(preview.errors))
    item = db.get(InventoryItem, payload.item_id)
    assert item is not None
    current_mappings = list(db.scalars(select(WooItemMapping).where(WooItemMapping.woo_product_id == payload.woo_product_id, WooItemMapping.woo_variation_id.is_(None) if payload.woo_variation_id is None else WooItemMapping.woo_variation_id == payload.woo_variation_id, WooItemMapping.active.is_(True))).all())
    mapping = current_mappings[0] if current_mappings else WooItemMapping(item_id=item.id, woo_product_id=payload.woo_product_id, woo_variation_id=payload.woo_variation_id, mapping_source="remap", confidence=100, active=True)
    mapping.woo_sku = preview.remote.woo_sku or item.sku
    mapping.woo_name = preview.remote.woo_name or item.description
    mapping.mapping_source = "remap"
    mapping.note = payload.note
    item.woo_product_id = payload.woo_product_id
    item.woo_variation_id = payload.woo_variation_id
    item.woo_sync_status = "manually_mapped"
    item.woo_sync_error = None
    db.add(mapping)
    db.add(InventoryAuditEvent(
        item_id=item.id,
        sku=item.sku,
        barcode=item.barcode,
        event_type="woocommerce_remap",
        quantity_delta=0,
        previous_in_stock=item.in_stock or 0,
        new_in_stock=item.in_stock or 0,
        previous_allocated=item.allocated or 0,
        new_allocated=item.allocated or 0,
        previous_sellable=item.sellable or 0,
        new_sellable=item.sellable or 0,
        warehouse=item.warehouse,
        inventory_location=item.inventory_location,
        reference_type="woo_item_mapping",
        notes=payload.note or "WooCommerce mapping exception committed after preview.",
        created_by="woocommerce-remap",
    ))
    affected_lines = list(db.scalars(select(OrderItem).where(
        OrderItem.woo_product_id == payload.woo_product_id,
        OrderItem.woo_variation_id.is_(None) if payload.woo_variation_id is None else OrderItem.woo_variation_id == payload.woo_variation_id,
        OrderItem.matched_status.in_(["unmatched", "conflict", "unknown"]),
    )).all())
    for line in affected_lines:
        line.inventory_item_id = item.id
        line.matched_status = "matched"
        line.sync_status = "remapped"
        line.sync_error = None
    db.flush()
    allocation_summary = auto_allocate_processing_orders_fifo(db, source="woocommerce-remap", commit=False) if affected_lines else {}
    db.commit()
    db.refresh(mapping)
    return WooRemapCommitResponse(status="mapped", mapping=mapping_to_read(mapping), warnings=preview.warnings, safe_message=SAFE_MESSAGE, reprocessed_order_lines=len(affected_lines), allocation_summary=allocation_summary)


def list_mappings(db: Session, sku: str | None = None, item_id: int | None = None, woo_product_id: int | None = None, mapping_source: str | None = None, active: bool | None = True) -> WooRemapMappingListResponse:
    statement = select(WooItemMapping).order_by(WooItemMapping.updated_at.desc(), WooItemMapping.id.desc())
    if item_id is not None:
        statement = statement.where(WooItemMapping.item_id == item_id)
    if woo_product_id is not None:
        statement = statement.where(WooItemMapping.woo_product_id == woo_product_id)
    if mapping_source:
        statement = statement.where(WooItemMapping.mapping_source == mapping_source)
    if active is not None:
        statement = statement.where(WooItemMapping.active.is_(active))
    rows = list(db.scalars(statement).all())
    if sku:
        rows = [row for row in rows if sku.casefold() in (row.woo_sku or "").casefold()]
    return WooRemapMappingListResponse(mappings=[mapping_to_read(row) for row in rows], total=len(rows))


def deactivate_mapping(db: Session, mapping_id: int, note: str | None = None) -> WooItemMapping | None:
    mapping = db.get(WooItemMapping, mapping_id)
    if mapping is None:
        return None
    mapping.active = False
    if note:
        mapping.note = note
    db.commit()
    db.refresh(mapping)
    return mapping


def remote_rows_from_items(db: Session) -> list[WooRemapRemoteSummary]:
    rows = list(db.scalars(select(InventoryItem).where(InventoryItem.woo_product_id.is_not(None)).order_by(InventoryItem.woo_last_synced_at.desc().nullslast(), InventoryItem.id.desc())).all())
    return [
        remote_from_item(item, "mapped" if item.woo_sync_status != "error" else "manual_review")
        for item in rows
        if item.woo_product_id is not None
    ]


def remote_rows_from_sync_errors(db: Session) -> list[WooRemapRemoteSummary]:
    errors = list(db.scalars(select(WooCommerceSyncError).where(WooCommerceSyncError.remote_product_id.is_not(None)).order_by(WooCommerceSyncError.created_at.desc()).limit(200)).all())
    return [
        WooRemapRemoteSummary(woo_product_id=error.remote_product_id, woo_variation_id=error.remote_variation_id, woo_sku=error.sku, woo_name=error.error_message, reason="manual_review")
        for error in errors
        if error.remote_product_id is not None
    ]


def remote_summary(db: Session, woo_product_id: int, woo_variation_id: int | None) -> WooRemapRemoteSummary:
    item = db.scalars(select(InventoryItem).where(InventoryItem.woo_product_id == woo_product_id, InventoryItem.woo_variation_id.is_(None) if woo_variation_id is None else InventoryItem.woo_variation_id == woo_variation_id)).first()
    if item:
        return remote_from_item(item, "mapped")
    error = db.scalars(select(WooCommerceSyncError).where(WooCommerceSyncError.remote_product_id == woo_product_id, WooCommerceSyncError.remote_variation_id.is_(None) if woo_variation_id is None else WooCommerceSyncError.remote_variation_id == woo_variation_id).order_by(WooCommerceSyncError.created_at.desc())).first()
    return WooRemapRemoteSummary(woo_product_id=woo_product_id, woo_variation_id=woo_variation_id, woo_sku=error.sku if error else None, woo_name=error.error_message if error else None, reason="manual_review")


def active_mapping_for_remote(db: Session, woo_product_id: int, woo_variation_id: int | None) -> WooItemMapping | None:
    return db.scalars(select(WooItemMapping).where(WooItemMapping.woo_product_id == woo_product_id, WooItemMapping.woo_variation_id.is_(None) if woo_variation_id is None else WooItemMapping.woo_variation_id == woo_variation_id, WooItemMapping.active.is_(True))).first()


def suggest_items(db: Session, remote: WooRemapRemoteSummary) -> list[WooRemapItemSummary]:
    statement = select(InventoryItem).limit(20)
    clauses = []
    if remote.woo_sku:
        clauses.append(InventoryItem.sku == remote.woo_sku)
        clauses.append(InventoryItem.barcode == remote.woo_sku)
    if remote.woo_name:
        clauses.append(InventoryItem.description.ilike(f"%{remote.woo_name[:80]}%"))
    if clauses:
        statement = select(InventoryItem).where(or_(*clauses)).limit(10)
    return [item_to_summary(item) for item in db.scalars(statement).all()]


def item_to_summary(item: InventoryItem) -> WooRemapItemSummary:
    return WooRemapItemSummary(item_id=item.id, sku=item.sku, barcode=item.barcode, description=item.description, brand=item.brand, category=item.category, woo_product_id=item.woo_product_id, woo_variation_id=item.woo_variation_id)


def mapping_to_read(mapping: WooItemMapping) -> WooRemapMappingRead:
    return WooRemapMappingRead(
        id=mapping.id,
        item_id=mapping.item_id,
        woo_product_id=mapping.woo_product_id,
        woo_variation_id=mapping.woo_variation_id,
        woo_sku=mapping.woo_sku,
        woo_name=mapping.woo_name,
        mapping_source=mapping.mapping_source,
        confidence=float(mapping.confidence) if mapping.confidence is not None else None,
        active=mapping.active,
        note=mapping.note,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


def remote_from_item(item: InventoryItem, reason: str) -> WooRemapRemoteSummary:
    return WooRemapRemoteSummary(
        woo_product_id=item.woo_product_id,
        woo_variation_id=item.woo_variation_id,
        woo_sku=item.sku,
        woo_name=item.woo_name or item.description,
        parent_product_name=item.woo_parent_name,
        variation_attributes=item.woo_variation_attributes or [],
        woo_stock_snapshot=float(item.woo_stock_quantity_snapshot) if item.woo_stock_quantity_snapshot is not None else None,
        mapping_status=item.woo_sync_status,
        reason=reason,
    )
