import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.inventory import InventoryItem
from app.models.woocommerce import WooCommerceSyncRun, WooItemMapping
from app.services.woocommerce_sync_errors import prune_sync_errors, store_sync_error_once
from app.schemas.woocommerce import WooCommerceNewProductImportResponse, WooCommerceProductPreviewResponse, WooCommerceProductPreviewRow, WooCommerceSyncRequest
from app.services.items import apply_calculated_fields
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError


NEW_PRODUCT_SYNC_TYPE = "new_products"
WOO_METADATA_FIELDS = {"sku", "barcode", "description", "recommended_retail_price", "sales_price"}


def sync_item_metadata_to_woo(db: Session, item: InventoryItem, changed_fields: set[str]) -> None:
    if item.woo_product_id is None or not changed_fields.intersection(WOO_METADATA_FIELDS):
        return
    payload = {}
    if "sku" in changed_fields:
        payload["sku"] = item.sku or ""
    if "barcode" in changed_fields:
        payload["global_unique_id"] = item.barcode or ""
    if "description" in changed_fields:
        payload["description"] = item.description or ""
    if "recommended_retail_price" in changed_fields:
        payload["regular_price"] = str(item.recommended_retail_price) if item.recommended_retail_price is not None else ""
    if "sales_price" in changed_fields:
        payload["sale_price"] = str(item.sales_price) if item.sales_price is not None else ""
    settings = effective_woocommerce_settings(db, get_settings())
    if not settings.woocommerce_allow_product_metadata_write:
        return
    client = WooCommerceClient(settings)
    variation = item.woo_variation_id is not None
    operation = "update_variation_metadata" if variation else "update_product_metadata"
    path = f"/wp-json/wc/v3/products/{item.woo_product_id}"
    if variation:
        path += f"/variations/{item.woo_variation_id}"
    try:
        client.guarded_write(operation, "PATCH", path, payload)
        item.woo_sync_status = "synced"
        item.woo_sync_error = None
    except WooCommerceClientError as error:
        item.woo_sync_status = "pending_writeback"
        item.woo_sync_error = error.message
    db.add(item)
    db.commit()
    db.refresh(item)


def import_new_products(db: Session, client: WooCommerceClient, created_by: str) -> WooCommerceNewProductImportResponse:
    if not client.configured:
        raise WooCommerceClientError("WooCommerce credentials are not configured.")

    started_at = datetime.now(timezone.utc)
    previous = db.scalars(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.sync_type == NEW_PRODUCT_SYNC_TYPE, WooCommerceSyncRun.status == "completed")
        .order_by(WooCommerceSyncRun.completed_at.desc(), WooCommerceSyncRun.id.desc())
    ).first()
    cursor_value = (previous.progress or {}).get("cursor_at") if previous else None
    cursor = datetime.fromisoformat(cursor_value.replace("Z", "+00:00")) if cursor_value else None
    checked_since = cursor - timedelta(minutes=5) if cursor else None

    known_product_ids = set(db.scalars(select(InventoryItem.woo_product_id).where(InventoryItem.woo_product_id.is_not(None), InventoryItem.woo_variation_id.is_(None))).all())
    known_variation_ids = set(db.scalars(select(InventoryItem.woo_variation_id).where(InventoryItem.woo_variation_id.is_not(None))).all())
    active_mappings = list(db.scalars(select(WooItemMapping).where(WooItemMapping.active.is_(True))).all())
    known_product_ids.update(mapping.woo_product_id for mapping in active_mappings if mapping.woo_variation_id is None)
    known_variation_ids.update(mapping.woo_variation_id for mapping in active_mappings if mapping.woo_variation_id is not None)

    remote_records: list[dict[str, Any]] = []
    page = 1
    while True:
        products = client.list_products(
            page=page,
            per_page=100,
            statuses=["any"],
            modified_after=checked_since.isoformat().replace("+00:00", "Z") if checked_since else None,
        )
        for product in products:
            product_id = int(product["id"])
            product_type = product.get("type")
            if product_type == "simple" and product_id not in known_product_ids:
                remote_records.append({"product": product, "variation": None})
            elif product_type == "variable":
                for variation_id in product.get("variations") or []:
                    variation_id = int(variation_id)
                    if variation_id not in known_variation_ids:
                        remote_records.append({"product": product, "variation": client.get_product_variation(product_id, variation_id)})
        if len(products) < 100:
            break
        page += 1

    rows = build_preview_rows(db, remote_records, allow_missing_sku=True)
    sync_run = WooCommerceSyncRun(
        sync_type=NEW_PRODUCT_SYNC_TYPE,
        status="running",
        started_at=started_at,
        created_by=created_by,
        total_remote_records=len(rows),
    )
    db.add(sync_run)
    db.flush()
    created_ids: list[int] = []
    setup_ids: list[int] = []
    created_count = linked_count = skipped_count = conflict_count = error_count = 0
    warnings = [warning for row in rows for warning in row.warnings]
    errors = [error for row in rows for error in row.errors]
    synced_at = datetime.now(timezone.utc)

    for row, remote in zip(rows, remote_records):
        if row.action in {"skip", "conflict", "error"}:
            skipped_count += row.action == "skip"
            conflict_count += row.action == "conflict"
            error_count += row.action == "error"
            store_sync_error(db, sync_run.id, row, row.errors or row.warnings)
            continue
        record = normalize_remote_record(remote["product"], remote.get("variation"))
        savepoint = db.begin_nested()
        try:
            if row.action == "create":
                item = create_item_from_woo(record, synced_at)
                db.add(item)
                db.flush()
                created_count += 1
                created_ids.append(item.id)
            else:
                item = db.get(InventoryItem, row.local_item_id)
                if item is None:
                    raise ValueError("Matched local item no longer exists.")
                update_item_from_woo(item, record, synced_at)
                linked_count += 1
            ensure_mapping_record(db, item, record)
            setup_ids.append(item.id)
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            error_count += 1
            errors.append(str(exc))
            store_sync_error(db, sync_run.id, row, [str(exc)])

    sync_run.created_count = created_count
    sync_run.matched_count = linked_count
    sync_run.skipped_count = skipped_count
    sync_run.conflict_count = conflict_count
    sync_run.error_count = error_count
    sync_run.completed_at = datetime.now(timezone.utc)
    sync_run.status = "completed_with_errors" if conflict_count or error_count else "completed"
    sync_run.progress = {"created_item_ids": created_ids}
    if sync_run.status == "completed":
        sync_run.progress["cursor_at"] = started_at.isoformat()
    db.commit()
    db.refresh(sync_run)
    imported_count = created_count + linked_count
    return WooCommerceNewProductImportResponse(
        sync_run_id=sync_run.id,
        status=sync_run.status,
        checked_since=checked_since,
        total_remote_records=len(rows),
        created_count=created_count,
        linked_count=linked_count,
        skipped_count=skipped_count,
        conflict_count=conflict_count,
        error_count=error_count,
        created_item_ids=created_ids,
        setup_item_ids=setup_ids,
        warnings=warnings,
        errors=errors,
        message=(f"Imported {imported_count} new product{'s' if imported_count != 1 else ''}." if imported_count else "No new WooCommerce products found."),
    )


@dataclass
class NormalizedWooRecord:
    remote_type: str
    woo_product_id: int
    woo_variation_id: int | None
    sku: str
    barcode: str
    name: str
    parent_name: str
    variation_attributes: list[dict]
    parent_container: bool
    purchasable: bool
    description: str
    category: str
    brand: str
    regular_price: Decimal | None
    sale_price: Decimal | None
    price: Decimal
    permalink: str
    status: str
    manage_stock: bool | None
    stock_quantity: Decimal | None
    stock_status: str
    weight: Decimal | None
    length: Decimal | None
    width: Decimal | None
    height: Decimal | None
    image_url: str
    raw_payload: dict[str, Any]


def preview_product_sync(db: Session, client: WooCommerceClient, payload: WooCommerceSyncRequest) -> WooCommerceProductPreviewResponse:
    if not client.configured:
        return WooCommerceProductPreviewResponse(
            configured=False,
            total_remote_records=0,
            create_count=0,
            update_count=0,
            matched_count=0,
            skipped_count=0,
            conflict_count=0,
            error_count=0,
            errors=["WooCommerce credentials are not configured."],
        )
    try:
        remote_records, has_more = fetch_product_records(client, payload)
    except WooCommerceClientError as error:
        return WooCommerceProductPreviewResponse(
            configured=True,
            total_remote_records=0,
            create_count=0,
            update_count=0,
            matched_count=0,
            skipped_count=0,
            conflict_count=0,
            error_count=1,
            errors=[error.message],
        )
    rows = build_preview_rows(db, remote_records, payload.blocked_skus)
    return build_preview_response(True, rows, payload.page, has_more)


def commit_product_sync(db: Session, client: WooCommerceClient, payload: WooCommerceSyncRequest) -> tuple[WooCommerceSyncRun | None, WooCommerceProductPreviewResponse]:
    started_at = datetime.now(timezone.utc)
    if not client.configured:
        return None, preview_product_sync(db, client, payload)
    try:
        remote_records, has_more = fetch_product_records(client, payload)
    except WooCommerceClientError as error:
        return None, WooCommerceProductPreviewResponse(
            configured=True,
            total_remote_records=0,
            create_count=0,
            update_count=0,
            matched_count=0,
            skipped_count=0,
            conflict_count=0,
            error_count=1,
            errors=[error.message],
        )
    normalized_records = [normalize_remote_record(remote["product"], remote.get("variation"), parent_container=bool(remote.get("parent_container"))) for remote in remote_records]
    rows = build_preview_rows(db, remote_records, payload.blocked_skus)
    row_records = list(zip(rows, normalized_records))
    preview = build_preview_response(True, rows, payload.page, has_more)
    prune_sync_errors(db)
    sync_run = WooCommerceSyncRun(sync_type="products", status="completed", started_at=started_at, created_by=payload.created_by or "system", total_remote_records=preview.total_remote_records)
    db.add(sync_run)
    db.flush()
    created_count = updated_count = matched_count = skipped_count = conflict_count = error_count = unchanged_count = 0
    now = datetime.now(timezone.utc)

    for row, record in row_records:
        if row.action in {"skip", "conflict", "error"}:
            skipped_count += 1 if row.action == "skip" else 0
            conflict_count += 1 if row.action == "conflict" else 0
            error_count += 1 if row.action == "error" else 0
            store_sync_error(db, sync_run.id, row, row.errors or row.warnings)
            continue
        savepoint = db.begin_nested()
        try:
            if row.action == "create":
                item = create_item_from_woo(record, now)
                db.add(item)
                db.flush()
                ensure_mapping_record(db, item, record)
                created_count += 1
            elif row.local_item_id is not None:
                item = db.get(InventoryItem, row.local_item_id)
                if item is None:
                    error_count += 1
                    store_sync_error(db, sync_run.id, row, ["Matched local item no longer exists."])
                    continue
                update_item_from_woo(item, record, now)
                ensure_mapping_record(db, item, record)
                db.add(item)
                updated_count += 1 if row.action == "update" else 0
                unchanged_count += 1 if row.action == "unchanged" else 0
                matched_count += 1
            savepoint.commit()
        except Exception as exc:
            savepoint.rollback()
            error_count += 1
            store_sync_error(db, sync_run.id, row, [str(exc)])

    sync_run.created_count = created_count
    sync_run.updated_count = updated_count
    sync_run.matched_count = matched_count
    sync_run.skipped_count = skipped_count
    sync_run.conflict_count = conflict_count
    sync_run.error_count = error_count
    sync_run.completed_at = datetime.now(timezone.utc)
    sync_run.status = "completed_with_errors" if conflict_count or error_count else "completed"
    db.commit()
    db.refresh(sync_run)
    unmatched_count, unmatched_skus = unmatched_local_items(db) if not has_more else (0, [])
    response = WooCommerceProductPreviewResponse(
        configured=True,
        total_remote_records=preview.total_remote_records,
        create_count=created_count,
        update_count=updated_count,
        matched_count=matched_count,
        skipped_count=skipped_count,
        conflict_count=conflict_count,
        error_count=error_count,
        warnings=preview.warnings,
        errors=preview.errors,
        preview_rows=[],
        page=payload.page,
        next_page=(payload.page + 1) if payload.page is not None and has_more else None,
        has_more=has_more,
        unmatched_local_count=unmatched_count,
        unmatched_local_skus=unmatched_skus,
        simple_products_examined=preview.simple_products_examined,
        variable_parents_examined=preview.variable_parents_examined,
        purchasable_variations_examined=preview.purchasable_variations_examined,
        new_simple_count=sum(1 for row in rows if row.action == "create" and row.remote_type == "simple"),
        new_variation_count=sum(1 for row in rows if row.action == "create" and row.remote_type == "variation"),
        unchanged_count=unchanged_count,
        skipped_parent_count=preview.skipped_parent_count,
        missing_sku_count=preview.missing_sku_count,
        duplicate_sku_conflict_count=preview.duplicate_sku_conflict_count,
        duplicate_mapping_conflict_count=preview.duplicate_mapping_conflict_count,
        unmapped_count=preview.unmapped_count,
        invalid_count=preview.invalid_count,
    )
    return sync_run, response


def fetch_product_records(client: WooCommerceClient, payload: WooCommerceSyncRequest) -> tuple[list[dict[str, Any]], bool]:
    if payload.page is not None:
        return client.fetch_sellable_product_batch(payload.page, payload.per_page, payload.include_statuses)
    return client.fetch_all_sellable_products_and_variations(payload.include_statuses, payload.limit), False


def build_preview_rows(db: Session, remote_records: list[dict[str, Any]], blocked_skus: list[str] | None = None, *, allow_missing_sku: bool = False) -> list[WooCommerceProductPreviewRow]:
    records = [normalize_remote_record(remote["product"], remote.get("variation"), parent_container=bool(remote.get("parent_container"))) for remote in remote_records]
    sku_counts = Counter(normalize_key(record.sku) for record in records if record.sku)
    duplicate_skus = {sku for sku, count in sku_counts.items() if count > 1} | {normalize_key(sku) for sku in (blocked_skus or []) if sku}
    rows = []
    for record in records:
        row = build_preview_row(db, record, allow_missing_sku=allow_missing_sku)
        if not record.parent_container and normalize_key(record.sku) in duplicate_skus:
            row.action = "conflict"
            row.status = "conflict"
            row.errors.append("Duplicate WooCommerce SKU; this product was not changed.")
        rows.append(row)
    return rows


def normalize_remote_record(product: dict[str, Any], variation: dict[str, Any] | None = None, *, parent_container: bool = False) -> NormalizedWooRecord:
    source = variation or product
    remote_type = "variation" if variation else product.get("type", "simple")
    parent_name = product.get("name") or ""
    name = variation_name(parent_name, variation) if variation else parent_name
    description = name if variation else strip_html(source.get("description") or product.get("short_description") or parent_name)
    dimensions = source.get("dimensions") or {}
    parent_dimensions = product.get("dimensions") or {}
    regular_price = to_decimal_or_none(source.get("regular_price"))
    sale_price = to_decimal_or_none(source.get("sale_price"))
    price = to_decimal(source.get("price") or source.get("sale_price") or source.get("regular_price"))
    return NormalizedWooRecord(
        remote_type=remote_type,
        woo_product_id=int(product.get("id")),
        woo_variation_id=int(variation["id"]) if variation else None,
        sku=(source.get("sku") or "").strip(),
        barcode=extract_barcode(source) or extract_barcode(product) or "",
        name=name,
        parent_name=parent_name,
        variation_attributes=list(variation.get("attributes") or []) if variation else [],
        parent_container=parent_container,
        purchasable=bool(source.get("purchasable", True)) and bool(source.get("status", product.get("status")) == "publish"),
        description=description or name,
        category=first_category(product),
        brand=extract_brand(product),
        regular_price=regular_price,
        sale_price=sale_price,
        price=price,
        permalink=source.get("permalink") or product.get("permalink") or "",
        status=source.get("status") or product.get("status") or "",
        manage_stock=(product.get("manage_stock") if source.get("manage_stock") == "parent" else source.get("manage_stock")),
        stock_quantity=to_decimal_or_none(source.get("stock_quantity")),
        stock_status=source.get("stock_status") or product.get("stock_status") or "",
        weight=to_decimal_or_none(source.get("weight") or product.get("weight")),
        length=to_decimal_or_none(dimensions.get("length") or parent_dimensions.get("length")),
        width=to_decimal_or_none(dimensions.get("width") or parent_dimensions.get("width")),
        height=to_decimal_or_none(dimensions.get("height") or parent_dimensions.get("height")),
        image_url=first_image(source) or first_image(product),
        raw_payload={"product": product, "variation": variation},
    )


def build_preview_row(db: Session, record: NormalizedWooRecord, *, allow_missing_sku: bool = False) -> WooCommerceProductPreviewRow:
    warnings: list[str] = []
    errors: list[str] = []
    local_item = None if record.parent_container else find_matching_item(db, record, errors)
    action = "create"
    status = "valid"
    if record.parent_container:
        action = "skip"
        status = "skipped"
        warnings.append("Variable parent container is informational and will not become a stock item.")
        if record.sku and record.manage_stock and record.stock_quantity is not None:
            action = "conflict"
            status = "manual_review"
            errors.append("Variable parent appears independently stock-managed; manual review is required.")
    elif not record.purchasable and record.remote_type == "variation":
        action = "skip"
        status = "skipped"
        warnings.append("Variation is not currently purchasable.")
    elif not allow_missing_sku and not record.sku and local_item is None:
        action = "skip"
        status = "skipped"
        warnings.append("Missing SKU: no existing Woo identity was found, so no item was created.")
    elif errors:
        action = "conflict"
        status = "conflict"
    elif local_item is not None:
        action = "update" if woo_owned_values_changed(local_item, record) else "unchanged"
    if record.status and record.status != "publish":
        warnings.append(f"WooCommerce status is {record.status}; local item will be inactive when created.")
    return WooCommerceProductPreviewRow(
        remote_type=record.remote_type,
        product_name=record.name,
        parent_product_name=record.parent_name if record.woo_variation_id is not None else None,
        variation_attributes=record.variation_attributes,
        woo_product_id=record.woo_product_id,
        woo_variation_id=record.woo_variation_id,
        sku=record.sku,
        barcode=record.barcode,
        description=record.description,
        category=record.category,
        brand=record.brand,
        price=float(record.price),
        regular_price=float(record.regular_price) if record.regular_price is not None else None,
        stock_status=record.stock_status,
        stock_quantity_snapshot=float(record.stock_quantity) if record.stock_quantity is not None else None,
        local_item_id=local_item.id if local_item else None,
        current_mapping=mapping_summary(db, local_item) if local_item else None,
        proposed_item={"sku": record.sku, "description": record.description, "mapping_type": record.remote_type},
        action=action,
        status=status,
        warnings=warnings,
        errors=errors,
    )


def find_matching_item(db: Session, record: NormalizedWooRecord, errors: list[str]) -> InventoryItem | None:
    if record.woo_variation_id is not None:
        woo_matches = list(db.scalars(select(InventoryItem).where(InventoryItem.woo_variation_id == record.woo_variation_id)).all())
        if len(woo_matches) == 1 and woo_matches[0].woo_product_id != record.woo_product_id:
            errors.append("Woo variation ID is already attached to a different parent product.")
            return None
    else:
        woo_matches = list(db.scalars(select(InventoryItem).where(InventoryItem.woo_product_id == record.woo_product_id, InventoryItem.woo_variation_id.is_(None))).all())
    if len(woo_matches) > 1:
        errors.append("WooCommerce product and variation IDs are mapped to multiple local items.")
        return None
    woo_match = woo_matches[0] if woo_matches else None
    mapping_matches = active_mapping_matches(db, record)
    if len(mapping_matches) > 1:
        errors.append("Duplicate active Woo mapping records exist for this target.")
        return None
    mapped_item = db.get(InventoryItem, mapping_matches[0].item_id) if mapping_matches else None
    if woo_match and mapped_item and woo_match.id != mapped_item.id:
        errors.append("Woo identity fields and explicit mapping record point to different local items.")
        return None
    match = woo_match or mapped_item
    if match is None:
        match = unique_text_match(db, InventoryItem.sku, record.sku, "SKU", errors)
    if errors or match is None:
        return None
    remote_ids = (record.woo_product_id, record.woo_variation_id)
    local_ids = (match.woo_product_id, match.woo_variation_id)
    if match.woo_product_id is not None and local_ids != remote_ids:
        errors.append("The matching local item is already mapped to a different WooCommerce product or variation.")
        return None
    return match


def unique_text_match(db: Session, column, value: str, label: str, errors: list[str]) -> InventoryItem | None:
    if not value:
        return None
    matches = list(db.scalars(select(InventoryItem).where(func.lower(func.trim(column)) == normalize_key(value))).all())
    if len(matches) > 1:
        errors.append(f"Duplicate local {label}: {value}. No item was changed.")
        return None
    return matches[0] if matches else None


def build_preview_response(configured: bool, rows: list[WooCommerceProductPreviewRow], page: int | None = None, has_more: bool = False) -> WooCommerceProductPreviewResponse:
    return WooCommerceProductPreviewResponse(
        configured=configured,
        total_remote_records=len(rows),
        create_count=sum(1 for row in rows if row.action == "create"),
        update_count=sum(1 for row in rows if row.action == "update"),
        matched_count=sum(1 for row in rows if row.local_item_id is not None),
        skipped_count=sum(1 for row in rows if row.action == "skip"),
        conflict_count=sum(1 for row in rows if row.action == "conflict"),
        error_count=sum(1 for row in rows if row.action == "error"),
        warnings=[warning for row in rows for warning in row.warnings],
        errors=[error for row in rows for error in row.errors],
        preview_rows=rows,
        page=page,
        next_page=(page + 1) if page is not None and has_more else None,
        has_more=has_more,
        simple_products_examined=sum(1 for row in rows if row.remote_type == "simple"),
        variable_parents_examined=sum(1 for row in rows if row.remote_type == "variable"),
        purchasable_variations_examined=sum(1 for row in rows if row.remote_type == "variation" and row.action != "skip"),
        new_simple_count=sum(1 for row in rows if row.action == "create" and row.remote_type == "simple"),
        new_variation_count=sum(1 for row in rows if row.action == "create" and row.remote_type == "variation"),
        unchanged_count=sum(1 for row in rows if row.action == "unchanged"),
        skipped_parent_count=sum(1 for row in rows if row.remote_type == "variable" and row.action == "skip"),
        missing_sku_count=sum(1 for row in rows if not row.sku and row.remote_type != "variable"),
        duplicate_sku_conflict_count=sum(1 for row in rows if any("Duplicate WooCommerce SKU" in error or "Duplicate local SKU" in error for error in row.errors)),
        duplicate_mapping_conflict_count=sum(1 for row in rows if any("mapping" in error.casefold() or "multiple local" in error.casefold() for error in row.errors)),
        unmapped_count=sum(1 for row in rows if row.action == "skip" and row.remote_type != "variable"),
        invalid_count=sum(1 for row in rows if row.action in {"conflict", "error"}),
    )


def create_item_from_woo(record: NormalizedWooRecord, synced_at: datetime) -> InventoryItem:
    item = InventoryItem(
        client="Pongo",
        sku=record.sku,
        unit_of_measurement="Each",
        in_stock=Decimal("0"),
        allocated=Decimal("0"),
        on_order=Decimal("0"),
        active=record.status == "publish",
        non_inventory=False,
        source="woocommerce",
    )
    update_item_from_woo(item, record, synced_at)
    return item


def update_item_from_woo(item: InventoryItem, record: NormalizedWooRecord, synced_at: datetime) -> None:
    item.sku = record.sku or item.sku
    item.barcode = item.barcode or record.barcode or None
    item.description = record.description or item.description
    item.category = record.category or item.category
    item.brand = item.brand or record.brand or None
    item.recommended_retail_price = record.regular_price
    item.sales_price = record.price
    item.weight = record.weight
    item.storage_length = record.length
    item.storage_width = record.width
    item.storage_height = record.height
    item.image_url = record.image_url or item.image_url
    attach_woo_mapping(item, record, synced_at)
    apply_calculated_fields(item)


def attach_woo_mapping(item: InventoryItem, record: NormalizedWooRecord, synced_at: datetime) -> None:
    item.woo_product_id = record.woo_product_id
    item.woo_variation_id = record.woo_variation_id
    item.woo_product_type = record.remote_type
    item.woo_name = record.name
    item.woo_parent_name = record.parent_name if record.woo_variation_id is not None else None
    item.woo_variation_attributes = record.variation_attributes or None
    item.woo_permalink = record.permalink
    item.woo_status = record.status
    item.woo_manage_stock = record.manage_stock
    item.woo_stock_status = record.stock_status
    item.woo_stock_quantity_snapshot = record.stock_quantity
    item.woo_last_synced_at = synced_at
    item.woo_sync_status = "synced" if item.sku and item.barcode else "needs_setup"
    item.woo_sync_error = None


def active_mapping_matches(db: Session, record: NormalizedWooRecord) -> list[WooItemMapping]:
    if record.woo_variation_id is None:
        predicate = (
            WooItemMapping.woo_product_id == record.woo_product_id,
            WooItemMapping.woo_variation_id.is_(None),
        )
    else:
        predicate = (WooItemMapping.woo_variation_id == record.woo_variation_id,)
    return list(db.scalars(select(WooItemMapping).where(
        *predicate,
        WooItemMapping.active.is_(True),
    )).all())


def ensure_mapping_record(db: Session, item: InventoryItem, record: NormalizedWooRecord) -> None:
    remote_mappings = active_mapping_matches(db, record)
    if any(mapping.item_id != item.id for mapping in remote_mappings):
        raise ValueError("Woo target is already assigned to another active local item.")
    item_mappings = list(db.scalars(select(WooItemMapping).where(WooItemMapping.item_id == item.id, WooItemMapping.active.is_(True))).all())
    if any((mapping.woo_product_id, mapping.woo_variation_id) != (record.woo_product_id, record.woo_variation_id) for mapping in item_mappings):
        raise ValueError("Local item already has a different active Woo mapping.")
    mapping = remote_mappings[0] if remote_mappings else (item_mappings[0] if item_mappings else None)
    if mapping is None:
        mapping = WooItemMapping(item_id=item.id, woo_product_id=record.woo_product_id, woo_variation_id=record.woo_variation_id, mapping_source="sync", confidence=100, active=True)
        db.add(mapping)
    mapping.woo_sku = record.sku or None
    mapping.woo_name = record.name or None


def mapping_summary(db: Session, item: InventoryItem) -> dict:
    mappings = list(db.scalars(select(WooItemMapping).where(WooItemMapping.item_id == item.id, WooItemMapping.active.is_(True))).all())
    return {
        "item_id": item.id,
        "woo_product_id": item.woo_product_id,
        "woo_variation_id": item.woo_variation_id,
        "explicit_mapping_ids": [mapping.id for mapping in mappings],
    }


def woo_owned_values_changed(item: InventoryItem, record: NormalizedWooRecord) -> bool:
    expected = {
        "sku": record.sku or item.sku,
        "description": record.description or item.description,
        "category": record.category or item.category,
        "recommended_retail_price": record.regular_price,
        "sales_price": record.price,
        "weight": record.weight,
        "storage_length": record.length,
        "storage_width": record.width,
        "storage_height": record.height,
        "image_url": record.image_url or item.image_url,
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
    return any(comparable_value(getattr(item, field, None)) != comparable_value(value) for field, value in expected.items())


def comparable_value(value):
    if isinstance(value, Decimal):
        return value.normalize()
    return value


def unmatched_local_items(db: Session) -> tuple[int, list[str]]:
    statement = select(InventoryItem).where(InventoryItem.woo_product_id.is_(None)).order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())
    items = list(db.scalars(statement).all())
    return len(items), [item.sku or f"item-{item.id}" for item in items[:100]]


def normalize_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def store_sync_error(db: Session, sync_run_id: int, row: WooCommerceProductPreviewRow, messages: list[str]) -> None:
    store_sync_error_once(
        db,
        sync_run_id=sync_run_id,
        remote_product_id=row.woo_product_id,
        remote_variation_id=row.woo_variation_id,
        sku=row.sku,
        barcode=row.barcode,
        error_message=" ".join(messages) if messages else "WooCommerce sync row was not committed.",
        raw_payload=row.model_dump(),
    )


def first_category(product: dict[str, Any]) -> str:
    categories = product.get("categories") or []
    return categories[0].get("name", "") if categories else ""


def extract_brand(product: dict[str, Any]) -> str:
    for attribute in product.get("attributes") or []:
        if str(attribute.get("name", "")).casefold() == "brand":
            options = attribute.get("options") or []
            return str(options[0]) if options else ""
    for meta in product.get("meta_data") or []:
        if str(meta.get("key", "")).casefold() in {"brand", "_brand"}:
            return str(meta.get("value") or "")
    return ""


def extract_barcode(record: dict[str, Any]) -> str:
    if record.get("global_unique_id") not in (None, ""):
        return str(record["global_unique_id"])
    for meta in record.get("meta_data") or []:
        if str(meta.get("key", "")).casefold() in {"barcode", "_barcode", "_ywbc_barcode"}:
            return str(meta.get("value") or "")
    for attribute in record.get("attributes") or []:
        if str(attribute.get("name", "")).casefold() in {"barcode", "upc", "gtin"}:
            option = attribute.get("option") or ((attribute.get("options") or [""])[0])
            return str(option or "")
    return ""


def variation_name(parent_name: str, variation: dict[str, Any] | None) -> str:
    if not variation:
        return parent_name
    parts = [attribute.get("option") for attribute in variation.get("attributes") or [] if attribute.get("option")]
    return f"{parent_name} - {', '.join(parts)}" if parts else parent_name


def first_image(record: dict[str, Any]) -> str:
    image = record.get("image")
    if isinstance(image, dict) and image.get("src"):
        return image["src"]
    images = record.get("images") or []
    return images[0].get("src", "") if images else ""


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def to_decimal_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return to_decimal(value)
