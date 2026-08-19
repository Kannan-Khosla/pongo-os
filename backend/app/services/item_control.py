from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, union_all
from sqlalchemy.orm import Session, selectinload

from app.models.allocations import AllocationLine
from app.models.cycle_counts import CycleCountLine
from app.models.fulfillments import FulfillmentLine
from app.models.item_notes import ItemNote
from app.models.imports import ItemImportChange
from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation, InventoryLocation, InventoryTransferLine, MovementType, StockAdjustmentLine, StockMovement
from app.models.orders import OrderItem
from app.models.picks import PickLine
from app.models.receipts import ReceiptItem
from app.services.item_identifiers import barcode_scan_candidates
from app.services.location_inventory import get_or_create_item_location, lock_inventory_stock, recalculate_item_location, recalculate_item_totals, to_decimal


ITEM_BULK_MODEL_FIELDS = {
    "client",
    "description",
    "category",
    "brand",
    "tags",
    "manufacturer",
    "manufacturer_website",
    "unit_cost",
    "sales_price",
    "recommended_retail_price",
    "unit_of_measurement",
    "par_level",
    "default_econ_order",
    "default_lead_time_days",
    "reorder",
    "active",
    "non_inventory",
    "assembly",
    "track_lot",
    "perishable",
    "serializable",
    "storage_length",
    "storage_width",
    "storage_height",
    "weight",
}
ITEM_BULK_OPERATION_FIELDS = {"add_tags", "location_id", "make_default_location"}
ITEM_BULK_ALLOWED_FIELDS = ITEM_BULK_MODEL_FIELDS | ITEM_BULK_OPERATION_FIELDS
ITEM_BULK_BLOCKED_FIELDS = {
    "id",
    "sku",
    "barcode",
    "image_url",
    "source",
    "warehouse",
    "inventory_location",
    "default_location",
    "in_stock",
    "allocated",
    "sellable",
    "under_par",
    "on_order",
    "woo_product_id",
    "woo_variation_id",
    "woo_stock_quantity_snapshot",
    "woo_stock_status",
    "woo_name",
    "woo_parent_name",
    "woo_permalink",
    "woo_status",
    "woo_sync_status",
    "woo_sync_error",
    "storage_volume",
}
ITEM_SEARCH_COLUMNS = (
    InventoryItem.sku,
    InventoryItem.barcode,
    InventoryItem.woo_name,
    InventoryItem.description,
    InventoryItem.category,
    InventoryItem.brand,
    InventoryItem.manufacturer,
    InventoryItem.warehouse,
    InventoryItem.inventory_location,
    InventoryItem.tags,
)

ITEM_BULK_DECIMAL_FIELDS = {
    "unit_cost",
    "sales_price",
    "recommended_retail_price",
    "par_level",
    "default_econ_order",
    "weight",
    "storage_length",
    "storage_width",
    "storage_height",
}
ITEM_BULK_BOOLEAN_FIELDS = {"reorder", "active", "non_inventory", "assembly", "track_lot", "perishable", "serializable"}
ITEM_BULK_TEXT_LIMITS = {
    "client": 120,
    "description": 10000,
    "category": 200,
    "brand": 200,
    "tags": 2000,
    "add_tags": 2000,
    "manufacturer": 200,
    "manufacturer_website": 500,
    "unit_of_measurement": 50,
}


def item_keyword_predicates(query: str) -> list:
    return [
        or_(
            *(column.ilike(f"%{keyword}%") for column in ITEM_SEARCH_COLUMNS),
            InventoryItem.barcode.in_(barcode_scan_candidates(keyword)),
        )
        for keyword in query.split()
    ]


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def item_summary(item: InventoryItem | None) -> dict[str, Any] | None:
    if item is None:
        return None
    return {
        "id": item.id,
        "client": item.client,
        "sku": item.sku,
        "barcode": item.barcode,
        "product_name": item.woo_name or item.description,
        "description": item.description,
        "category": item.category,
        "brand": item.brand,
        "tags": item.tags,
        "image_url": item.image_url,
        "unit_of_measurement": item.unit_of_measurement,
        "unit_cost": as_float(item.unit_cost),
        "sales_price": as_float(item.sales_price),
        "recommended_retail_price": as_float(item.recommended_retail_price),
        "manufacturer": item.manufacturer,
        "manufacturer_website": item.manufacturer_website,
        "warehouse": item.warehouse,
        "inventory_location": item.inventory_location,
        "default_location": item.default_location,
        "in_stock": as_float(item.in_stock),
        "allocated": as_float(item.allocated),
        "sellable": as_float(item.sellable),
        "under_par": item.under_par,
        "on_order": as_float(item.on_order),
        "weight": as_float(item.weight),
        "active": item.active,
        "woo_product_id": item.woo_product_id,
        "woo_variation_id": item.woo_variation_id,
        "woo_stock_quantity_snapshot": as_float(item.woo_stock_quantity_snapshot),
        "woo_stock_status": item.woo_stock_status,
        "woo_sync_status": item.woo_sync_status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def sku_is_locked(db: Session, item: InventoryItem) -> bool:
    return bool(
        to_decimal(item.in_stock) != 0
        or to_decimal(item.allocated) != 0
        or db.scalar(select(StockMovement.id).where(StockMovement.inventory_item_id == item.id).limit(1))
    )


def item_location_summary(row: InventoryItemLocation, item: InventoryItem | None = None) -> dict[str, Any]:
    recalculate_item_location(row, item)
    return {
        "id": row.id,
        "warehouse": row.warehouse,
        "inventory_location": row.inventory_location,
        "location_code": row.location_code,
        "location_name": row.location_name,
        "is_default_location": row.is_default_location,
        "in_stock": as_float(row.in_stock) or 0,
        "allocated": as_float(row.allocated) or 0,
        "sellable": as_float(row.sellable) or 0,
        "on_order": as_float(row.on_order) or 0,
        "par_level": as_float(row.par_level),
        "under_par": row.under_par,
        "active": row.active,
        "updated_at": row.updated_at,
    }


def build_item_detail(db: Session, item_id: int) -> dict[str, Any]:
    item = db.scalars(select(InventoryItem).where(InventoryItem.id == item_id).options(selectinload(InventoryItem.locations))).one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    recalculate_item_totals(db, item.id)
    stock_by_location = [item_location_summary(row, item) for row in sorted(item.locations, key=lambda row: (not row.is_default_location, row.warehouse or "", row.inventory_location or ""))]
    quick_stats = build_item_quick_stats(db, item)
    summary = item_summary(item)
    summary["sku_locked"] = sku_is_locked(db, item)
    return {
        "item": summary,
        "stock_by_location": stock_by_location,
        "recent_activity": build_item_activity(db, item_id, limit=25, offset=0)["activity"],
        "quick_stats": quick_stats,
    }


def build_item_quick_stats(db: Session, item: InventoryItem) -> dict[str, Any]:
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    last_received = db.scalar(select(func.max(ReceiptItem.created_at)).where(ReceiptItem.inventory_item_id == item.id))
    last_counted = db.scalar(select(func.max(CycleCountLine.created_at)).where(CycleCountLine.item_id == item.id))
    last_adjusted = db.scalar(select(func.max(StockAdjustmentLine.created_at)).where(StockAdjustmentLine.inventory_item_id == item.id))
    last_ordered = db.scalar(select(func.max(OrderItem.created_at)).where(OrderItem.inventory_item_id == item.id))
    total_ordered_30 = db.scalar(select(func.coalesce(func.sum(OrderItem.quantity_ordered), 0)).where(OrderItem.inventory_item_id == item.id, OrderItem.created_at >= thirty_days_ago)) or 0
    total_fulfilled_30 = db.scalar(select(func.coalesce(func.sum(FulfillmentLine.quantity_to_fulfill), 0)).where(FulfillmentLine.item_id == item.id, FulfillmentLine.created_at >= thirty_days_ago)) or 0
    unit_cost = item.unit_cost or Decimal("0")
    return {
        "total_locations": len([row for row in item.locations if row.active]),
        "inventory_value": as_float((item.in_stock or Decimal("0")) * unit_cost),
        "last_received_at": last_received,
        "last_counted_at": last_counted,
        "last_adjusted_at": last_adjusted,
        "last_ordered_at": last_ordered,
        "total_ordered_qty_last_30_days": as_float(total_ordered_30) or 0,
        "total_fulfilled_qty_last_30_days": as_float(total_fulfilled_30) or 0,
    }


def activity_row(
    *,
    id: str,
    type: str,
    title: str,
    description: str | None,
    created_at: datetime | None,
    quantity_change: Decimal | float | None = None,
    warehouse: str | None = None,
    inventory_location: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    reference_number: str | None = None,
    severity: str = "info",
) -> dict[str, Any]:
    return {
        "id": id,
        "type": type,
        "title": title,
        "description": description,
        "quantity_change": as_float(quantity_change),
        "warehouse": warehouse,
        "inventory_location": inventory_location,
        "reference_type": reference_type,
        "reference_id": reference_id,
        "reference_number": reference_number,
        "created_at": created_at,
        "severity": severity,
    }


def build_item_activity(
    db: Session,
    item_id: int,
    *,
    type_filter: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    item = db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    safe_limit = max(1, min(limit, 200))
    safe_offset = max(0, offset)
    per_source_limit = safe_offset + safe_limit
    requested_type = type_filter or "all"
    rows: list[dict[str, Any]] = []
    sources: list[tuple[Any, list[Any], Any]] = []

    def predicates_for(created_at_column: Any, *predicates: Any) -> list[Any]:
        result = list(predicates)
        if start_date:
            result.append(created_at_column >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc))
        if end_date:
            next_day = end_date + timedelta(days=1)
            result.append(created_at_column < datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc))
        return result

    def include(activity_type: str) -> bool:
        return requested_type in {"all", activity_type}

    transfer_movement_types = (MovementType.transfer_in, MovementType.transfer_out)
    adjustment_movement_types = (
        MovementType.adjustment_increase,
        MovementType.adjustment_decrease,
        MovementType.damage,
        MovementType.loss,
        MovementType.correction,
    )
    adjustment_movement_values = {member.value for member in adjustment_movement_types}

    def movement_activity_row(movement: StockMovement) -> dict[str, Any]:
        movement_type = movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type)
        normalized_type = "transfer" if movement_type.startswith("transfer_") else ("adjustment" if movement_type in adjustment_movement_values else "stock_movement")
        return activity_row(
            id=f"movement-{movement.id}",
            type=normalized_type,
            title=movement_type.replace("_", " ").title(),
            description=movement.reason or movement.notes,
            quantity_change=movement.quantity_change,
            warehouse=movement.warehouse,
            inventory_location=movement.inventory_location_name,
            reference_type=movement.reference_type,
            reference_id=movement.reference_id,
            reference_number=movement.reference_number,
            created_at=movement.created_at,
            severity="success" if (movement.quantity_change or 0) >= 0 else "warning",
        )

    movement_predicates = [StockMovement.inventory_item_id == item_id]
    if requested_type == "transfer":
        movement_predicates.append(StockMovement.movement_type.in_(transfer_movement_types))
    elif requested_type == "adjustment":
        movement_predicates.append(StockMovement.movement_type.in_(adjustment_movement_types))
    elif requested_type == "stock_movement":
        movement_predicates.append(StockMovement.movement_type.notin_((*transfer_movement_types, *adjustment_movement_types)))
    if requested_type in {"all", "transfer", "adjustment", "stock_movement"}:
        sources.append(
            (
                StockMovement,
                predicates_for(StockMovement.created_at, *movement_predicates),
                movement_activity_row,
            )
        )
    if include("note"):
        sources.append((ItemNote, predicates_for(ItemNote.created_at, ItemNote.inventory_item_id == item_id), lambda note: activity_row(id=f"note-{note.id}", type="note", title=f"{note.note_type or 'General'} note", description=note.note, created_at=note.created_at, reference_type="item_note", reference_id=note.id)))
    if include("metadata_import"):
        sources.append((ItemImportChange, predicates_for(ItemImportChange.created_at, ItemImportChange.item_id == item_id), lambda change: activity_row(id=f"item-import-change-{change.id}", type="metadata_import", title=f"{change.field_name.replace('_', ' ').title()} imported", description=f"{change.previous_value!s} → {change.new_value!s} from {change.source_filename or 'CSV'}", created_at=change.created_at, reference_type="import_job", reference_id=change.import_job_id)))
    if include("receipt"):
        sources.append((ReceiptItem, predicates_for(ReceiptItem.created_at, ReceiptItem.inventory_item_id == item_id), lambda receipt: activity_row(id=f"receipt-{receipt.id}", type="receipt", title="Receipt line", description=receipt.notes, quantity_change=receipt.quantity_received or receipt.quantity, warehouse=receipt.warehouse, inventory_location=receipt.inventory_location_name, reference_type="receipt", reference_id=receipt.receipt_id, reference_number=receipt.po_or_receipt_number, created_at=receipt.created_at, severity="success")))
    if include("cycle_count"):
        sources.append((CycleCountLine, predicates_for(CycleCountLine.created_at, CycleCountLine.item_id == item_id), lambda count: activity_row(id=f"cycle-{count.id}", type="cycle_count", title="Cycle count", description=count.notes, quantity_change=count.variance_quantity, warehouse=count.warehouse, inventory_location=count.inventory_location, reference_type="cycle_count", reference_id=count.cycle_count_id, created_at=count.created_at, severity="warning" if count.variance_quantity else "info")))
    if include("transfer"):
        sources.append((InventoryTransferLine, predicates_for(InventoryTransferLine.created_at, InventoryTransferLine.inventory_item_id == item_id), lambda transfer: activity_row(id=f"transfer-{transfer.id}", type="transfer", title="Transfer", description=transfer.notes, quantity_change=transfer.quantity, warehouse=transfer.from_warehouse, inventory_location=transfer.from_inventory_location, reference_type="transfer", reference_id=transfer.transfer_id, created_at=transfer.created_at)))
    if include("adjustment"):
        sources.append((StockAdjustmentLine, predicates_for(StockAdjustmentLine.created_at, StockAdjustmentLine.inventory_item_id == item_id), lambda adjustment: activity_row(id=f"adjustment-{adjustment.id}", type="adjustment", title="Adjustment", description=adjustment.notes, quantity_change=adjustment.quantity_change, warehouse=adjustment.warehouse, inventory_location=adjustment.inventory_location, reference_type="stock_adjustment", reference_id=adjustment.adjustment_id, created_at=adjustment.created_at, severity="warning")))
    if include("allocation"):
        sources.append((AllocationLine, predicates_for(AllocationLine.created_at, AllocationLine.item_id == item_id), lambda allocation: activity_row(id=f"allocation-{allocation.id}", type="allocation", title="Allocation", description=allocation.notes, quantity_change=allocation.quantity_to_allocate, warehouse=allocation.warehouse, inventory_location=allocation.inventory_location, reference_type="allocation", reference_id=allocation.allocation_id, created_at=allocation.created_at)))
    if include("pick"):
        sources.append((PickLine, predicates_for(PickLine.created_at, PickLine.item_id == item_id), lambda pick: activity_row(id=f"pick-{pick.id}", type="pick", title="Pick", description=pick.notes, quantity_change=pick.quantity_to_pick, warehouse=pick.warehouse, inventory_location=pick.inventory_location, reference_type="pick", reference_id=pick.pick_id, created_at=pick.created_at)))
    if include("fulfillment"):
        sources.append((FulfillmentLine, predicates_for(FulfillmentLine.created_at, FulfillmentLine.item_id == item_id), lambda fulfillment: activity_row(id=f"fulfillment-{fulfillment.id}", type="fulfillment", title="Fulfillment", description=fulfillment.notes, quantity_change=fulfillment.quantity_to_fulfill, warehouse=fulfillment.warehouse, inventory_location=fulfillment.inventory_location, reference_type="fulfillment", reference_id=fulfillment.fulfillment_id, created_at=fulfillment.created_at, severity="success")))
    if include("order"):
        sources.append((OrderItem, predicates_for(OrderItem.created_at, OrderItem.inventory_item_id == item_id), lambda order: activity_row(id=f"order-{order.id}", type="order", title="Order line", description=order.description or order.name, quantity_change=order.quantity_ordered, reference_type="order", reference_id=order.order_id, created_at=order.created_at)))

    total = 0
    if sources:
        count_statement = union_all(*(select(func.count(model.id)).where(*predicates) for model, predicates, _mapper in sources))
        total = sum(int(count or 0) for count in db.scalars(count_statement).all())
        for model, predicates, mapper in sources:
            source_rows = db.scalars(
                select(model)
                .where(*predicates)
                .order_by(model.created_at.desc(), model.id.desc())
                .limit(per_source_limit)
            ).all()
            rows.extend(mapper(row) for row in source_rows)

    rows.sort(key=lambda row: row["created_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return {"activity": rows[safe_offset : safe_offset + safe_limit], "total": total, "limit": safe_limit, "offset": safe_offset}


def search_items(db: Session, *, q: str | None = None, sku: str | None = None, barcode: str | None = None, brand: str | None = None, category: str | None = None, limit: int = 25) -> dict[str, Any]:
    statement = select(InventoryItem)
    ordering = [InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc()]
    if q:
        statement = statement.where(*item_keyword_predicates(q))
        term = q.strip()
        if term:
            contains = f"%{term}%"
            prefix = f"{term}%"
            barcode_candidates = barcode_scan_candidates(term)
            ordering.insert(
                0,
                case(
                    (InventoryItem.sku.ilike(prefix), 0),
                    (InventoryItem.barcode.in_(barcode_candidates), 1),
                    (InventoryItem.sku.ilike(contains), 2),
                    (InventoryItem.barcode.ilike(prefix), 3),
                    (InventoryItem.barcode.ilike(contains), 4),
                    (InventoryItem.woo_name.ilike(contains), 5),
                    (InventoryItem.description.ilike(contains), 5),
                    else_=6,
                ),
            )
    if sku:
        statement = statement.where(InventoryItem.sku.ilike(f"%{sku}%"))
    if barcode:
        statement = statement.where(
            or_(
                InventoryItem.barcode.ilike(f"%{barcode}%"),
                InventoryItem.barcode.in_(barcode_scan_candidates(barcode)),
            )
        )
    if brand:
        statement = statement.where(InventoryItem.brand == brand)
    if category:
        statement = statement.where(InventoryItem.category == category)
    items = list(db.scalars(statement.order_by(*ordering).limit(max(1, min(limit, 100)))).all())
    return {
        "items": [
            {
                **(item_summary(item) or {}),
                "woo_mapping_summary": {
                    "mapped": bool(item.woo_product_id or item.woo_variation_id),
                    "product_id": item.woo_product_id,
                    "variation_id": item.woo_variation_id,
                    "sync_status": item.woo_sync_status,
                },
            }
            for item in items
        ],
        "total": len(items),
    }


def normalize_bulk_tags(value: Any) -> list[str]:
    values = value if isinstance(value, list) else str(value or "").replace("|", ",").split(",")
    return list(dict.fromkeys(str(tag).strip() for tag in values if str(tag).strip()))


def merge_bulk_tags(current: str | None, additions: Any) -> str | None:
    tags = normalize_bulk_tags(current) + normalize_bulk_tags(additions)
    unique = list(dict.fromkeys(tag.casefold() for tag in tags))
    labels = {tag.casefold(): tag for tag in tags}
    return ", ".join(labels[tag] for tag in unique) or None


def bulk_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise HTTPException(status_code=422, detail=f"Invalid boolean value: {value}")


def bulk_value_warnings(updates: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for field in ITEM_BULK_DECIMAL_FIELDS.intersection(updates):
        try:
            value = Decimal(str(updates[field]).replace(",", ""))
        except (InvalidOperation, ValueError):
            warnings.append(f"{field.replace('_', ' ').title()} must be a number.")
            continue
        if value < 0:
            warnings.append(f"{field.replace('_', ' ').title()} cannot be negative.")
    if "default_lead_time_days" in updates:
        try:
            if int(updates["default_lead_time_days"]) < 0:
                warnings.append("Default Lead Time Days cannot be negative.")
        except (TypeError, ValueError):
            warnings.append("Default Lead Time Days must be a whole number.")
    for field in ITEM_BULK_BOOLEAN_FIELDS.intersection(updates):
        try:
            bulk_boolean(updates[field])
        except HTTPException:
            warnings.append(f"{field.replace('_', ' ').title()} must be Yes or No.")
    for field, limit in ITEM_BULK_TEXT_LIMITS.items():
        if field in updates and len(str(updates[field])) > limit:
            warnings.append(f"{field.replace('_', ' ').title()} cannot exceed {limit} characters.")
    return warnings


def preview_bulk_item_update(db: Session, item_ids: list[int], updates: dict[str, Any]) -> dict[str, Any]:
    blocked = sorted(set(updates).intersection(ITEM_BULK_BLOCKED_FIELDS))
    allowed_updates = {key: value for key, value in updates.items() if key in ITEM_BULK_ALLOWED_FIELDS}
    unknown = sorted(set(updates) - ITEM_BULK_ALLOWED_FIELDS - ITEM_BULK_BLOCKED_FIELDS)
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids))).all()) if item_ids else []
    warnings = bulk_value_warnings(allowed_updates)
    if blocked:
        warnings.append(f"Blocked unique, stock, or integration fields: {', '.join(blocked)}")
    if unknown:
        warnings.append(f"Unsupported fields: {', '.join(unknown)}")
    location_id = allowed_updates.get("location_id")
    try:
        normalized_location_id = int(location_id) if location_id not in (None, "") else None
    except (TypeError, ValueError):
        normalized_location_id = None
        warnings.append("The selected inventory location is invalid.")
    location = db.get(InventoryLocation, normalized_location_id) if normalized_location_id is not None else None
    if location_id not in (None, "") and location is None:
        warnings.append("The selected inventory location does not exist.")
    elif location is not None and not location.active:
        warnings.append("The selected inventory location is inactive.")
    if allowed_updates.get("make_default_location") and location is None:
        warnings.append("Choose a location before making it the default.")
    if "add_tags" in allowed_updates and not normalize_bulk_tags(allowed_updates["add_tags"]):
        warnings.append("Enter at least one tag to add.")
    return {
        "affected_count": len(items),
        "fields_to_update": sorted(allowed_updates),
        "sample_items": [item_summary(item) for item in items[:10]],
        "warnings": warnings,
        "can_commit": bool(items and allowed_updates and not warnings),
    }


def commit_bulk_item_update(db: Session, item_ids: list[int], updates: dict[str, Any], *, created_by: str = "system") -> dict[str, Any]:
    preview = preview_bulk_item_update(db, item_ids, updates)
    if not preview["can_commit"]:
        raise HTTPException(status_code=400, detail=preview)
    allowed_updates = {key: value for key, value in updates.items() if key in ITEM_BULK_ALLOWED_FIELDS}
    location_id = allowed_updates.pop("location_id", None)
    make_default_location = bulk_boolean(allowed_updates.pop("make_default_location", False))
    add_tags = allowed_updates.pop("add_tags", None)
    location = db.get(InventoryLocation, int(location_id)) if location_id not in (None, "") else None
    lock_inventory_stock(db, item_ids)
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.id.in_(item_ids)).order_by(InventoryItem.id).execution_options(populate_existing=True)).all()) if item_ids else []
    for item in items:
        for key, value in allowed_updates.items():
            if key in ITEM_BULK_DECIMAL_FIELDS:
                setattr(item, key, to_decimal(value) if value not in (None, "") else None)
            elif key == "default_lead_time_days":
                setattr(item, key, int(value) if value not in (None, "") else None)
            elif key in ITEM_BULK_BOOLEAN_FIELDS:
                setattr(item, key, bulk_boolean(value))
            else:
                setattr(item, key, value)
        if add_tags is not None:
            item.tags = merge_bulk_tags(item.tags, add_tags)
        if location is not None:
            get_or_create_item_location(
                db,
                item,
                location.warehouse,
                location.location_code or location.location_name,
                location_id=location.id,
                is_default_location=make_default_location,
            )
        else:
            recalculate_item_totals(db, item.id)
        changed_fields = sorted([*allowed_updates, *(["tags"] if add_tags is not None else []), *(["location"] if location is not None else [])])
        db.add(
            InventoryAuditEvent(
                item_id=item.id,
                sku=item.sku,
                barcode=item.barcode,
                event_type="bulk_metadata_update",
                quantity_delta=Decimal("0"),
                previous_in_stock=item.in_stock or Decimal("0"),
                new_in_stock=item.in_stock or Decimal("0"),
                previous_allocated=item.allocated or Decimal("0"),
                new_allocated=item.allocated or Decimal("0"),
                previous_sellable=item.sellable or Decimal("0"),
                new_sellable=item.sellable or Decimal("0"),
                warehouse=item.warehouse,
                inventory_location=item.inventory_location,
                reference_type="item_bulk_edit",
                notes=", ".join(changed_fields),
                created_by=created_by,
            )
        )
    db.commit()
    fields_updated = sorted([*allowed_updates, *(["tags"] if add_tags is not None else []), *(["location"] if location is not None else [])])
    return {"updated_count": len(items), "fields_updated": fields_updated, "warnings": preview["warnings"]}
