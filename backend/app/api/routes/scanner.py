from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.models.cycle_counts import CycleCount, CycleCountLine
from app.models.inventory import InventoryItem, InventoryItemLocation, InventoryLocation
from app.models.scanner import ScannerEvent
from app.services.bulk_receiving import commit_bulk_receipt, preview_bulk_receipt
from app.services.auth import authenticated_actor
from app.services.item_control import item_location_summary, item_summary
from app.services.location_inventory import (
    create_committed_adjustment,
    create_committed_transfer,
    cycle_count_location,
    find_item_location,
    get_or_create_item_location,
    next_adjustment_number,
    to_decimal,
)
from app.services.order_workflow import auto_allocate_processing_orders_fifo
from app.services.stock_mutation_guard import IdempotencyConflict
from app.services.woocommerce_client import WooCommerceClient
from app.services.woocommerce_writeback import sync_inventory_stock

router = APIRouter(prefix="/scanner", tags=["scanner"])


def log_scan(db: Session, session_type: str, scan_input: str, status: str, message: str | None = None, *, matched_type: str | None = None, matched_id: int | None = None, quantity=None, warehouse: str | None = None, inventory_location: str | None = None) -> None:
    db.add(
        ScannerEvent(
            session_type=session_type,
            scan_input=scan_input or "",
            matched_entity_type=matched_type,
            matched_entity_id=matched_id,
            result_status=status,
            message=message,
            quantity=quantity,
            warehouse=warehouse,
            inventory_location=inventory_location,
            created_at=datetime.now(timezone.utc),
        )
    )


def resolve_scan_item(db: Session, scan_input: str | None) -> InventoryItem | None:
    value = (scan_input or "").strip()
    if not value:
        return None
    exact_matches = list(
        db.scalars(
            select(InventoryItem)
            .where(or_(InventoryItem.sku == value, InventoryItem.barcode == value))
            .order_by(InventoryItem.sku.asc().nullslast(), InventoryItem.id.asc())
        ).all()
    )
    if len(exact_matches) > 1:
        raise HTTPException(status_code=409, detail="Scan matches multiple inventory items; use a unique SKU or barcode.")
    if exact_matches:
        return exact_matches[0]
    if value.isdigit() and (item := db.get(InventoryItem, int(value))) is not None:
        return item
    description_matches = list(db.scalars(select(InventoryItem).where(InventoryItem.description.ilike(f"%{value}%"))).all())
    if len(description_matches) > 1:
        raise HTTPException(status_code=409, detail="Scan matches multiple inventory items; use a unique SKU or barcode.")
    return description_matches[0] if description_matches else None


@router.get("/inventory/lookup")
def inventory_lookup(scan_input: str, db: Session = Depends(get_db)) -> dict:
    item = resolve_scan_item(db, scan_input)
    if item is None:
        log_scan(db, "inventory_lookup", scan_input, "error", "No matching item.")
        db.commit()
        return {"matched": False, "item": None, "stock_by_location": [], "warnings": ["No matching item found."]}
    rows = list(db.scalars(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item.id, InventoryItemLocation.active.is_(True))).all())
    log_scan(db, "inventory_lookup", scan_input, "success", "Item matched.", matched_type="inventory_item", matched_id=item.id)
    db.commit()
    return {"matched": True, "item": item_summary(item), "stock_by_location": [item_location_summary(row, item) for row in rows], "warnings": []}


@router.get("/location/lookup")
def location_lookup(scan_input: str, db: Session = Depends(get_db)) -> dict:
    value = (scan_input or "").strip()
    location = db.scalars(select(InventoryLocation).where(or_(InventoryLocation.location_code == value, InventoryLocation.location_name == value, InventoryLocation.warehouse == value, InventoryLocation.description.ilike(f"%{value}%")))).first()
    if location is None:
        rows = list(db.scalars(select(InventoryItemLocation).where(or_(InventoryItemLocation.location_code == value, InventoryItemLocation.inventory_location == value, InventoryItemLocation.location_name == value, InventoryItemLocation.warehouse == value)).options(selectinload(InventoryItemLocation.inventory_item))).all())
    else:
        rows = list(db.scalars(select(InventoryItemLocation).where(or_(InventoryItemLocation.location_id == location.id, InventoryItemLocation.inventory_location == location.location_code, InventoryItemLocation.location_code == location.location_code)).options(selectinload(InventoryItemLocation.inventory_item))).all())
    if location is None and not rows:
        log_scan(db, "location_lookup", value, "error", "No matching location.")
        db.commit()
        return {"matched": False, "location": None, "items": [], "total_skus": 0, "total_units": 0, "inventory_value": 0}
    total_units = sum((row.in_stock or Decimal("0") for row in rows), Decimal("0"))
    inventory_value = sum(((row.in_stock or Decimal("0")) * (row.inventory_item.unit_cost or Decimal("0")) for row in rows if row.inventory_item), Decimal("0"))
    log_scan(db, "location_lookup", value, "success", "Location matched.", matched_type="inventory_location", matched_id=location.id if location else None)
    db.commit()
    return {
        "matched": True,
        "location": {
            "id": location.id if location else None,
            "warehouse": location.warehouse if location else (rows[0].warehouse if rows else None),
            "location_code": location.location_code if location else (rows[0].location_code if rows else None),
            "location_name": location.location_name if location else (rows[0].location_name if rows else None),
        },
        "items": [{**item_location_summary(row, row.inventory_item), "sku": row.inventory_item.sku if row.inventory_item else None, "description": row.inventory_item.description if row.inventory_item else None} for row in rows[:100]],
        "total_skus": len(rows),
        "total_units": float(total_units),
        "inventory_value": float(inventory_value),
    }


@router.post("/receiving/scan/preview")
def receiving_scan_preview(payload: dict, db: Session = Depends(get_db)) -> dict:
    preview = preview_bulk_receipt({"warehouse": payload.get("warehouse"), "lines": [{**payload, "quantity": payload.get("quantity", 1)}]}, db)
    return preview["lines"][0] if preview["lines"] else preview


@router.post("/receiving/scan/commit")
def receiving_scan_commit(payload: dict, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    try:
        return commit_bulk_receipt(
            {
                "idempotency_key": payload.get("idempotency_key"),
                "warehouse": payload.get("warehouse"),
                "source": "scanner",
                "notes": payload.get("notes"),
                "created_by": actor,
                "lines": [{**payload, "quantity": payload.get("quantity", 1)}],
            },
            db,
        )
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/cycle-count/preview")
def cycle_count_scan_preview(payload: dict, db: Session = Depends(get_db)) -> dict:
    item = resolve_scan_item(db, payload.get("scan_input") or payload.get("sku") or payload.get("barcode"))
    if item is None:
        return {"can_commit": False, "errors": ["No matching item was found."]}
    row = find_item_location(db, item.id, payload.get("warehouse"), payload.get("inventory_location"))
    current = row.in_stock if row else Decimal("0")
    counted = to_decimal(payload.get("counted_quantity"))
    variance = counted - current
    errors = []
    if counted < 0:
        errors.append("Counted quantity cannot be negative.")
    if variance != 0 and not (payload.get("reason") or payload.get("notes")):
        errors.append("Reason is required when the counted quantity differs from system stock.")
    return {"can_commit": not errors, "item": item_summary(item), "inventory_item_location_id": row.id if row else None, "system_quantity": float(current), "counted_quantity": float(counted), "variance_quantity": float(variance), "errors": errors}


@router.post("/cycle-count/commit")
def cycle_count_scan_commit(payload: dict, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    preview = cycle_count_scan_preview(payload, db)
    if not preview["can_commit"]:
        raise HTTPException(status_code=400, detail=preview)
    item = db.get(InventoryItem, preview["item"]["id"])
    warehouse = payload.get("warehouse") or item.warehouse or "UNASSIGNED"
    inventory_location = payload.get("inventory_location") or item.inventory_location or item.default_location or "UNASSIGNED"
    count = CycleCount(count_number=f"CC-SCAN-{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}", status="posted", warehouse=warehouse, inventory_location=inventory_location, count_type="scanner", notes=payload.get("reason") or payload.get("notes"), created_by=actor, posted_at=datetime.now(timezone.utc))
    db.add(count)
    db.flush()
    change = cycle_count_location(db, item, warehouse, inventory_location, payload.get("counted_quantity"), reference_number=count.count_number, reference_id=count.id, notes=payload.get("reason") or payload.get("notes"), created_by=actor)
    db.add(CycleCountLine(cycle_count_id=count.id, item_id=item.id, inventory_item_location_id=change.item_location.id, sku=item.sku, barcode=item.barcode, description=item.description, warehouse=warehouse, inventory_location=inventory_location, system_quantity=change.old_location_stock, counted_quantity=change.new_location_stock, variance_quantity=change.new_location_stock - change.old_location_stock, unit_cost=item.unit_cost, variance_value=(change.new_location_stock - change.old_location_stock) * (item.unit_cost or Decimal("0")), notes=payload.get("reason") or payload.get("notes")))
    auto_allocate_processing_orders_fifo(db, source=f"scanner-cycle-count:{count.count_number}")
    db.commit()
    return {"count_id": count.id, "count_number": count.count_number, "status": "posted", "variance_quantity": preview["variance_quantity"]}


@router.post("/transfers/preview")
def transfer_scan_preview(payload: dict, db: Session = Depends(get_db)) -> dict:
    item = resolve_scan_item(db, payload.get("scan_input") or payload.get("sku") or payload.get("barcode"))
    quantity = to_decimal(payload.get("quantity"))
    errors = []
    if item is None:
        errors.append("No matching item was found.")
        return {"can_commit": False, "errors": errors}
    from_row = find_item_location(db, item.id, payload.get("from_warehouse"), payload.get("from_inventory_location"))
    if from_row is None:
        errors.append("Source item-location row was not found.")
    elif from_row.sellable < quantity:
        errors.append("Insufficient sellable stock at the source location.")
    if quantity <= 0:
        errors.append("Quantity must be greater than zero.")
    if not payload.get("to_inventory_location"):
        errors.append("Destination location is required.")
    return {"can_commit": not errors, "item": item_summary(item), "from_inventory_item_location_id": from_row.id if from_row else None, "source_sellable": float(from_row.sellable) if from_row else 0, "quantity": float(quantity), "errors": errors}


@router.post("/transfers/commit")
def transfer_scan_commit(payload: dict, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    preview = transfer_scan_preview(payload, db)
    if not preview["can_commit"]:
        raise HTTPException(status_code=400, detail=preview)
    item = db.get(InventoryItem, preview["item"]["id"])
    from_row = db.get(InventoryItemLocation, preview["from_inventory_item_location_id"])
    try:
        transfer = create_committed_transfer(
            db,
            item=item,
            from_row=from_row,
            to_warehouse=payload.get("to_warehouse") or from_row.warehouse,
            to_inventory_location=payload.get("to_inventory_location"),
            quantity=payload.get("quantity"),
            notes=payload.get("notes"),
            created_by=actor,
            idempotency_key=payload.get("idempotency_key"),
        )
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"transfer_id": transfer.id, "transfer_number": transfer.transfer_number, "status": transfer.status}


@router.post("/adjustments/preview")
def adjustment_scan_preview(payload: dict, db: Session = Depends(get_db)) -> dict:
    item = resolve_scan_item(db, payload.get("scan_input") or payload.get("sku") or payload.get("barcode"))
    errors = []
    if item is None:
        return {"can_commit": False, "errors": ["No matching item was found."]}
    row = find_item_location(db, item.id, payload.get("warehouse"), payload.get("inventory_location"))
    virtual_location = False
    if row is None:
        virtual_location = True
    if not payload.get("reason"):
        errors.append("Adjustment reason is required.")
    current = (row.in_stock if row is not None else Decimal("0")) or Decimal("0")
    if payload.get("new_quantity") not in (None, ""):
        quantity_change = to_decimal(payload.get("new_quantity")) - current
    else:
        quantity_change = to_decimal(payload.get("quantity_change"))
    if current + quantity_change < 0:
        errors.append("Adjustment would make location stock negative.")
    return {"can_commit": not errors, "item": item_summary(item), "inventory_item_location_id": row.id if row else None, "virtual_location": virtual_location, "old_quantity": float(current), "new_quantity": float(current + quantity_change), "quantity_change": float(quantity_change), "errors": errors}


@router.post("/adjustments/commit")
def adjustment_scan_commit(payload: dict, db: Session = Depends(get_db), actor: str = Depends(authenticated_actor)) -> dict:
    preview = adjustment_scan_preview(payload, db)
    if not preview["can_commit"]:
        raise HTTPException(status_code=400, detail=preview)
    item = db.get(InventoryItem, preview["item"]["id"])
    row = db.get(InventoryItemLocation, preview["inventory_item_location_id"]) if preview.get("inventory_item_location_id") else get_or_create_item_location(db, item, payload.get("warehouse") or item.warehouse, payload.get("inventory_location") or item.inventory_location or item.default_location)
    try:
        adjustment = create_committed_adjustment(
            db,
            item=item,
            row=row,
            quantity_change=preview["quantity_change"],
            adjustment_type=payload.get("adjustment_type") or "correction",
            reason=payload.get("reason"),
            notes=payload.get("notes"),
            created_by=actor,
            idempotency_key=payload.get("idempotency_key"),
        )
    except IdempotencyConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    replayed = bool(getattr(adjustment, "_idempotent_replay", False))
    if not replayed:
        auto_allocate_processing_orders_fifo(db, source=f"scanner-adjustment:{adjustment.adjustment_number}")
    db.commit()
    if not replayed:
        settings = get_settings()
        sync_inventory_stock(
            db,
            settings,
            WooCommerceClient(settings),
            item_ids={item.id},
            requested_by=actor,
        )
    return {"adjustment_id": adjustment.id, "adjustment_number": adjustment.adjustment_number, "status": adjustment.status, "quantity_change": preview["quantity_change"]}
