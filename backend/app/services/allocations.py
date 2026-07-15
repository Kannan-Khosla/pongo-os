from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session, selectinload

from app.models.allocations import Allocation, AllocationLine
from app.models.inventory import InventoryAuditEvent, InventoryItem
from app.models.orders import Order, OrderItem
from app.schemas.allocations import (
    AllocationCommitResponse,
    AllocationDetail,
    AllocationExceptionLineRead,
    AllocationExceptionListResponse,
    AllocationLineRead,
    AllocationPreviewLine,
    AllocationPreviewOrder,
    AllocationPreviewResponse,
    AllocationRead,
    AllocationRequest,
)
from app.services.location_inventory import allocate_from_location, choose_allocation_location
from app.services.order_workflow import acquire_fifo_allocation_lock, is_active_order, sync_order_workflow_statuses

ALLOCATABLE_ORDER_STATUSES = {"open", "partially_allocated"}


def list_allocation_exception_lines(
    db: Session,
    search: str | None = None,
    warehouse: str | None = None,
    ordered_from: date | None = None,
    ordered_to: date | None = None,
    include_fully_allocated: bool = False,
) -> AllocationExceptionListResponse:
    statement = (
        select(OrderItem)
        .join(Order)
        .where(Order.woo_status == "processing")
        .options(selectinload(OrderItem.order), selectinload(OrderItem.inventory_item))
        .order_by(Order.date_created.asc().nulls_last(), Order.id.asc(), OrderItem.line_number.asc().nulls_last(), OrderItem.id.asc())
    )
    rows: list[AllocationExceptionLineRead] = []
    needle = (search or "").strip().casefold()
    for line in db.scalars(statement).all():
        order = line.order
        item = line.inventory_item
        if not is_active_order(order) or (item is not None and item.non_inventory):
            continue
        if ordered_from and (order.date_created is None or order.date_created.date() < ordered_from):
            continue
        if ordered_to and (order.date_created is None or order.date_created.date() > ordered_to):
            continue
        line_warehouse = item.warehouse if item else None
        if warehouse and (line_warehouse or "").casefold() != warehouse.casefold():
            continue
        ordered = to_decimal(line.quantity_ordered)
        allocated = to_decimal(line.quantity_allocated)
        unallocated = max(ordered - allocated, Decimal("0"))
        if not include_fully_allocated and unallocated <= 0 and line.matched_status == "matched":
            continue
        sku = line.sku or (item.sku if item else None)
        barcode = line.barcode or (item.barcode if item else None)
        description = line.name or line.description or (item.description if item else None)
        searchable = " ".join(
            str(value or "")
            for value in [order.woo_order_number, order.customer_name, order.customer_email, sku, barcode, description]
        ).casefold()
        if needle and needle not in searchable:
            continue
        available = max(current_sellable(item), Decimal("0")) if item else Decimal("0")
        reason = allocation_line_exception_reason(line, item, unallocated, available)
        rows.append(
            AllocationExceptionLineRead(
                order_id=order.id,
                order_line_id=line.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                ordered_at=order.date_created,
                customer_name=order.customer_name,
                item_id=item.id if item else None,
                sku=sku,
                barcode=barcode,
                description=description,
                warehouse=line_warehouse,
                inventory_location=item.inventory_location if item else None,
                quantity_ordered=decimal_to_float(ordered),
                quantity_allocated=decimal_to_float(allocated),
                quantity_unallocated=decimal_to_float(unallocated),
                quantity_picked=decimal_to_float(line.quantity_picked),
                quantity_available=decimal_to_float(available),
                allocation_status=line.allocation_status or "unallocated",
                exception_reason=reason,
            )
        )
    return AllocationExceptionListResponse(
        lines=rows,
        total_orders=len({row.order_id for row in rows}),
        total_lines=len(rows),
        total_quantity_unallocated=decimal_to_float(sum((to_decimal(row.quantity_unallocated) for row in rows), Decimal("0"))),
        lines_with_available_stock=sum(1 for row in rows if row.quantity_available > 0),
        lines_out_of_stock=sum(1 for row in rows if row.quantity_available <= 0),
    )


def allocation_line_exception_reason(line: OrderItem, item: InventoryItem | None, unallocated: Decimal, available: Decimal) -> str:
    if line.matched_status == "conflict":
        return "conflicting_item_match"
    if line.matched_status != "matched" or item is None:
        return "unmatched_item"
    if unallocated <= 0:
        return "fully_allocated"
    if available <= 0:
        return "out_of_stock"
    if available < unallocated:
        return "insufficient_stock"
    return "available_to_allocate"


def preview_allocation(db: Session, payload: AllocationRequest) -> AllocationPreviewResponse:
    return build_preview_response(build_preview_orders(db, payload))


def commit_allocation(db: Session, payload: AllocationRequest) -> AllocationCommitResponse:
    acquire_fifo_allocation_lock(db)
    preview = preview_allocation(db, payload)
    blocking_errors = list(preview.errors)
    if not payload.allow_partial:
        for order in preview.preview_orders:
            for line in order.lines:
                if line.allocation_status != "allocated":
                    blocking_errors.append(f"Order line {line.order_line_id} cannot be fully allocated.")
    if blocking_errors:
        return AllocationCommitResponse(
            status="rejected",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            allocated_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_allocated=0,
            total_shortage_quantity=preview.total_shortage_quantity,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=blocking_errors,
        )

    allocatable_preview_lines = [line for order in preview.preview_orders for line in order.lines if line.recommended_allocate_quantity > 0 and line.allocation_status in {"allocated", "partial"}]
    if not allocatable_preview_lines:
        return AllocationCommitResponse(
            status="rejected",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            allocated_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_allocated=0,
            total_shortage_quantity=preview.total_shortage_quantity,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=["No order lines are eligible for allocation."],
        )

    now = datetime.now(timezone.utc)
    first_order = preview.preview_orders[0] if len(preview.preview_orders) == 1 else None
    allocation = Allocation(
        allocation_number=next_allocation_number(db, now),
        status="posted",
        allocation_type="single_order" if len(preview.preview_orders) == 1 else "batch",
        order_id=first_order.order_id if first_order else None,
        woo_order_id=first_order.woo_order_id if first_order else None,
        woo_order_number=first_order.woo_order_number if first_order else None,
        notes=payload.notes,
        created_by=payload.created_by or "system",
        posted_at=now,
    )
    try:
        db.add(allocation)
        db.flush()
        audit_count = 0
        allocated_lines = 0
        partial_lines = 0
        touched_order_ids: set[int] = set()
        for preview_line in allocatable_preview_lines:
            order_line = db.get(OrderItem, preview_line.order_line_id)
            item = db.get(InventoryItem, preview_line.item_id) if preview_line.item_id else None
            if order_line is None or item is None:
                raise ValueError(f"Order line {preview_line.order_line_id} changed before allocation commit.")
            quantity_to_allocate = to_decimal(preview_line.recommended_allocate_quantity)
            remaining = remaining_to_allocate(order_line)
            sellable_before = current_sellable(item)
            if quantity_to_allocate <= 0 or quantity_to_allocate > remaining or quantity_to_allocate > sellable_before:
                raise ValueError(f"Order line {order_line.id} is no longer valid for allocation.")
            in_stock_before = item.in_stock or Decimal("0")
            allocated_before = item.allocated or Decimal("0")
            line_allocated_before = order_line.quantity_allocated or Decimal("0")
            change = allocate_from_location(
                db,
                item,
                quantity_to_allocate,
                reference_number=allocation.allocation_number,
                reference_id=allocation.id,
                notes=payload.notes,
                created_by=payload.created_by or "system",
            )
            allocated_after = change.item.allocated or Decimal("0")
            line_allocated_after = line_allocated_before + quantity_to_allocate
            sellable_after = change.item.sellable or Decimal("0")
            line_remaining_after = max((order_line.quantity_ordered or Decimal("0")) - line_allocated_after, Decimal("0"))
            line_shortage_after = max(line_remaining_after - sellable_after, Decimal("0"))
            order_line.quantity_allocated = line_allocated_after
            order_line.allocated_qty = line_allocated_after
            order_line.sellable_snapshot = sellable_after
            order_line.shortage_quantity = line_shortage_after
            order_line.availability_status = "allocated" if line_remaining_after == 0 else ("partial" if line_allocated_after > 0 else "unavailable")
            order_line.allocation_status = "allocated" if line_remaining_after == 0 else ("partially_allocated" if line_allocated_after > 0 else "unallocated")
            order_line.status = order_line.availability_status
            allocation_line = AllocationLine(
                allocation_id=allocation.id,
                order_id=order_line.order_id,
                order_line_id=order_line.id,
                item_id=item.id,
                inventory_item_location_id=change.item_location.id,
                sku=order_line.sku or item.sku,
                barcode=order_line.barcode or item.barcode,
                description=order_line.name or order_line.description or item.description,
                warehouse=change.item_location.warehouse,
                inventory_location=change.item_location.inventory_location,
                quantity_ordered=order_line.quantity_ordered or Decimal("0"),
                quantity_previously_allocated=line_allocated_before,
                quantity_to_allocate=quantity_to_allocate,
                quantity_allocated_after=line_allocated_after,
                in_stock_before=in_stock_before,
                allocated_before=allocated_before,
                sellable_before=sellable_before,
                allocated_after=allocated_after,
                sellable_after=sellable_after,
                shortage_quantity=line_shortage_after,
                status="allocated" if line_remaining_after == 0 else "partial",
                notes=payload.notes,
            )
            db.add(allocation_line)
            db.add(
                InventoryAuditEvent(
                    item_id=item.id,
                    sku=item.sku,
                    barcode=item.barcode,
                    event_type="allocate",
                    quantity_delta=quantity_to_allocate,
                    previous_in_stock=in_stock_before,
                    new_in_stock=in_stock_before,
                    previous_allocated=change.old_item_allocated,
                    new_allocated=change.new_item_allocated,
                    previous_sellable=sellable_before,
                    new_sellable=sellable_after,
                    warehouse=change.item_location.warehouse,
                    inventory_location=change.item_location.inventory_location,
                    reference_type="allocation",
                    reference_id=allocation.id,
                    reference_number=allocation.allocation_number,
                    notes=payload.notes,
                    created_by=payload.created_by or "system",
                )
            )
            audit_count += 1
            allocated_lines += 1
            partial_lines += 1 if line_remaining_after > 0 else 0
            touched_order_ids.add(order_line.order_id)

        db.flush()
        for order_id in touched_order_ids:
            order = db.scalars(select(Order).where(Order.id == order_id).options(selectinload(Order.items))).one()
            update_order_allocation_status(order)
        db.commit()
        db.refresh(allocation)
        return AllocationCommitResponse(
            allocation_id=allocation.id,
            allocation_number=allocation.allocation_number,
            status=allocation.status,
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            allocated_lines=allocated_lines,
            partial_lines=partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_allocated=decimal_to_float(sum((line.quantity_to_allocate for line in allocation.lines), Decimal("0"))),
            total_shortage_quantity=preview.total_shortage_quantity,
            created_audit_events=audit_count,
            warnings=preview.warnings,
            errors=[],
        )
    except Exception as exc:
        db.rollback()
        return AllocationCommitResponse(
            status="error",
            total_orders=preview.total_orders,
            total_lines=preview.total_lines,
            allocated_lines=0,
            partial_lines=preview.partial_lines,
            skipped_lines=preview.skipped_lines,
            total_quantity_allocated=0,
            total_shortage_quantity=preview.total_shortage_quantity,
            created_audit_events=0,
            warnings=preview.warnings,
            errors=[str(exc)],
        )


def build_preview_orders(db: Session, payload: AllocationRequest) -> list[AllocationPreviewOrder]:
    order_lines = selected_order_lines(db, payload)
    orders_by_id: dict[int, list[OrderItem]] = {}
    for line in order_lines:
        orders_by_id.setdefault(line.order_id, []).append(line)
    preview_orders: list[AllocationPreviewOrder] = []
    for order_id, lines in orders_by_id.items():
        order = lines[0].order
        preview_lines = [build_preview_line(line, explicit_quantity(payload, line.id)) for line in lines]
        warnings = []
        errors = []
        if order.local_status not in ALLOCATABLE_ORDER_STATUSES:
            errors.append(f"Order status {order.local_status or 'unknown'} is not eligible for allocation.")
        line_count = len(preview_lines)
        allocatable_lines = sum(1 for line in preview_lines if line.allocation_status == "allocated")
        partial_lines = sum(1 for line in preview_lines if line.allocation_status == "partial")
        skipped_lines = sum(1 for line in preview_lines if line.allocation_status in {"skipped", "unavailable"})
        conflict_lines = sum(1 for line in preview_lines if line.allocation_status == "conflict")
        recommended_status = "allocated" if line_count and allocatable_lines == line_count else ("partially_allocated" if allocatable_lines or partial_lines else order.local_status or "open")
        preview_orders.append(
            AllocationPreviewOrder(
                order_id=order.id,
                woo_order_id=order.woo_order_id,
                woo_order_number=order.woo_order_number,
                local_status=order.local_status,
                line_count=line_count,
                allocatable_lines=allocatable_lines,
                partial_lines=partial_lines,
                skipped_lines=skipped_lines,
                conflict_lines=conflict_lines,
                recommended_status=recommended_status,
                warnings=warnings,
                errors=errors + [error for line in preview_lines for error in line.errors],
                lines=preview_lines,
            )
        )
    return preview_orders


def selected_order_lines(db: Session, payload: AllocationRequest) -> list[OrderItem]:
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


def explicit_quantity(payload: AllocationRequest, order_line_id: int) -> Decimal | None:
    for line in payload.lines:
        if line.order_line_id == order_line_id:
            return to_decimal(line.quantity_to_allocate)
    return None


def build_preview_line(line: OrderItem, requested_quantity: Decimal | None = None) -> AllocationPreviewLine:
    warnings: list[str] = []
    errors: list[str] = []
    item = line.inventory_item
    ordered = line.quantity_ordered or Decimal("0")
    previously_allocated = line.quantity_allocated or Decimal("0")
    remaining = max(ordered - previously_allocated, Decimal("0"))
    in_stock = item.in_stock if item else Decimal("0")
    allocated = item.allocated if item else Decimal("0")
    sellable = current_sellable(item) if item else Decimal("0")
    item_location_id = None
    location_warehouse = item.warehouse if item else None
    location_name = item.inventory_location if item else None
    recommended = Decimal("0")
    status = "skipped"
    if line.order.local_status not in ALLOCATABLE_ORDER_STATUSES:
        errors.append(f"Order status {line.order.local_status or 'unknown'} is not eligible.")
    elif line.matched_status != "matched":
        status = "conflict" if line.matched_status == "conflict" else "skipped"
        errors.append(f"Order line matched status is {line.matched_status or 'unknown'}.")
    elif item is None:
        errors.append("Order line has no matched local item.")
    elif item.non_inventory:
        warnings.append("Non-inventory items are not allocated.")
    elif remaining <= 0:
        warnings.append("Order line is already fully allocated.")
    elif sellable <= 0:
        status = "unavailable"
        warnings.append("Matched item has no sellable inventory.")
    else:
        try:
            db = object_session(line)
            if db is None:
                raise ValueError("Order line is not attached to a database session.")
            location_row = choose_allocation_location(db, item, requested_quantity or min(remaining, sellable))
            item_location_id = location_row.id
            location_warehouse = location_row.warehouse
            location_name = location_row.inventory_location
        except Exception as exc:
            location_row = None
            errors.append(str(exc))
        recommended = min(remaining, sellable) if not errors else Decimal("0")
        if requested_quantity is not None and not errors:
            if requested_quantity <= 0:
                errors.append("Requested allocation quantity must be greater than zero.")
                recommended = Decimal("0")
            elif requested_quantity > remaining:
                errors.append("Requested allocation quantity exceeds remaining order quantity.")
                recommended = Decimal("0")
            elif requested_quantity > sellable:
                errors.append("Requested allocation quantity exceeds current item sellable quantity.")
                recommended = Decimal("0")
            else:
                recommended = requested_quantity
        status = "allocated" if recommended == remaining and recommended > 0 else ("partial" if recommended > 0 else status)
    shortage = max(remaining - recommended, Decimal("0"))
    return AllocationPreviewLine(
        order_id=line.order_id,
        order_line_id=line.id,
        item_id=item.id if item else None,
        inventory_item_location_id=item_location_id,
        sku=line.sku or (item.sku if item else None),
        barcode=line.barcode or (item.barcode if item else None),
        description=line.name or line.description or (item.description if item else None),
        quantity_ordered=decimal_to_float(ordered),
        quantity_previously_allocated=decimal_to_float(previously_allocated),
        remaining_to_allocate=decimal_to_float(remaining),
        in_stock=decimal_to_float(in_stock),
        allocated=decimal_to_float(allocated),
        sellable=decimal_to_float(sellable),
        recommended_allocate_quantity=decimal_to_float(recommended),
        shortage_quantity=decimal_to_float(shortage),
        allocation_status=status,
        warnings=warnings,
        errors=errors,
    )


def build_preview_response(orders: list[AllocationPreviewOrder]) -> AllocationPreviewResponse:
    lines = [line for order in orders for line in order.lines]
    return AllocationPreviewResponse(
        total_orders=len(orders),
        total_lines=len(lines),
        allocatable_lines=sum(1 for line in lines if line.allocation_status == "allocated"),
        partial_lines=sum(1 for line in lines if line.allocation_status == "partial"),
        skipped_lines=sum(1 for line in lines if line.allocation_status in {"skipped", "unavailable"}),
        conflict_lines=sum(1 for line in lines if line.allocation_status == "conflict"),
        total_quantity_to_allocate=decimal_to_float(sum((to_decimal(line.recommended_allocate_quantity) for line in lines), Decimal("0"))),
        total_shortage_quantity=decimal_to_float(sum((to_decimal(line.shortage_quantity) for line in lines), Decimal("0"))),
        warnings=[warning for order in orders for warning in order.warnings] + [warning for line in lines for warning in line.warnings],
        errors=[error for order in orders for error in order.errors] + [error for line in lines for error in line.errors],
        preview_orders=orders,
    )


def update_order_allocation_status(order: Order) -> None:
    sync_order_workflow_statuses(order)


def list_allocations(
    db: Session,
    status: str | None = None,
    allocation_type: str | None = None,
    order_id: int | None = None,
    woo_order_id: int | None = None,
    woo_order_number: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    created_by: str | None = None,
):
    statement = select(Allocation).options(selectinload(Allocation.lines)).order_by(Allocation.created_at.desc(), Allocation.id.desc())
    if status:
        statement = statement.where(Allocation.status == status)
    if allocation_type:
        statement = statement.where(Allocation.allocation_type == allocation_type)
    if order_id is not None:
        statement = statement.where(Allocation.order_id == order_id)
    if woo_order_id is not None:
        statement = statement.where(Allocation.woo_order_id == woo_order_id)
    if woo_order_number:
        statement = statement.where(Allocation.woo_order_number == woo_order_number)
    if date_from:
        statement = statement.where(Allocation.created_at >= date_from)
    if date_to:
        statement = statement.where(Allocation.created_at <= date_to)
    if created_by:
        statement = statement.where(Allocation.created_by == created_by)
    return list(db.scalars(statement).all())


def get_allocation_detail(db: Session, allocation_id: int) -> AllocationDetail | None:
    allocation = db.scalars(select(Allocation).where(Allocation.id == allocation_id).options(selectinload(Allocation.lines))).one_or_none()
    if allocation is None:
        return None
    audit_ids = list(db.scalars(select(InventoryAuditEvent.id).where(InventoryAuditEvent.reference_type == "allocation", InventoryAuditEvent.reference_id == allocation.id)).all())
    base = allocation_to_read(allocation).model_dump()
    base["notes"] = allocation.notes
    base["lines"] = [allocation_line_to_read(line) for line in sorted(allocation.lines, key=lambda row: row.id)]
    base["audit_event_ids"] = audit_ids
    return AllocationDetail.model_validate(base)


def export_allocation_csv(db: Session, allocation_id: int) -> str | None:
    detail = get_allocation_detail(db, allocation_id)
    if detail is None:
        return None
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Allocation Number",
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
            "Previously Allocated",
            "Quantity Allocated",
            "Allocated After",
            "In Stock Before",
            "Sellable Before",
            "Sellable After",
            "Shortage Quantity",
            "Line Status",
            "Notes",
        ]
    )
    for line in detail.lines:
        writer.writerow(
            [
                detail.allocation_number,
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
                line.quantity_previously_allocated,
                line.quantity_to_allocate,
                line.quantity_allocated_after,
                line.in_stock_before,
                line.sellable_before,
                line.sellable_after,
                line.shortage_quantity,
                line.status,
                line.notes or "",
            ]
        )
    return output.getvalue()


def allocation_to_read(allocation: Allocation) -> AllocationRead:
    return AllocationRead(
        id=allocation.id,
        allocation_number=allocation.allocation_number,
        status=allocation.status,
        allocation_type=allocation.allocation_type,
        order_id=allocation.order_id,
        woo_order_id=allocation.woo_order_id,
        woo_order_number=allocation.woo_order_number,
        total_lines=len(allocation.lines),
        total_quantity_allocated=decimal_to_float(sum((line.quantity_to_allocate for line in allocation.lines), Decimal("0"))),
        created_by=allocation.created_by,
        auto_allocated=bool(allocation.auto_allocated),
        allocation_source=allocation.allocation_source,
        created_at=allocation.created_at,
        posted_at=allocation.posted_at,
    )


def allocation_line_to_read(line: AllocationLine) -> AllocationLineRead:
    return AllocationLineRead(
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
        quantity_previously_allocated=decimal_to_float(line.quantity_previously_allocated),
        quantity_to_allocate=decimal_to_float(line.quantity_to_allocate),
        quantity_allocated_after=decimal_to_float(line.quantity_allocated_after),
        in_stock_before=decimal_to_float(line.in_stock_before),
        allocated_before=decimal_to_float(line.allocated_before),
        sellable_before=decimal_to_float(line.sellable_before),
        allocated_after=decimal_to_float(line.allocated_after),
        sellable_after=decimal_to_float(line.sellable_after),
        shortage_quantity=decimal_to_float(line.shortage_quantity),
        status=line.status,
        auto_allocated=bool(line.auto_allocated),
        allocation_source=line.allocation_source,
        notes=line.notes,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def next_allocation_number(db: Session, now: datetime) -> str:
    prefix = f"AL-{now:%Y%m%d}-"
    count = db.scalar(select(func.count(Allocation.id)).where(Allocation.allocation_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def remaining_to_allocate(line: OrderItem) -> Decimal:
    return max((line.quantity_ordered or Decimal("0")) - (line.quantity_allocated or Decimal("0")), Decimal("0"))


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
