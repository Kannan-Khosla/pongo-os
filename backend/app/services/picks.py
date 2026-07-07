from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.models.inventory import InventoryAuditEvent, InventoryItem
from app.models.orders import Order, OrderItem
from app.models.picks import Pick, PickLine
from app.schemas.picks import (
    PickCommitResponse,
    PickDetail,
    PickLineRead,
    PickPreviewLine,
    PickPreviewOrder,
    PickPreviewResponse,
    PickRead,
    PickRequest,
    PickScanRequest,
    PickScanResponse,
    PickScannerLine,
    PickScannerOrder,
)

PICKABLE_ORDER_STATUSES = {"allocated", "partially_picked", "picked"}


def preview_pick(db: Session, payload: PickRequest) -> PickPreviewResponse:
    return build_preview_response(build_preview_orders(db, payload))


def get_scanner_order(db: Session, order_id: int) -> PickScannerOrder | None:
    order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.inventory_item))).one_or_none()
    if order is None:
        return None
    lines = [scanner_line(line) for line in sorted(order.items, key=lambda row: row.line_number or row.id)]
    return PickScannerOrder(
        order_id=order.id,
        woo_order_id=order.woo_order_id,
        woo_order_number=order.woo_order_number,
        customer_name=order.customer_name,
        customer_email=order.customer_email,
        local_status=order.local_status,
        line_count=len(lines),
        complete_lines=sum(1 for line in lines if line.remaining_to_pick <= 0 and line.allocated_quantity > 0),
        total_allocated_quantity=decimal_to_float(sum((line.quantity_allocated or Decimal("0")) for line in order.items)),
        total_picked_quantity=decimal_to_float(sum((line.quantity_picked or Decimal("0")) for line in order.items)),
        lines=lines,
    )


def preview_scan(db: Session, order_id: int, payload: PickScanRequest) -> PickScanResponse | None:
    line, response = find_scan_line(db, order_id, payload)
    if response is not None:
        return response
    assert line is not None
    preview = preview_pick(db, PickRequest(lines=[{"order_line_id": line.id, "quantity_to_pick": payload.quantity}], allow_partial=True, created_by=payload.created_by, notes=payload.note))
    preview_line = preview.preview_orders[0].lines[0] if preview.preview_orders and preview.preview_orders[0].lines else None
    return PickScanResponse(
        status="valid" if preview_line and not preview_line.errors and preview_line.recommended_pick_quantity > 0 else "rejected",
        matched_line=scanner_line(line),
        proposed_picked_quantity=preview_line.quantity_picked_after if preview_line else None,
        warnings=preview.warnings,
        errors=preview.errors,
    )


def commit_scan(db: Session, order_id: int, payload: PickScanRequest) -> PickScanResponse | None:
    preview = preview_scan(db, order_id, payload)
    if preview is None or preview.status != "valid" or preview.matched_line is None:
        return preview
    commit = commit_pick(db, PickRequest(lines=[{"order_line_id": preview.matched_line.order_line_id, "quantity_to_pick": payload.quantity}], allow_partial=True, created_by=payload.created_by, notes=payload.note))
    refreshed = db.get(OrderItem, preview.matched_line.order_line_id)
    return PickScanResponse(
        status=commit.status,
        matched_line=scanner_line(refreshed) if refreshed else preview.matched_line,
        proposed_picked_quantity=commit.total_quantity_picked,
        warnings=commit.warnings,
        errors=commit.errors,
        commit=commit,
    )


def commit_pick(db: Session, payload: PickRequest) -> PickCommitResponse:
    preview = preview_pick(db, payload)
    blocking_errors = list(preview.errors)
    if not payload.allow_partial:
        for order in preview.preview_orders:
            for line in order.lines:
                if line.pick_status != "picked":
                    blocking_errors.append(f"Order line {line.order_line_id} cannot be fully picked.")
    if blocking_errors:
        return PickCommitResponse(
            status="rejected",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=blocking_errors,
        )

    pickable_preview_lines = [line for order in preview.preview_orders for line in order.lines if line.recommended_pick_quantity > 0 and line.pick_status in {"picked", "partial"}]
    if not pickable_preview_lines:
        return PickCommitResponse(
            status="rejected",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=["No order lines are eligible for picking."],
        )

    now = datetime.now(timezone.utc)
    first_order = preview.preview_orders[0] if len(preview.preview_orders) == 1 else None
    pick = Pick(
        pick_number=next_pick_number(db, now),
        status="posted",
        pick_type="single_order" if len(preview.preview_orders) == 1 else "batch",
        order_id=first_order.order_id if first_order else None,
        woo_order_id=first_order.woo_order_id if first_order else None,
        woo_order_number=first_order.woo_order_number if first_order else None,
        notes=payload.notes,
        created_by=payload.created_by or "system",
        posted_at=now,
    )
    try:
        db.add(pick)
        db.flush()
        audit_count = 0
        picked_lines = 0
        partial_lines = 0
        touched_order_ids: set[int] = set()
        for preview_line in pickable_preview_lines:
            order_line = db.get(OrderItem, preview_line.order_line_id)
            item = db.get(InventoryItem, preview_line.item_id) if preview_line.item_id else None
            if order_line is None or item is None:
                raise ValueError(f"Order line {preview_line.order_line_id} changed before pick commit.")
            quantity_to_pick = to_decimal(preview_line.recommended_pick_quantity)
            allocated = order_line.quantity_allocated or Decimal("0")
            previously_picked = order_line.quantity_picked or Decimal("0")
            remaining = remaining_to_pick(order_line)
            if quantity_to_pick <= 0 or quantity_to_pick > allocated or quantity_to_pick > remaining:
                raise ValueError(f"Order line {order_line.id} is no longer valid for picking.")
            location_row = pick_from_location_audit_only(
                db,
                item,
                quantity_to_pick,
                reference_number=pick.pick_number,
                reference_id=pick.id,
                notes=payload.notes,
                created_by=payload.created_by or "system",
            )
            picked_after = previously_picked + quantity_to_pick
            remaining_after = max(allocated - picked_after, Decimal("0"))
            order_line.quantity_picked = picked_after
            order_line.picked_qty = picked_after
            order_line.status = "picked" if remaining_after == 0 else "partial"
            pick_line = PickLine(
                pick_id=pick.id,
                order_id=order_line.order_id,
                order_line_id=order_line.id,
                item_id=item.id,
                inventory_item_location_id=location_row.id,
                sku=order_line.sku or item.sku,
                barcode=order_line.barcode or item.barcode,
                description=order_line.name or order_line.description or item.description,
                warehouse=location_row.warehouse,
                inventory_location=location_row.inventory_location,
                quantity_ordered=order_line.quantity_ordered or Decimal("0"),
                quantity_allocated=allocated,
                quantity_previously_picked=previously_picked,
                quantity_to_pick=quantity_to_pick,
                quantity_picked_after=picked_after,
                remaining_to_pick=remaining_after,
                status="picked" if remaining_after == 0 else "partial",
                notes=payload.notes,
            )
            db.add(pick_line)
            audit_count += 1
            picked_lines += 1
            partial_lines += 1 if remaining_after > 0 else 0
            touched_order_ids.add(order_line.order_id)

        db.flush()
        for order_id in touched_order_ids:
            order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items))).one()
            update_order_picking_status(order)
        db.commit()
        db.refresh(pick)
        return PickCommitResponse(
            pick_id=pick.id,
            pick_number=pick.pick_number,
            status=pick.status,
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=picked_lines,
            partial_lines=partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=decimal_to_float(sum((line.quantity_to_pick for line in pick.lines), Decimal("0"))),
            created_audit_events=audit_count,
            warnings=preview.warnings,
            errors=[],
        )
    except Exception as exc:
        db.rollback()
        return PickCommitResponse(
            status="error",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            picked_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_picked=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=[str(exc)],
        )


def build_preview_orders(db: Session, payload: PickRequest) -> list[PickPreviewOrder]:
    order_lines = selected_order_lines(db, payload)
    orders_by_id: dict[int, list[OrderItem]] = {}
    for line in order_lines:
        orders_by_id.setdefault(line.order_id, []).append(line)
    preview_orders: list[PickPreviewOrder] = []
    for order_id, lines in orders_by_id.items():
        order = lines[0].order
        preview_lines = [build_preview_line(line, explicit_quantity(payload, line.id)) for line in lines]
        errors = []
        if order.local_status not in PICKABLE_ORDER_STATUSES:
            errors.append(f"Order status {order.local_status or 'unknown'} is not eligible for picking.")
        line_count = len(preview_lines)
        pickable_lines = sum(1 for line in preview_lines if line.pick_status == "picked")
        partial_lines = sum(1 for line in preview_lines if line.pick_status == "partial")
        skipped_lines = sum(1 for line in preview_lines if line.pick_status == "skipped")
        conflict_lines = sum(1 for line in preview_lines if line.pick_status == "conflict")
        recommended_status = "picked" if line_count and pickable_lines == line_count else ("partially_picked" if pickable_lines or partial_lines else order.local_status or "allocated")
        preview_orders.append(
            PickPreviewOrder(
                order_id=order.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                local_status=order.local_status,
                line_count=line_count,
                pickable_lines=pickable_lines,
                partial_lines=partial_lines,
                skipped_lines=skipped_lines,
                conflict_lines=conflict_lines,
                recommended_status=recommended_status,
                warnings=[],
                errors=errors + [error for line in preview_lines for error in line.errors],
                lines=preview_lines,
            )
        )
    return preview_orders


def selected_order_lines(db: Session, payload: PickRequest) -> list[OrderItem]:
    if payload.lines:
        ids = [line.order_line_id for line in payload.lines]
        return list(db.scalars(select(OrderItem).where(OrderItem.id.in_(ids)).options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))).all())
    if payload.order_ids:
        return list(
            db.scalars(
                select(OrderItem)
                .join(Order)
                .where(Order.id.in_(payload.order_ids))
                .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
                .order_by(OrderItem.order_id.asc(), OrderItem.line_number.asc().nullslast(), OrderItem.id.asc())
            ).all()
        )
    return [] 


def find_scan_line(db: Session, order_id: int, payload: PickScanRequest) -> tuple[OrderItem | None, PickScanResponse | None]:
    query = (payload.sku_or_barcode or "").strip().casefold()
    if not query:
        return None, PickScanResponse(status="rejected", errors=["Scan value is required."])
    if payload.quantity <= 0:
        return None, PickScanResponse(status="rejected", errors=["Quantity must be greater than zero."])
    order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items).selectinload(OrderItem.inventory_item))).one_or_none()
    if order is None:
        return None, None
    matches = [
        line
        for line in order.items
        if query in {str(line.sku or "").casefold(), str(line.barcode or "").casefold(), str(line.inventory_item.sku if line.inventory_item else "").casefold(), str(line.inventory_item.barcode if line.inventory_item else "").casefold()}
    ]
    if not matches:
        return None, PickScanResponse(status="not_found", errors=["Scanned SKU/barcode is not in this order."])
    line = matches[0]
    if line.matched_status != "matched":
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), errors=["Matched order line is not linked to a local item."])
    remaining = remaining_to_pick(line)
    if remaining <= 0:
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), warnings=["This item is already fully picked."])
    if to_decimal(payload.quantity) > remaining:
        return line, PickScanResponse(status="rejected", matched_line=scanner_line(line), errors=["Scanned quantity exceeds remaining quantity to pick."])
    return line, None


def scanner_line(line: OrderItem) -> PickScannerLine:
    item = line.inventory_item
    allocated = line.quantity_allocated or Decimal("0")
    picked = line.quantity_picked or Decimal("0")
    remaining = remaining_to_pick(line)
    item_location_id = None
    warehouse = item.warehouse if item else None
    inventory_location = item.inventory_location if item else None
    warnings = []
    if line.matched_status != "matched":
        warnings.append(f"Line match status is {line.matched_status or 'unknown'}.")
    if allocated <= 0:
        warnings.append("Line has no allocated quantity.")
    if item is not None and remaining > 0:
        try:
            db = object_session(line)
            if db is not None:
                location_row = choose_allocated_location(db, item, remaining)
                item_location_id = location_row.id
                warehouse = location_row.warehouse
                inventory_location = location_row.inventory_location
        except Exception as exc:
            warnings.append(str(exc))
    return PickScannerLine(
        order_line_id=line.id,
        item_id=line.inventory_item_id,
        inventory_item_location_id=item_location_id,
        sku=line.sku or (item.sku if item else None),
        barcode=line.barcode or (item.barcode if item else None),
        description=line.name or line.description or (item.description if item else None),
        ordered_quantity=decimal_to_float(line.quantity_ordered),
        allocated_quantity=decimal_to_float(allocated),
        picked_quantity=decimal_to_float(picked),
        remaining_to_pick=decimal_to_float(remaining),
        warehouse=warehouse,
        inventory_location=inventory_location,
        status="picked" if remaining <= 0 and allocated > 0 else ("partial" if picked > 0 else "pending"),
        warnings=warnings,
    )


def explicit_quantity(payload: PickRequest, order_line_id: int) -> Decimal | None:
    for line in payload.lines:
        if line.order_line_id == order_line_id:
            return to_decimal(line.quantity_to_pick)
    return None


def build_preview_line(line: OrderItem, requested_quantity: Decimal | None = None) -> PickPreviewLine:
    warnings: list[str] = []
    errors: list[str] = []
    item = line.inventory_item
    ordered = line.quantity_ordered or Decimal("0")
    allocated = line.quantity_allocated or Decimal("0")
    previously_picked = line.quantity_picked or Decimal("0")
    remaining = max(allocated - previously_picked, Decimal("0"))
    recommended = Decimal("0")
    status = "skipped"
    item_location_id = None
    warehouse = item.warehouse if item else None
    inventory_location = item.inventory_location if item else None
    if line.matched_status != "matched":
        status = "conflict" if line.matched_status == "conflict" else "skipped"
        errors.append(f"Order line matched status is {line.matched_status or 'unknown'}.")
    elif line.order.local_status not in PICKABLE_ORDER_STATUSES:
        errors.append(f"Order status {line.order.local_status or 'unknown'} is not eligible.")
    elif item is None:
        errors.append("Order line has no matched local item.")
    elif allocated <= 0:
        warnings.append("Order line has no allocated quantity to pick.")
    elif previously_picked > allocated:
        status = "error"
        errors.append("Order line picked quantity exceeds allocated quantity.")
    elif remaining <= 0:
        warnings.append("Order line is already fully picked.")
    else:
        try:
            db = object_session(line)
            if db is None:
                raise ValueError("Order line is not attached to a database session.")
            location_row = choose_allocated_location(db, item, requested_quantity or remaining)
            item_location_id = location_row.id
            warehouse = location_row.warehouse
            inventory_location = location_row.inventory_location
        except Exception as exc:
            errors.append(str(exc))
        recommended = Decimal("0") if errors else remaining
        if requested_quantity is not None and not errors:
            if requested_quantity <= 0:
                errors.append("Requested pick quantity must be greater than zero.")
                recommended = Decimal("0")
            elif requested_quantity > allocated:
                errors.append("Requested pick quantity exceeds allocated quantity.")
                recommended = Decimal("0")
            elif requested_quantity > remaining:
                errors.append("Requested pick quantity exceeds remaining quantity to pick.")
                recommended = Decimal("0")
            else:
                recommended = requested_quantity
        status = "picked" if recommended == remaining and recommended > 0 else ("partial" if recommended > 0 else status)
    picked_after = previously_picked + recommended
    remaining_after = max(allocated - picked_after, Decimal("0"))
    return PickPreviewLine(
        order_id=line.order_id,
        order_line_id=line.id,
        item_id=item.id if item else None,
        inventory_item_location_id=item_location_id,
        sku=line.sku or (item.sku if item else None),
        barcode=line.barcode or (item.barcode if item else None),
        description=line.name or line.description or (item.description if item else None),
        warehouse=warehouse,
        inventory_location=inventory_location,
        quantity_ordered=decimal_to_float(ordered),
        quantity_allocated=decimal_to_float(allocated),
        quantity_previously_picked=decimal_to_float(previously_picked),
        remaining_to_pick=decimal_to_float(remaining),
        recommended_pick_quantity=decimal_to_float(recommended),
        quantity_picked_after=decimal_to_float(picked_after),
        pick_status=status,
        warnings=warnings,
        errors=errors,
    )


def build_preview_response(orders: list[PickPreviewOrder]) -> PickPreviewResponse:
    lines = [line for order in orders for line in order.lines]
    return PickPreviewResponse(
        total_orders=len(orders),
        total_lines=len(lines),
        pickable_lines=sum(1 for line in lines if line.pick_status == "picked"),
        partial_lines=sum(1 for line in lines if line.pick_status == "partial"),
        skipped_lines=sum(1 for line in lines if line.pick_status == "skipped"),
        conflict_lines=sum(1 for line in lines if line.pick_status == "conflict"),
        total_quantity_to_pick=decimal_to_float(sum((to_decimal(line.recommended_pick_quantity) for line in lines), Decimal("0"))),
        warnings=[warning for order in orders for warning in order.warnings] + [warning for line in lines for warning in line.warnings],
        errors=[error for order in orders for error in order.errors] + [error for line in lines for error in line.errors],
        preview_orders=orders,
    )


def update_order_picking_status(order: Order) -> None:
    lines = list(order.items)
    matched_allocated_lines = [line for line in lines if line.matched_status == "matched" and (line.quantity_allocated or Decimal("0")) > 0]
    blocked = any(line.matched_status in {"unmatched", "conflict"} for line in lines)
    any_picked = any((line.quantity_picked or Decimal("0")) > 0 for line in matched_allocated_lines)
    all_picked = bool(matched_allocated_lines) and all((line.quantity_picked or Decimal("0")) >= (line.quantity_allocated or Decimal("0")) for line in matched_allocated_lines)
    if all_picked and not blocked:
        order.local_status = "picked"
    elif any_picked:
        order.local_status = "partially_picked"
    order.allocation_status = order.local_status


def list_picks(
    db: Session,
    status: str | None = None,
    pick_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
):
    statement = select(Pick).options(selectinload(Pick.lines)).order_by(Pick.created_at.desc(), Pick.id.desc())
    if status:
        statement = statement.where(Pick.status == status)
    if pick_type:
        statement = statement.where(Pick.pick_type == pick_type)
    if order_id is not None:
        statement = statement.where(Pick.order_id == order_id)
    if woo_order_id is not None:
        statement = statement.where(Pick.woo_order_id == woo_order_id)
    if woo_order_number:
        statement = statement.where(Pick.woo_order_number == woo_order_number)
    if date_from:
        statement = statement.where(Pick.created_at >= date_from)
    if date_to:
        statement = statement.where(Pick.created_at <= date_to)
    if created_by:
        statement = statement.where(Pick.created_by == created_by)
    return list(db.scalars(statement).all())


def get_pick_detail(db: Session, pick_id: int) -> PickDetail | None:
    pick = db.scalars(select(Pick).where(Pick.id == pick_id).options(selectinload(Pick.lines))).one_or_none()
    if pick is None:
        return None
    audit_ids = list(db.scalars(select(InventoryAuditEvent.id).where(InventoryAuditEvent.reference_type == "pick", InventoryAuditEvent.reference_id == pick.id)).all())
    base = pick_to_read(pick).model_dump()
    base["notes"] = pick.notes
    base["lines"] = [pick_line_to_read(line) for line in sorted(pick.lines, key=lambda row: row.id)]
    base["audit_event_ids"] = audit_ids
    return PickDetail.model_validate(base)


def export_pick_csv(db: Session, pick_id: int) -> str | None:
    detail = get_pick_detail(db, pick_id)
    if detail is None:
        return None
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Pick Number",
            "Status",
            "Created At",
            "Posted At",
            "Woo Order Number",
            "Order ID",
            "SKU",
            "Barcode",
            "Description",
            "Warehouse",
            "Inventory Location",
            "Quantity Ordered",
            "Quantity Allocated",
            "Previously Picked",
            "Quantity Picked",
            "Picked After",
            "Remaining To Pick",
            "Line Status",
            "Notes",
        ]
    )
    for line in detail.lines:
        writer.writerow(
            [
                detail.pick_number,
                detail.status,
                detail.created_at.isoformat() if detail.created_at else "",
                detail.posted_at.isoformat() if detail.posted_at else "",
                detail.woo_order_number or "",
                line.order_id,
                line.sku or "",
                line.barcode or "",
                line.description or "",
                line.warehouse or "",
                line.inventory_location or "",
                line.quantity_ordered,
                line.quantity_allocated,
                line.quantity_previously_picked,
                line.quantity_to_pick,
                line.quantity_picked_after,
                line.remaining_to_pick,
                line.status,
                line.notes or "",
            ]
        )
    return output.getvalue()


def pick_to_read(pick: Pick) -> PickRead:
    return PickRead(
        id=pick.id,
        pick_number=pick.pick_number,
        status=pick.status,
        pick_type=pick.pick_type,
        order_id=pick.order_id,
        woo_order_id=pick.woo_order_id,
        woo_order_number=pick.woo_order_number,
        total_lines=len(pick.lines),
        total_quantity_picked=decimal_to_float(sum((line.quantity_to_pick for line in pick.lines), Decimal("0"))),
        created_by=pick.created_by,
        created_at=pick.created_at,
        posted_at=pick.posted_at,
    )


def pick_line_to_read(line: PickLine) -> PickLineRead:
    return PickLineRead(
        id=line.id,
        order_id=line.order_id,
        order_line_id=line.order_line_id,
        item_id=line.item_id,
        inventory_item_location_id=line.inventory_item_location_id,
        sku=line.sku,
        barcode=line.barcode,
        description=line.description,
        warehouse=line.warehouse,
        inventory_location=line.inventory_location,
        quantity_ordered=decimal_to_float(line.quantity_ordered),
        quantity_allocated=decimal_to_float(line.quantity_allocated),
        quantity_previously_picked=decimal_to_float(line.quantity_previously_picked),
        quantity_to_pick=decimal_to_float(line.quantity_to_pick),
        quantity_picked_after=decimal_to_float(line.quantity_picked_after),
        remaining_to_pick=decimal_to_float(line.remaining_to_pick),
        status=line.status,
        notes=line.notes,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def next_pick_number(db: Session, now: datetime) -> str:
    prefix = f"PK-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(Pick.id)).where(Pick.pick_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def remaining_to_pick(line: OrderItem) -> Decimal:
    return max((line.quantity_allocated or Decimal("0")) - (line.quantity_picked or Decimal("0")), Decimal("0"))


def current_sellable(item: InventoryItem) -> Decimal:
    return (item.in_stock or Decimal("0")) - (item.allocated or Decimal("0"))


def to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def decimal_to_float(value: Decimal | int | float | None) -> float:
    return float(value or 0)
from app.services.location_inventory import choose_allocated_location, pick_from_location_audit_only
