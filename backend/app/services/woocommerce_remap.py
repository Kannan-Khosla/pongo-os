from __future__ import annotations

from sqlalchemy import String, and_, cast, exists, func, literal, or_, select, tuple_, union_all
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


def list_remap_candidates(
    db: Session,
    search: str | None = None,
    *,
    page: int = 1,
    page_size: int = 100,
) -> WooRemapCandidateListResponse:
    ranked_items = (
        select(
            InventoryItem.id.label("item_id"),
            func.row_number()
            .over(
                partition_by=(InventoryItem.woo_product_id, InventoryItem.woo_variation_id),
                order_by=(InventoryItem.woo_last_synced_at.desc().nullslast(), InventoryItem.id.desc()),
            )
            .label("remote_rank"),
        )
        .where(InventoryItem.woo_product_id.is_not(None))
        .subquery()
    )
    selected_item_ids = select(ranked_items.c.item_id).where(ranked_items.c.remote_rank == 1).subquery()
    item_predicates = []
    if search:
        search_text = (
            cast(InventoryItem.woo_product_id, String)
            + " "
            + func.coalesce(cast(InventoryItem.woo_variation_id, String), "")
            + " "
            + func.coalesce(InventoryItem.sku, "")
            + " "
            + func.coalesce(InventoryItem.woo_name, InventoryItem.description, "")
        )
        item_predicates.append(func.lower(search_text).contains(search.casefold(), autoescape=True))

    item_total = int(
        db.scalar(
            select(func.count(InventoryItem.id))
            .join(selected_item_ids, selected_item_ids.c.item_id == InventoryItem.id)
            .where(*item_predicates)
        )
        or 0
    )
    latest_errors = latest_error_candidates_query()
    error_predicates = error_candidate_predicates(latest_errors, search=search)
    error_total = int(
        db.scalar(
            select(func.count())
            .select_from(latest_errors)
            .where(*error_predicates)
        )
        or 0
    )
    total = item_total + error_total
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    offset = (effective_page - 1) * page_size

    item_rows: list[InventoryItem] = []
    if offset < item_total:
        item_rows = list(
            db.scalars(
                select(InventoryItem)
                .join(selected_item_ids, selected_item_ids.c.item_id == InventoryItem.id)
                .where(*item_predicates)
                .order_by(InventoryItem.woo_last_synced_at.desc().nullslast(), InventoryItem.id.desc())
                .offset(offset)
                .limit(page_size)
            ).all()
        )
    remotes: list[WooRemapRemoteSummary] = [
        remote_from_item(item, "mapped" if item.woo_sync_status != "error" else "manual_review")
        for item in item_rows
    ]
    remaining = page_size - len(remotes)
    if remaining > 0:
        error_offset = max(0, offset - item_total)
        error_rows = db.execute(
            select(
                latest_errors.c.remote_product_id,
                latest_errors.c.remote_variation_id,
                latest_errors.c.sku,
                latest_errors.c.error_message,
            )
            .where(*error_predicates)
            .order_by(latest_errors.c.created_at.desc(), latest_errors.c.id.desc())
            .offset(error_offset)
            .limit(remaining)
        ).all()
        remotes.extend(
            WooRemapRemoteSummary(
                woo_product_id=int(row.remote_product_id),
                woo_variation_id=(
                    int(row.remote_variation_id)
                    if row.remote_variation_id is not None
                    else None
                ),
                woo_sku=row.sku,
                woo_name=row.error_message,
                reason="manual_review",
            )
            for row in error_rows
        )

    mappings = active_mappings_for_remotes(db, remotes)
    suggestions = suggest_items_for_remotes(db, remotes)
    candidates = []
    for remote in remotes:
        key = remote_key(remote.woo_product_id, remote.woo_variation_id)
        mapping = mappings.get(key)
        candidates.append(
            WooRemapCandidate(
                remote=remote,
                current_mapping=mapping_to_read(mapping) if mapping else None,
                suggested_items=suggestions.get(key, []),
            )
        )
    return WooRemapCandidateListResponse(
        candidates=candidates,
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(candidates),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


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


def list_mappings(
    db: Session,
    sku: str | None = None,
    item_id: int | None = None,
    woo_product_id: int | None = None,
    mapping_source: str | None = None,
    active: bool | None = True,
    *,
    page: int = 1,
    page_size: int = 100,
) -> WooRemapMappingListResponse:
    predicates = []
    if item_id is not None:
        predicates.append(WooItemMapping.item_id == item_id)
    if woo_product_id is not None:
        predicates.append(WooItemMapping.woo_product_id == woo_product_id)
    if mapping_source:
        predicates.append(WooItemMapping.mapping_source == mapping_source)
    if active is not None:
        predicates.append(WooItemMapping.active.is_(active))
    if sku:
        predicates.append(func.lower(func.coalesce(WooItemMapping.woo_sku, "")).contains(sku.casefold(), autoescape=True))
    total = int(db.scalar(select(func.count(WooItemMapping.id)).where(*predicates)) or 0)
    total_pages = (total + page_size - 1) // page_size if total else 0
    effective_page = min(page, max(total_pages, 1))
    rows = list(
        db.scalars(
            select(WooItemMapping)
            .where(*predicates)
            .order_by(WooItemMapping.updated_at.desc(), WooItemMapping.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return WooRemapMappingListResponse(
        mappings=[mapping_to_read(row) for row in rows],
        total=total,
        page=effective_page,
        page_size=page_size,
        total_pages=total_pages,
        returned_count=len(rows),
        has_previous=effective_page > 1,
        has_next=effective_page < total_pages,
    )


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


def latest_error_candidates_query():
    """Return one latest sync-error row for each Woo product/variation identity."""
    ranked_errors = (
        select(
            WooCommerceSyncError.id.label("id"),
            WooCommerceSyncError.remote_product_id.label("remote_product_id"),
            WooCommerceSyncError.remote_variation_id.label("remote_variation_id"),
            WooCommerceSyncError.sku.label("sku"),
            WooCommerceSyncError.error_message.label("error_message"),
            WooCommerceSyncError.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(
                    WooCommerceSyncError.remote_product_id,
                    func.coalesce(WooCommerceSyncError.remote_variation_id, -1),
                ),
                order_by=(
                    WooCommerceSyncError.created_at.desc(),
                    WooCommerceSyncError.id.desc(),
                ),
            )
            .label("remote_rank"),
        )
        .where(WooCommerceSyncError.remote_product_id.is_not(None))
        .subquery("ranked_woo_sync_errors")
    )
    return (
        select(
            ranked_errors.c.id,
            ranked_errors.c.remote_product_id,
            ranked_errors.c.remote_variation_id,
            ranked_errors.c.sku,
            ranked_errors.c.error_message,
            ranked_errors.c.created_at,
        )
        .where(ranked_errors.c.remote_rank == 1)
        .subquery("latest_woo_sync_errors")
    )


def error_candidate_predicates(latest_errors, search: str | None = None) -> list:
    predicates = [
        ~exists(
            select(1).where(
                InventoryItem.woo_product_id == latest_errors.c.remote_product_id,
                func.coalesce(InventoryItem.woo_variation_id, -1)
                == func.coalesce(latest_errors.c.remote_variation_id, -1),
            )
        )
    ]
    if search:
        search_text = (
            cast(latest_errors.c.remote_product_id, String)
            + " "
            + func.coalesce(cast(latest_errors.c.remote_variation_id, String), "")
            + " "
            + func.coalesce(latest_errors.c.sku, "")
            + " "
            + func.coalesce(latest_errors.c.error_message, "")
        )
        predicates.append(func.lower(search_text).contains(search.casefold(), autoescape=True))
    return predicates


def remote_key(woo_product_id: int, woo_variation_id: int | None) -> tuple[int, int]:
    return (int(woo_product_id), int(woo_variation_id) if woo_variation_id is not None else -1)


def active_mappings_for_remotes(
    db: Session,
    remotes: list[WooRemapRemoteSummary],
) -> dict[tuple[int, int], WooItemMapping]:
    keys = sorted({remote_key(remote.woo_product_id, remote.woo_variation_id) for remote in remotes})
    if not keys:
        return {}
    mappings: dict[tuple[int, int], WooItemMapping] = {}
    rows = db.scalars(
        select(WooItemMapping)
        .where(
            WooItemMapping.active.is_(True),
            tuple_(
                WooItemMapping.woo_product_id,
                func.coalesce(WooItemMapping.woo_variation_id, -1),
            ).in_(keys),
        )
        .order_by(WooItemMapping.id)
    ).all()
    for mapping in rows:
        mappings.setdefault(remote_key(mapping.woo_product_id, mapping.woo_variation_id), mapping)
    return mappings


def suggest_items_for_remotes(
    db: Session,
    remotes: list[WooRemapRemoteSummary],
) -> dict[tuple[int, int], list[WooRemapItemSummary]]:
    """Return at most ten suggestions per candidate with a fixed query count."""
    if not remotes:
        return {}
    suggestions: dict[tuple[int, int], list[WooRemapItemSummary]] = {
        remote_key(remote.woo_product_id, remote.woo_variation_id): []
        for remote in remotes
    }
    searchable = [
        (index, remote)
        for index, remote in enumerate(remotes)
        if remote.woo_sku or remote.woo_name
    ]
    fallback_items: list[InventoryItem] = []
    if any(not remote.woo_sku and not remote.woo_name for remote in remotes):
        fallback_items = list(
            db.scalars(
                select(InventoryItem).order_by(InventoryItem.id).limit(20)
            ).all()
        )
    for remote in remotes:
        key = remote_key(remote.woo_product_id, remote.woo_variation_id)
        if not remote.woo_sku and not remote.woo_name:
            suggestions[key] = [item_to_summary(item) for item in fallback_items]
    if not searchable:
        return suggestions

    candidate_selects = [
        select(
            literal(index).label("candidate_index"),
            cast(literal(remote.woo_sku), String).label("woo_sku"),
            cast(
                literal(remote.woo_name[:80].casefold() if remote.woo_name else None),
                String,
            ).label("woo_name"),
        )
        for index, remote in searchable
    ]
    candidate_rows = union_all(*candidate_selects).cte("remap_suggestion_candidates")
    match_clause = or_(
        and_(
            candidate_rows.c.woo_sku.is_not(None),
            or_(
                InventoryItem.sku == candidate_rows.c.woo_sku,
                InventoryItem.barcode == candidate_rows.c.woo_sku,
            ),
        ),
        and_(
            candidate_rows.c.woo_name.is_not(None),
            func.lower(func.coalesce(InventoryItem.description, "")).like(
                literal("%") + candidate_rows.c.woo_name + literal("%")
            ),
        ),
    )
    ranked_matches = (
        select(
            candidate_rows.c.candidate_index,
            InventoryItem.id.label("item_id"),
            func.row_number()
            .over(
                partition_by=candidate_rows.c.candidate_index,
                order_by=InventoryItem.id,
            )
            .label("suggestion_rank"),
        )
        .select_from(candidate_rows.join(InventoryItem, match_clause))
        .subquery("ranked_remap_suggestions")
    )
    match_rows = db.execute(
        select(
            ranked_matches.c.candidate_index,
            ranked_matches.c.item_id,
            ranked_matches.c.suggestion_rank,
        )
        .where(ranked_matches.c.suggestion_rank <= 10)
        .order_by(ranked_matches.c.candidate_index, ranked_matches.c.suggestion_rank)
    ).all()
    item_ids = sorted({int(row.item_id) for row in match_rows})
    items_by_id = {
        item.id: item
        for item in db.scalars(
            select(InventoryItem).where(InventoryItem.id.in_(item_ids))
        ).all()
    } if item_ids else {}
    remote_keys_by_index = {
        index: remote_key(remote.woo_product_id, remote.woo_variation_id)
        for index, remote in searchable
    }
    for row in match_rows:
        item = items_by_id.get(int(row.item_id))
        if item is not None:
            suggestions[remote_keys_by_index[int(row.candidate_index)]].append(item_to_summary(item))
    return suggestions


def remote_summary(db: Session, woo_product_id: int, woo_variation_id: int | None) -> WooRemapRemoteSummary:
    item = db.scalars(select(InventoryItem).where(InventoryItem.woo_product_id == woo_product_id, InventoryItem.woo_variation_id.is_(None) if woo_variation_id is None else InventoryItem.woo_variation_id == woo_variation_id)).first()
    if item:
        return remote_from_item(item, "mapped")
    error = db.scalars(select(WooCommerceSyncError).where(WooCommerceSyncError.remote_product_id == woo_product_id, WooCommerceSyncError.remote_variation_id.is_(None) if woo_variation_id is None else WooCommerceSyncError.remote_variation_id == woo_variation_id).order_by(WooCommerceSyncError.created_at.desc()).limit(1)).first()
    return WooRemapRemoteSummary(woo_product_id=woo_product_id, woo_variation_id=woo_variation_id, woo_sku=error.sku if error else None, woo_name=error.error_message if error else None, reason="manual_review")


def active_mapping_for_remote(db: Session, woo_product_id: int, woo_variation_id: int | None) -> WooItemMapping | None:
    return db.scalars(select(WooItemMapping).where(WooItemMapping.woo_product_id == woo_product_id, WooItemMapping.woo_variation_id.is_(None) if woo_variation_id is None else WooItemMapping.woo_variation_id == woo_variation_id, WooItemMapping.active.is_(True))).first()


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
