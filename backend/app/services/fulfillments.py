from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.models.fulfillments import Fulfillment, FulfillmentLine
from app.models.inventory import InventoryAuditEvent, InventoryItem, StockMovement
from app.models.orders import Order, OrderItem
from app.models.picks import PickLine
from app.schemas.fulfillments import (
    FulfillmentCommitResponse,
    FulfillmentDetail,
    FulfillmentLineRead,
    FulfillmentPreviewLine,
    FulfillmentPreviewOrder,
    FulfillmentPreviewResponse,
    FulfillmentRead,
    FulfillmentRequest,
)
from app.services.location_inventory import choose_allocated_location
from app.services.order_workflow import actionable_order_line_clause, add_audit_event, first_item_location, operational_line_identity

FULFILLABLE_ORDER_STATUSES = {"picked", "partially_picked", "partially_fulfilled"}


def preview_fulfillment(db: Session, payload: FulfillmentRequest) -> FulfillmentPreviewResponse:
    return build_preview_response(build_preview_orders(db, payload))


def commit_fulfillment(db: Session, payload: FulfillmentRequest) -> FulfillmentCommitResponse:
    preview = preview_fulfillment(db, payload)
    blocking_errors = list(preview.errors)
    if not payload.allow_partial:
        for order in preview.preview_orders:
            for line in order.lines:
                if line.fulfillment_status != "fulfilled":
                    blocking_errors.append(f"Order line {line.order_line_id} cannot be fully fulfilled.")
    if blocking_errors:
        return rejected_response(preview, blocking_errors)

    fulfillable_preview_lines = [line for order in preview.preview_orders for line in order.lines if line.recommended_fulfill_quantity > 0 and line.fulfillment_status in {"fulfilled", "partial"}]
    if not fulfillable_preview_lines:
        return rejected_response(preview, ["No order lines are eligible for fulfillment."])

    now = datetime.now(timezone.utc)
    first_order = preview.preview_orders[0] if len(preview.preview_orders) == 1 else None
    fulfillment = Fulfillment(
        fulfillment_number=next_fulfillment_number(db, now),
        status="posted",
        fulfillment_type="single_order" if len(preview.preview_orders) == 1 else "batch",
        order_id=first_order.order_id if first_order else None,
        woo_order_id=first_order.woo_order_id if first_order else None,
        woo_order_number=first_order.woo_order_number if first_order else None,
        notes=payload.notes,
        created_by=payload.created_by or "system",
        posted_at=now,
    )
    try:
        db.add(fulfillment)
        db.flush()
        movement_count = 0
        audit_count = 0
        fulfilled_lines = 0
        partial_lines = 0
        touched_order_ids: set[int] = set()
        for preview_line in fulfillable_preview_lines:
            order_line = db.get(OrderItem, preview_line.order_line_id)
            item = db.get(InventoryItem, preview_line.item_id) if preview_line.item_id else None
            if order_line is None or item is None:
                raise ValueError(f"Order line {preview_line.order_line_id} changed before fulfillment commit.")
            quantity_to_fulfill = to_decimal(preview_line.recommended_fulfill_quantity)
            picked = order_line.quantity_picked or Decimal("0")
            allocated = order_line.quantity_allocated or Decimal("0")
            previously_fulfilled = order_line.quantity_fulfilled or Decimal("0")
            remaining = remaining_to_fulfill(order_line)
            in_stock_before = item.in_stock or Decimal("0")
            allocated_before = item.allocated or Decimal("0")
            sellable_before = current_sellable(item)
            already_stock_reduced = picked > 0 and (order_line.quantity_stock_reduced or Decimal("0")) >= picked
            if not already_stock_reduced:
                raise ValueError("Fulfillment no longer reduces stock. Pick the order first or use direct completion without stock reduction.")
            if quantity_to_fulfill <= 0 or quantity_to_fulfill > remaining or quantity_to_fulfill > picked or quantity_to_fulfill > allocated:
                raise ValueError(f"Order line {order_line.id} is no longer valid for fulfillment.")
            location_row = last_pick_location(db, order_line) or first_item_location(db, item)
            in_stock_after = in_stock_before
            allocated_after = allocated_before
            fulfilled_after = previously_fulfilled + quantity_to_fulfill
            remaining_after = max(picked - fulfilled_after, Decimal("0"))
            sellable_after = sellable_before
            order_line.quantity_fulfilled = fulfilled_after
            order_line.fulfilled_qty = fulfilled_after
            order_line.status = "fulfilled" if remaining_after == 0 else "partial"
            fulfillment_line = FulfillmentLine(
                fulfillment_id=fulfillment.id,
                order_id=order_line.order_id,
                order_line_id=order_line.id,
                item_id=item.id,
                inventory_item_location_id=location_row.id if location_row else None,
                sku=operational_line_identity(order_line)[0],
                barcode=operational_line_identity(order_line)[1],
                description=operational_line_identity(order_line)[2],
                warehouse=location_row.warehouse if location_row else item.warehouse,
                inventory_location=location_row.inventory_location if location_row else item.inventory_location,
                quantity_ordered=order_line.quantity_ordered or Decimal("0"),
                quantity_allocated=allocated,
                quantity_picked=picked,
                quantity_previously_fulfilled=previously_fulfilled,
                quantity_to_fulfill=quantity_to_fulfill,
                unit_cost=item.unit_cost,
                quantity_fulfilled_after=fulfilled_after,
                remaining_to_fulfill=remaining_after,
                in_stock_before=in_stock_before,
                allocated_before=allocated_before,
                sellable_before=sellable_before,
                in_stock_after=in_stock_after,
                allocated_after=allocated_after,
                sellable_after=sellable_after,
                status="fulfilled" if remaining_after == 0 else "partial",
                notes=payload.notes,
            )
            db.add(fulfillment_line)
            if location_row is not None:
                add_audit_event(
                    db,
                    item,
                    location_row,
                    "fulfillment_no_stock_reduction",
                    Decimal("0"),
                    previous_in_stock=in_stock_before,
                    new_in_stock=in_stock_after,
                    previous_allocated=allocated_before,
                    new_allocated=allocated_after,
                    previous_sellable=sellable_before,
                    new_sellable=sellable_after,
                    reference_type="fulfillment",
                    reference_id=fulfillment.id,
                    reference_number=fulfillment.fulfillment_number,
                    notes="Stock already reduced during picking.",
                    created_by=payload.created_by or "system",
                )
            audit_count += 1
            fulfilled_lines += 1
            partial_lines += 1 if remaining_after > 0 else 0
            touched_order_ids.add(order_line.order_id)

        db.flush()
        for order_id in touched_order_ids:
            order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items))).one()
            update_order_fulfillment_status(order)
        db.commit()
        db.refresh(fulfillment)
        return FulfillmentCommitResponse(
            fulfillment_id=fulfillment.id,
            fulfillment_number=fulfillment.fulfillment_number,
            status=fulfillment.status,
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            fulfilled_lines=fulfilled_lines,
            partial_lines=partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_fulfilled=decimal_to_float(sum((line.quantity_to_fulfill for line in fulfillment.lines), Decimal("0"))),
            created_stock_movements=movement_count,
            created_audit_events=audit_count,
            warnings=preview.warnings + ["Stock already reduced during picking."],
            errors=[],
        )
    except Exception as exc:
        db.rollback()
        return FulfillmentCommitResponse(
            status="error",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            fulfilled_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_fulfilled=0,
            created_stock_movements=0,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=[str(exc)],
        )


def rejected_response(preview: FulfillmentPreviewResponse, errors: list[str]) -> FulfillmentCommitResponse:
    return FulfillmentCommitResponse(
        status="rejected",
        total_orders=preview.total_orders,
        total_lines=preview.total_lines,
        fulfilled_lines=0,
        partial_lines=preview.partial_lines,
        skipped_lines=preview.skipped_lines,
        total_quantity_fulfilled=0,
        created_stock_movements=0,
        created_audit_events=0,
        warnings=preview.warnings,
        errors=errors,
    )


def build_preview_orders(db: Session, payload: FulfillmentRequest) -> list[FulfillmentPreviewOrder]:
    order_lines = selected_order_lines(db, payload)
    orders_by_id: dict[int, list[OrderItem]] = {}
    for line in order_lines:
        orders_by_id.setdefault(line.order_id, []).append(line)
    preview_orders: list[FulfillmentPreviewOrder] = []
    for order_id, lines in orders_by_id.items():
        order = lines[0].order
        preview_lines = [build_preview_line(line, explicit_quantity(payload, line.id)) for line in lines]
        errors = []
        if order.local_status not in FULFILLABLE_ORDER_STATUSES:
            errors.append(f"Order status {order.local_status or 'unknown'} is not eligible for fulfillment.")
        line_count = len(preview_lines)
        fulfillable_lines = sum(1 for line in preview_lines if line.fulfillment_status == "fulfilled")
        partial_lines = sum(1 for line in preview_lines if line.fulfillment_status == "partial")
        skipped_lines = sum(1 for line in preview_lines if line.fulfillment_status == "skipped")
        conflict_lines = sum(1 for line in preview_lines if line.fulfillment_status == "conflict")
        recommended_status = "fulfilled" if line_count and fulfillable_lines == line_count else ("partially_fulfilled" if fulfillable_lines or partial_lines else order.local_status or "picked")
        preview_orders.append(
            FulfillmentPreviewOrder(
                order_id=order.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                local_status=order.local_status,
                line_count=line_count,
                fulfillable_lines=fulfillable_lines,
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


def selected_order_lines(db: Session, payload: FulfillmentRequest) -> list[OrderItem]:
    if payload.lines:
        ids = [line.order_line_id for line in payload.lines]
        return list(db.scalars(
            select(OrderItem)
            .join(Order)
            .where(OrderItem.id.in_(ids), Order.is_historical_snapshot.is_(False))
            .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
        ).all())
    if payload.order_ids:
        return list(
            db.scalars(
                select(OrderItem)
                .join(Order)
                .where(
                    Order.id.in_(payload.order_ids),
                    Order.is_historical_snapshot.is_(False),
                    actionable_order_line_clause(),
                )
                .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
                .order_by(OrderItem.order_id.asc(), OrderItem.line_number.asc().nullslast(), OrderItem.id.asc())
            ).all()
        )
    return []


def explicit_quantity(payload: FulfillmentRequest, order_line_id: int) -> Decimal | None:
    for line in payload.lines:
        if line.order_line_id == order_line_id:
            return to_decimal(line.quantity_to_fulfill)
    return None


def build_preview_line(line: OrderItem, requested_quantity: Decimal | None = None) -> FulfillmentPreviewLine:
    warnings: list[str] = []
    errors: list[str] = []
    item = line.inventory_item
    ordered = line.quantity_ordered or Decimal("0")
    allocated = line.quantity_allocated or Decimal("0")
    picked = line.quantity_picked or Decimal("0")
    previously_fulfilled = line.quantity_fulfilled or Decimal("0")
    remaining = max(picked - previously_fulfilled, Decimal("0"))
    in_stock = item.in_stock if item else Decimal("0")
    item_allocated = item.allocated if item else Decimal("0")
    sellable = current_sellable(item) if item else Decimal("0")
    item_location_id = None
    warehouse = item.warehouse if item else None
    inventory_location = item.inventory_location if item else None
    recommended = Decimal("0")
    status = "skipped"
    already_stock_reduced = picked > 0 and (line.quantity_stock_reduced or Decimal("0")) >= picked
    if line.matched_status != "matched":
        status = "conflict" if line.matched_status == "conflict" else "skipped"
        errors.append(f"Order line matched status is {line.matched_status or 'unknown'}.")
    elif line.order.local_status not in FULFILLABLE_ORDER_STATUSES:
        errors.append(f"Order status {line.order.local_status or 'unknown'} is not eligible.")
    elif item is None:
        errors.append("Order line has no matched local item.")
    elif picked <= 0:
        warnings.append("Order line has no picked quantity to fulfill.")
    elif previously_fulfilled > picked:
        status = "error"
        errors.append("Order line fulfilled quantity exceeds picked quantity.")
    elif remaining <= 0:
        warnings.append("Order line is already fully fulfilled.")
    elif not already_stock_reduced:
        errors.append("Fulfillment no longer reduces stock. Pick the order first or use direct completion without stock reduction.")
    elif already_stock_reduced:
        db = object_session(line)
        location_row = last_pick_location(db, line) if db is not None else None
        if location_row is not None:
            item_location_id = location_row.id
            warehouse = location_row.warehouse
            inventory_location = location_row.inventory_location
        recommended = remaining
        if requested_quantity is not None:
            if requested_quantity <= 0:
                errors.append("Requested fulfillment quantity must be greater than zero.")
                recommended = Decimal("0")
            elif requested_quantity > remaining:
                errors.append("Requested fulfillment quantity exceeds remaining quantity to fulfill.")
                recommended = Decimal("0")
            else:
                recommended = requested_quantity
        status = "fulfilled" if recommended == remaining and recommended > 0 else ("partial" if recommended > 0 else "skipped")
        warnings.append("Stock already reduced during picking; fulfillment will not reduce stock again.")
    elif item_allocated <= 0:
        errors.append("Fulfillment no longer reduces stock. Pick the order first or use direct completion without stock reduction.")
    elif in_stock <= 0:
        errors.append("Fulfillment no longer reduces stock. Pick the order first or use direct completion without stock reduction.")
    else:
        try:
            db = object_session(line)
            if db is None:
                raise ValueError("Order line is not attached to a database session.")
            location_row = choose_allocated_location(db, item, requested_quantity or min(remaining, item_allocated, in_stock))
            item_location_id = location_row.id
            warehouse = location_row.warehouse
            inventory_location = location_row.inventory_location
        except Exception as exc:
            errors.append(str(exc))
        recommended = min(remaining, item_allocated, in_stock)
        if requested_quantity is not None and not errors:
            if requested_quantity <= 0:
                errors.append("Requested fulfillment quantity must be greater than zero.")
                recommended = Decimal("0")
            elif requested_quantity > remaining:
                errors.append("Requested fulfillment quantity exceeds remaining quantity to fulfill.")
                recommended = Decimal("0")
            elif requested_quantity > allocated:
                errors.append("Requested fulfillment quantity exceeds allocated quantity.")
                recommended = Decimal("0")
            elif requested_quantity > item_allocated:
                errors.append("Requested fulfillment quantity exceeds current item Allocated.")
                recommended = Decimal("0")
            elif requested_quantity > in_stock:
                errors.append("Requested fulfillment quantity exceeds current item In Stock.")
                recommended = Decimal("0")
            else:
                recommended = requested_quantity
        if errors:
            recommended = Decimal("0")
        status = "fulfilled" if recommended == remaining and recommended > 0 else ("partial" if recommended > 0 else status)
        if recommended < remaining and recommended > 0:
            warnings.append("Only part of the picked quantity can currently be fulfilled.")
    return FulfillmentPreviewLine(
        order_id=line.order_id,
        order_line_id=line.id,
        item_id=item.id if item else None,
        inventory_item_location_id=item_location_id,
        sku=operational_line_identity(line)[0],
        barcode=operational_line_identity(line)[1],
        description=operational_line_identity(line)[2],
        quantity_ordered=decimal_to_float(ordered),
        quantity_allocated=decimal_to_float(allocated),
        quantity_picked=decimal_to_float(picked),
        quantity_previously_fulfilled=decimal_to_float(previously_fulfilled),
        remaining_to_fulfill=decimal_to_float(remaining),
        recommended_fulfill_quantity=decimal_to_float(recommended),
        fulfillment_status=status,
        in_stock=decimal_to_float(in_stock),
        allocated=decimal_to_float(item_allocated),
        sellable=decimal_to_float(sellable),
        warehouse=warehouse,
        inventory_location=inventory_location,
        warnings=warnings,
        errors=errors,
    )


def build_preview_response(orders: list[FulfillmentPreviewOrder]) -> FulfillmentPreviewResponse:
    lines = [line for order in orders for line in order.lines]
    return FulfillmentPreviewResponse(
        total_orders=len(orders),
        total_lines=len(lines),
        fulfillable_lines=sum(1 for line in lines if line.fulfillment_status == "fulfilled"),
        partial_lines=sum(1 for line in lines if line.fulfillment_status == "partial"),
        skipped_lines=sum(1 for line in lines if line.fulfillment_status == "skipped"),
        conflict_lines=sum(1 for line in lines if line.fulfillment_status == "conflict"),
        total_quantity_to_fulfill=decimal_to_float(sum((to_decimal(line.recommended_fulfill_quantity) for line in lines), Decimal("0"))),
        warnings=[warning for order in orders for warning in order.warnings] + [warning for line in lines for warning in line.warnings],
        errors=[error for order in orders for error in order.errors] + [error for line in lines for error in line.errors],
        preview_orders=orders,
    )


def update_order_fulfillment_status(order: Order) -> None:
    lines = list(order.items)
    matched_picked_lines = [line for line in lines if line.matched_status == "matched" and (line.quantity_picked or Decimal("0")) > 0]
    blocked = any(line.matched_status in {"unmatched", "conflict"} for line in lines)
    any_fulfilled = any((line.quantity_fulfilled or Decimal("0")) > 0 for line in matched_picked_lines)
    all_fulfilled = bool(matched_picked_lines) and all((line.quantity_fulfilled or Decimal("0")) >= (line.quantity_picked or Decimal("0")) for line in matched_picked_lines)
    if all_fulfilled and not blocked:
        order.local_status = "fulfilled"
        order.completion_status = "completed"
        order.completed_at = order.completed_at or datetime.now(timezone.utc)
        order.closed_at = order.closed_at or order.completed_at
    elif any_fulfilled:
        order.local_status = "partially_fulfilled"
        order.completion_status = "completed"
        order.completed_at = order.completed_at or datetime.now(timezone.utc)
        order.closed_at = order.closed_at or order.completed_at
    order.allocation_status = order.local_status


def list_fulfillments(
    db: Session,
    status: str | None = None,
    fulfillment_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
):
    statement = build_fulfillments_statement(
        status=status,
        fulfillment_type=fulfillment_type,
        order_id=order_id,
        woo_order_id=woo_order_id,
        woo_order_number=woo_order_number,
        date_from=date_from,
        date_to=date_to,
        created_by=created_by,
    )
    return list(db.scalars(statement.options(selectinload(Fulfillment.lines)).order_by(Fulfillment.created_at.desc(), Fulfillment.id.desc())).all())


def list_fulfillments_page(
    db: Session,
    *,
    page: int,
    page_size: int,
    clamp_page: bool = True,
    status: str | None = None,
    fulfillment_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
) -> tuple[list[Fulfillment], int, int, int]:
    statement = build_fulfillments_statement(
        status=status,
        fulfillment_type=fulfillment_type,
        order_id=order_id,
        woo_order_id=woo_order_id,
        woo_order_number=woo_order_number,
        date_from=date_from,
        date_to=date_to,
        created_by=created_by,
    )
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    total_pages = (total + page_size - 1) // page_size
    effective_page = min(page, max(total_pages, 1)) if clamp_page else page
    rows = list(
        db.scalars(
            statement
            .options(selectinload(Fulfillment.lines))
            .order_by(Fulfillment.created_at.desc(), Fulfillment.id.desc())
            .offset((effective_page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total, effective_page, total_pages


def build_fulfillments_statement(
    *,
    status: str | None = None,
    fulfillment_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
):
    statement = select(Fulfillment)
    if status:
        statement = statement.where(Fulfillment.status == status)
    if fulfillment_type:
        statement = statement.where(Fulfillment.fulfillment_type == fulfillment_type)
    if order_id is not None:
        statement = statement.where(Fulfillment.order_id == order_id)
    if woo_order_id is not None:
        statement = statement.where(Fulfillment.woo_order_id == woo_order_id)
    if woo_order_number:
        statement = statement.where(Fulfillment.woo_order_number == woo_order_number)
    if date_from:
        statement = statement.where(Fulfillment.created_at >= date_from)
    if date_to:
        statement = statement.where(Fulfillment.created_at <= date_to)
    if created_by:
        statement = statement.where(Fulfillment.created_by == created_by)
    return statement


def get_fulfillment_detail(db: Session, fulfillment_id: int) -> FulfillmentDetail | None:
    fulfillment = db.scalars(select(Fulfillment).where(Fulfillment.id == fulfillment_id).options(selectinload(Fulfillment.lines))).one_or_none()
    if fulfillment is None:
        return None
    movement_ids = list(db.scalars(select(StockMovement.id).where(StockMovement.reference_type == "fulfillment", StockMovement.reference_id == fulfillment.id)).all())
    audit_ids = list(db.scalars(select(InventoryAuditEvent.id).where(InventoryAuditEvent.reference_type == "fulfillment", InventoryAuditEvent.reference_id == fulfillment.id)).all())
    base = fulfillment_to_read(fulfillment).model_dump()
    base["notes"] = fulfillment.notes
    base["lines"] = [fulfillment_line_to_read(line) for line in sorted(fulfillment.lines, key=lambda row: row.id)]
    base["stock_movement_ids"] = movement_ids
    base["audit_event_ids"] = audit_ids
    return FulfillmentDetail.model_validate(base)


def export_fulfillment_csv(db: Session, fulfillment_id: int) -> str | None:
    detail = get_fulfillment_detail(db, fulfillment_id)
    if detail is None:
        return None
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Fulfillment Number",
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
            "Quantity Picked",
            "Previously Fulfilled",
            "Quantity Fulfilled",
            "Fulfilled After",
            "Remaining To Fulfill",
            "In Stock Before",
            "Allocated Before",
            "Sellable Before",
            "In Stock After",
            "Allocated After",
            "Sellable After",
            "Line Status",
            "Notes",
        ]
    )
    for line in detail.lines:
        writer.writerow(
            [
                detail.fulfillment_number,
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
                line.quantity_picked,
                line.quantity_previously_fulfilled,
                line.quantity_to_fulfill,
                line.quantity_fulfilled_after,
                line.remaining_to_fulfill,
                line.in_stock_before,
                line.allocated_before,
                line.sellable_before,
                line.in_stock_after,
                line.allocated_after,
                line.sellable_after,
                line.status,
                line.notes or "",
            ]
        )
    return output.getvalue()


def fulfillment_to_read(fulfillment: Fulfillment) -> FulfillmentRead:
    return FulfillmentRead(
        id=fulfillment.id,
        fulfillment_number=fulfillment.fulfillment_number,
        status=fulfillment.status,
        fulfillment_type=fulfillment.fulfillment_type,
        order_id=fulfillment.order_id,
        woo_order_id=fulfillment.woo_order_id,
        woo_order_number=fulfillment.woo_order_number,
        total_lines=len(fulfillment.lines),
        total_quantity_fulfilled=decimal_to_float(sum((line.quantity_to_fulfill for line in fulfillment.lines), Decimal("0"))),
        created_by=fulfillment.created_by,
        created_at=fulfillment.created_at,
        posted_at=fulfillment.posted_at,
    )


def fulfillment_line_to_read(line: FulfillmentLine) -> FulfillmentLineRead:
    return FulfillmentLineRead(
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
        quantity_picked=decimal_to_float(line.quantity_picked),
        quantity_previously_fulfilled=decimal_to_float(line.quantity_previously_fulfilled),
        quantity_to_fulfill=decimal_to_float(line.quantity_to_fulfill),
        quantity_fulfilled_after=decimal_to_float(line.quantity_fulfilled_after),
        remaining_to_fulfill=decimal_to_float(line.remaining_to_fulfill),
        in_stock_before=decimal_to_float(line.in_stock_before),
        allocated_before=decimal_to_float(line.allocated_before),
        sellable_before=decimal_to_float(line.sellable_before),
        in_stock_after=decimal_to_float(line.in_stock_after),
        allocated_after=decimal_to_float(line.allocated_after),
        sellable_after=decimal_to_float(line.sellable_after),
        status=line.status,
        notes=line.notes,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def next_fulfillment_number(db: Session, now: datetime) -> str:
    prefix = f"FL-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(Fulfillment.id)).where(Fulfillment.fulfillment_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def remaining_to_fulfill(line: OrderItem) -> Decimal:
    return max((line.quantity_picked or Decimal("0")) - (line.quantity_fulfilled or Decimal("0")), Decimal("0"))


def last_pick_location(db: Session | None, line: OrderItem):
    if db is None:
        return None
    pick_line = db.scalars(
        select(PickLine)
        .where(PickLine.order_line_id == line.id, PickLine.inventory_item_location_id.is_not(None))
        .order_by(PickLine.created_at.desc(), PickLine.id.desc())
    ).first()
    if pick_line is None or pick_line.inventory_item_location_id is None:
        return None
    from app.models.inventory import InventoryItemLocation

    return db.get(InventoryItemLocation, pick_line.inventory_item_location_id)


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
