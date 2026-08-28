from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from io import StringIO
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.inventory import InventoryItem, InventoryItemLocation
from app.models.receipts import Receipt, ReceiptItem
from app.services.business_dashboard import admin_today
from app.services.calculations import calculate_inventory_value
from app.services.item_identifiers import barcode_scan_candidates
from app.services.location_inventory import find_item_location, get_or_create_item_location, lock_inventory_stock, receive_to_location, receiving_unit_cost, to_decimal
from app.services.order_workflow import auto_allocate_processing_orders_fifo
from app.services.receiving import receipt_to_detail
from app.services.stock_mutation_guard import begin_stock_mutation, complete_stock_mutation


def resolve_receiving_item(db: Session, line: dict[str, Any]) -> tuple[InventoryItem | None, str | None]:
    resolved: dict[int, InventoryItem] = {}
    item_id = line.get("item_id")
    if item_id:
        item = db.get(InventoryItem, item_id)
        if item is None:
            return None, "Item ID does not match an existing item; receiving was blocked."
        resolved[item.id] = item
    candidates = [
        ("sku", line.get("sku")),
        ("barcode", line.get("barcode")),
        ("scan", line.get("scan_input")),
    ]
    for candidate_type, value in candidates:
        if not value:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        if candidate_type == "sku":
            predicate = InventoryItem.sku == normalized
        elif candidate_type == "barcode":
            predicate = InventoryItem.barcode.in_(barcode_scan_candidates(normalized))
        else:
            predicate = or_(
                InventoryItem.sku == normalized,
                InventoryItem.barcode.in_(barcode_scan_candidates(normalized)),
            )
        matches = list(db.scalars(
            select(InventoryItem).where(predicate)
        ).all())
        if len(matches) > 1:
            return None, "SKU or Barcode matches multiple existing items; receiving was blocked."
        if matches:
            resolved[matches[0].id] = matches[0]
    if len(resolved) > 1:
        return None, "Item ID, SKU, Barcode, or scan input identify different items; receiving was blocked."
    return (next(iter(resolved.values())), None) if resolved else (None, None)


def preview_bulk_receipt(payload: dict[str, Any], db: Session) -> dict[str, Any]:
    lines = payload.get("lines") or []
    preview_lines = []
    total_quantity = Decimal("0")
    total_cost = Decimal("0")
    default_warehouse = (payload.get("warehouse") or "Main Warehouse").strip() or "Main Warehouse"
    for index, raw_line in enumerate(lines, start=1):
        line = raw_line or {}
        item, match_error = resolve_receiving_item(db, line)
        quantity = to_decimal(line.get("quantity", line.get("quantity_received")))
        unit_cost = receiving_unit_cost(item, line.get("unit_cost"))
        warehouse = (line.get("warehouse") or default_warehouse).strip() or default_warehouse
        inventory_location = (line.get("inventory_location") or "").strip()
        errors = []
        warnings = []
        if item is None:
            errors.append(match_error or "No matching item was found.")
        if quantity <= 0:
            errors.append("Quantity must be greater than zero.")
        if item is not None and unit_cost <= 0:
            errors.append("Unit Cost is missing. Enter the current cost before receiving this item.")
        if not inventory_location:
            errors.append("Inventory Location is required.")
        if item is not None and line.get("unit_cost") not in (None, "") and unit_cost != to_decimal(item.unit_cost):
            warnings.append("This cost will become the item's new default Unit Cost.")
        item_location = find_item_location(db, item.id, warehouse, inventory_location) if item is not None and inventory_location else None
        old_location_stock = item_location.in_stock if item_location is not None else Decimal("0")
        old_item_stock = item.in_stock if item is not None else Decimal("0")
        line_cost = quantity * unit_cost
        if not errors:
            total_quantity += quantity
            total_cost += line_cost
        preview_lines.append(
            {
                "line_number": index,
                "status": "valid" if not errors else "invalid",
                "item": {
                    "id": item.id,
                    "sku": item.sku,
                    "barcode": item.barcode,
                    "description": item.description,
                    "brand": item.brand,
                    "category": item.category,
                    "image_url": item.image_url,
                    "unit_cost": float(to_decimal(item.unit_cost)),
                }
                if item
                else None,
                "scan_input": line.get("scan_input"),
                "warehouse": warehouse,
                "inventory_location": inventory_location,
                "inventory_item_location_id": item_location.id if item_location else None,
                "quantity": float(quantity),
                "unit_cost": float(unit_cost),
                "line_cost": float(line_cost),
                "old_location_stock": float(old_location_stock),
                "new_location_stock": float(old_location_stock + quantity) if item else 0,
                "old_item_stock": float(old_item_stock),
                "new_item_stock": float(old_item_stock + quantity) if item else 0,
                "warnings": warnings,
                "errors": errors,
            }
        )
    error_count = sum(1 for line in preview_lines if line["status"] == "invalid")
    return {
        "can_commit": bool(lines) and error_count == 0,
        "line_count": len(lines),
        "valid_line_count": len(lines) - error_count,
        "error_line_count": error_count,
        "total_quantity": float(total_quantity),
        "total_cost": float(total_cost),
        "lines": preview_lines,
    }


def next_bulk_receipt_number(db: Session, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    prefix = f"RCPT-{now:%Y}-"
    count = db.scalar(select(func.count(Receipt.id)).where(Receipt.receipt_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:05d}"


def commit_bulk_receipt(payload: dict[str, Any], db: Session) -> dict[str, Any]:
    mutation, replay = begin_stock_mutation(db, "bulk_receipt", payload.get("idempotency_key"), payload)
    if replay is not None:
        return replay

    preview = preview_bulk_receipt(payload, db)
    commit_valid_only = bool(payload.get("commit_valid_lines_only"))
    if preview["error_line_count"] and not commit_valid_only:
        raise HTTPException(status_code=400, detail=preview)
    valid_line_numbers = {line["line_number"] for line in preview["lines"] if line["status"] == "valid"}
    if not valid_line_numbers:
        raise HTTPException(status_code=400, detail=preview)
    item_ids = {
        item.id
        for index, raw_line in enumerate(payload.get("lines") or [], start=1)
        if index in valid_line_numbers
        and (item := resolve_receiving_item(db, raw_line or {})[0]) is not None
    }
    lock_inventory_stock(db, item_ids)
    preview = preview_bulk_receipt(payload, db)
    valid_line_numbers = {line["line_number"] for line in preview["lines"] if line["status"] == "valid"}
    now = datetime.now(timezone.utc)
    default_warehouse = (payload.get("warehouse") or "Main Warehouse").strip() or "Main Warehouse"
    receipt = Receipt(
        receipt_number=next_bulk_receipt_number(db, now),
        receipt_type="bulk",
        status="committed",
        source=payload.get("source") or "manual",
        warehouse=default_warehouse,
        reference_number=payload.get("reference_number"),
        notes=payload.get("notes"),
        created_by=payload.get("created_by") or "system",
        received_by=payload.get("created_by") or "system",
        received_date=date.fromisoformat(payload["receipt_date"]) if payload.get("receipt_date") else admin_today(now),
        received_at=now,
        committed_at=now,
    )
    db.add(receipt)
    db.flush()
    total_quantity = Decimal("0")
    total_cost = Decimal("0")
    movement_count = 0
    for index, raw_line in enumerate(payload.get("lines") or [], start=1):
        if index not in valid_line_numbers:
            continue
        line = raw_line or {}
        item, match_error = resolve_receiving_item(db, line)
        if item is None:
            raise ValueError(match_error or "No matching item was found.")
        quantity = to_decimal(line.get("quantity", line.get("quantity_received")))
        unit_cost = receiving_unit_cost(item, line.get("unit_cost"))
        warehouse = (line.get("warehouse") or default_warehouse).strip() or default_warehouse
        inventory_location = (line.get("inventory_location") or "").strip()
        get_or_create_item_location(db, item, warehouse, inventory_location)
        change = receive_to_location(
            db,
            item,
            warehouse,
            inventory_location,
            quantity,
            unit_cost=unit_cost,
            reference_number=receipt.receipt_number,
            reference_type="bulk_receipt",
            reference_id=receipt.id,
            notes=line.get("notes"),
            created_by=payload.get("created_by") or "system",
        )
        line_cost = calculate_inventory_value(quantity, unit_cost)
        receipt_item = ReceiptItem(
            receipt_id=receipt.id,
            inventory_item_id=item.id,
            inventory_location_id=change.item_location.location_id,
            inventory_item_location_id=change.item_location.id,
            line_status="committed",
            scan_input=line.get("scan_input"),
            sku=item.sku,
            category=item.category,
            description=item.description,
            quantity=quantity,
            quantity_received=quantity,
            uom=item.unit_of_measurement,
            unit_cost=unit_cost,
            unit_cost_total=line_cost,
            sales_price=to_decimal(line.get("sales_price")) if line.get("sales_price") not in (None, "") else item.sales_price,
            weight=to_decimal(line.get("weight")) if line.get("weight") not in (None, "") else item.weight,
            brand=item.brand,
            client=item.client,
            lot_number=line.get("lot_number"),
            expiration_date=date.fromisoformat(line["expiration_date"]) if line.get("expiration_date") else None,
            pkg_number=line.get("pkg_number"),
            item_number=line.get("item_number"),
            pallet_number=line.get("pallet_number"),
            warehouse=warehouse,
            inventory_location_name=inventory_location,
            default_location=item.default_location,
            received_date=receipt.received_date,
            po_or_receipt_number=receipt.receipt_number,
            name=item.description,
            notes=line.get("notes"),
        )
        db.add(receipt_item)
        total_quantity += quantity
        total_cost += line_cost
        movement_count += 1
    auto_allocate_processing_orders_fifo(db, source=f"bulk-receipt:{receipt.receipt_number}")
    db.flush()
    receipt = db.scalars(select(Receipt).where(Receipt.id == receipt.id).options(selectinload(Receipt.items).selectinload(ReceiptItem.inventory_item))).one()
    detail = receipt_to_detail(receipt).model_dump(mode="json")
    detail["total_inventory_value"] = float(total_cost)
    detail["created_movements"] = movement_count
    detail["total_quantity_received"] = float(total_quantity)
    complete_stock_mutation(mutation, detail)
    db.commit()
    return detail


def export_receipt_csv(receipt: Receipt) -> str:
    buffer = StringIO()
    fieldnames = ["receipt_number", "receipt_type", "status", "sku", "barcode", "description", "warehouse", "inventory_location", "quantity", "unit_cost", "total_cost", "lot_number", "expiration_date", "notes"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for line in receipt.items:
        writer.writerow(
            {
                "receipt_number": receipt.receipt_number,
                "receipt_type": receipt.receipt_type,
                "status": receipt.status,
                "sku": line.sku or "",
                "barcode": line.inventory_item.barcode if line.inventory_item else "",
                "description": line.description or "",
                "warehouse": line.warehouse or "",
                "inventory_location": line.inventory_location_name or "",
                "quantity": line.quantity_received or line.quantity or 0,
                "unit_cost": line.unit_cost or 0,
                "total_cost": line.unit_cost_total or 0,
                "lot_number": line.lot_number or "",
                "expiration_date": line.expiration_date.isoformat() if line.expiration_date else "",
                "notes": line.notes or "",
            }
        )
    return buffer.getvalue()
