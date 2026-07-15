import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem
from app.models.woocommerce import WooCommerceSyncError, WooCommerceSyncRun
from app.schemas.woocommerce import WooCommerceProductPreviewResponse, WooCommerceProductPreviewRow, WooCommerceSyncRequest
from app.services.items import apply_calculated_fields
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError


@dataclass
class NormalizedWooRecord:
    remote_type: str
    woo_product_id: int
    woo_variation_id: int | None
    sku: str
    barcode: str
    name: str
    description: str
    category: str
    brand: str
    regular_price: Decimal
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
    normalized_records = [normalize_remote_record(remote["product"], remote.get("variation")) for remote in remote_records]
    rows = build_preview_rows(db, remote_records, payload.blocked_skus)
    row_records = list(zip(rows, normalized_records))
    preview = build_preview_response(True, rows, payload.page, has_more)
    sync_run = WooCommerceSyncRun(sync_type="products", status="completed", started_at=started_at, created_by=payload.created_by or "system", total_remote_records=preview.total_remote_records)
    db.add(sync_run)
    db.flush()
    created_count = updated_count = matched_count = skipped_count = conflict_count = error_count = 0
    now = datetime.now(timezone.utc)

    for row, record in row_records:
        if row.action in {"skip", "conflict", "error"}:
            skipped_count += 1 if row.action == "skip" else 0
            conflict_count += 1 if row.action == "conflict" else 0
            error_count += 1 if row.action == "error" else 0
            store_sync_error(db, sync_run.id, row, row.errors or row.warnings)
            continue
        try:
            if row.action == "create":
                item = create_item_from_woo(record, now)
                db.add(item)
                created_count += 1
            elif row.local_item_id is not None:
                item = db.get(InventoryItem, row.local_item_id)
                if item is None:
                    error_count += 1
                    store_sync_error(db, sync_run.id, row, ["Matched local item no longer exists."])
                    continue
                attach_woo_mapping(item, record, now)
                db.add(item)
                updated_count += 1
                matched_count += 1
        except Exception as exc:
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
    )
    return sync_run, response


def fetch_product_records(client: WooCommerceClient, payload: WooCommerceSyncRequest) -> tuple[list[dict[str, Any]], bool]:
    if payload.page is not None:
        return client.fetch_sellable_product_batch(payload.page, payload.per_page, payload.include_statuses)
    return client.fetch_all_sellable_products_and_variations(payload.include_statuses, payload.limit), False


def build_preview_rows(db: Session, remote_records: list[dict[str, Any]], blocked_skus: list[str] | None = None) -> list[WooCommerceProductPreviewRow]:
    records = [normalize_remote_record(remote["product"], remote.get("variation")) for remote in remote_records]
    sku_counts = Counter(normalize_key(record.sku) for record in records if record.sku)
    duplicate_skus = {sku for sku, count in sku_counts.items() if count > 1} | {normalize_key(sku) for sku in (blocked_skus or []) if sku}
    rows = []
    for record in records:
        row = build_preview_row(db, record)
        if normalize_key(record.sku) in duplicate_skus:
            row.action = "conflict"
            row.status = "conflict"
            row.errors.append("Duplicate WooCommerce SKU; this product was not changed.")
        rows.append(row)
    return rows


def normalize_remote_record(product: dict[str, Any], variation: dict[str, Any] | None = None) -> NormalizedWooRecord:
    source = variation or product
    remote_type = "variation" if variation else product.get("type", "simple")
    parent_name = product.get("name") or ""
    name = variation_name(parent_name, variation) if variation else parent_name
    description = name if variation else strip_html(source.get("description") or product.get("short_description") or parent_name)
    dimensions = source.get("dimensions") or {}
    parent_dimensions = product.get("dimensions") or {}
    regular_price = to_decimal(source.get("regular_price"))
    sale_price = to_decimal_or_none(source.get("sale_price"))
    price = to_decimal(source.get("price") or source.get("sale_price") or source.get("regular_price"))
    return NormalizedWooRecord(
        remote_type=remote_type,
        woo_product_id=int(product.get("id")),
        woo_variation_id=int(variation["id"]) if variation else None,
        sku=(source.get("sku") or "").strip(),
        barcode=extract_barcode(source) or extract_barcode(product) or "",
        name=name,
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


def build_preview_row(db: Session, record: NormalizedWooRecord) -> WooCommerceProductPreviewRow:
    warnings: list[str] = []
    errors: list[str] = []
    local_item = find_matching_item(db, record, errors)
    action = "create"
    status = "valid"
    if not record.sku:
        action = "skip"
        status = "skipped"
        warnings.append("SKU is required for WooCommerce product sync.")
    elif errors:
        action = "conflict"
        status = "conflict"
    elif local_item is not None:
        action = "update"
    if record.status and record.status != "publish":
        warnings.append(f"WooCommerce status is {record.status}; local item will be inactive when created.")
    return WooCommerceProductPreviewRow(
        remote_type=record.remote_type,
        woo_product_id=record.woo_product_id,
        woo_variation_id=record.woo_variation_id,
        sku=record.sku,
        barcode=record.barcode,
        description=record.description,
        category=record.category,
        brand=record.brand,
        price=float(record.price),
        regular_price=float(record.regular_price),
        stock_status=record.stock_status,
        stock_quantity_snapshot=float(record.stock_quantity) if record.stock_quantity is not None else None,
        local_item_id=local_item.id if local_item else None,
        action=action,
        status=status,
        warnings=warnings,
        errors=errors,
    )


def find_matching_item(db: Session, record: NormalizedWooRecord, errors: list[str]) -> InventoryItem | None:
    woo_matches = list(db.scalars(
        select(InventoryItem).where(
            InventoryItem.woo_product_id == record.woo_product_id,
            InventoryItem.woo_variation_id.is_(None) if record.woo_variation_id is None else InventoryItem.woo_variation_id == record.woo_variation_id,
        )
    ).all())
    if len(woo_matches) > 1:
        errors.append("WooCommerce product and variation IDs are mapped to multiple local items.")
        return None
    woo_match = woo_matches[0] if woo_matches else None
    sku_match = unique_text_match(db, InventoryItem.sku, record.sku, "SKU", errors)
    if errors:
        return None
    if woo_match and sku_match and woo_match.id != sku_match.id:
        errors.append("WooCommerce IDs and SKU match different local items.")
        return None
    match = woo_match or sku_match
    if match is None:
        match = unique_text_match(db, InventoryItem.barcode, record.barcode, "Barcode", errors)
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
    item.description = record.description or item.description
    item.category = record.category or item.category
    item.brand = record.brand or item.brand
    item.recommended_retail_price = record.regular_price
    item.sales_price = record.price
    item.weight = record.weight
    item.storage_length = record.length
    item.storage_width = record.width
    item.storage_height = record.height
    item.image_url = record.image_url or item.image_url
    if record.barcode and not item.barcode:
        item.barcode = record.barcode
    attach_woo_mapping(item, record, synced_at)
    apply_calculated_fields(item)


def attach_woo_mapping(item: InventoryItem, record: NormalizedWooRecord, synced_at: datetime) -> None:
    item.woo_product_id = record.woo_product_id
    item.woo_variation_id = record.woo_variation_id
    item.woo_product_type = record.remote_type
    item.woo_permalink = record.permalink
    item.woo_status = record.status
    item.woo_manage_stock = record.manage_stock
    item.woo_stock_status = record.stock_status
    item.woo_stock_quantity_snapshot = record.stock_quantity
    item.woo_last_synced_at = synced_at
    item.woo_sync_status = "synced"
    item.woo_sync_error = None


def unmatched_local_items(db: Session) -> tuple[int, list[str]]:
    statement = select(InventoryItem).where(InventoryItem.woo_product_id.is_(None)).order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())
    items = list(db.scalars(statement).all())
    return len(items), [item.sku or f"item-{item.id}" for item in items[:100]]


def normalize_key(value: str | None) -> str:
    return str(value or "").strip().casefold()


def store_sync_error(db: Session, sync_run_id: int, row: WooCommerceProductPreviewRow, messages: list[str]) -> None:
    db.add(
        WooCommerceSyncError(
            sync_run_id=sync_run_id,
            remote_product_id=row.woo_product_id,
            remote_variation_id=row.woo_variation_id,
            sku=row.sku,
            barcode=row.barcode,
            error_message=" ".join(messages) if messages else "WooCommerce sync row was not committed.",
            raw_payload=row.model_dump(),
        )
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
