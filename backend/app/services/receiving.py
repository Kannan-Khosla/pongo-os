from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem, InventoryItemLocation, InventoryLocation
from app.models.receipts import Receipt, ReceiptItem
from app.schemas.receipts import (
    DirectReceiptLinePreview,
    DirectReceiptPreviewResponse,
    DirectReceiptRequest,
    ReceiptDetail,
    ReceiptLineRead,
    ReceiptRead,
)
from app.services.calculations import calculate_inventory_value
from app.services.items import apply_calculated_fields
from app.services.location_inventory import find_item_location, receive_to_location
from app.services.order_workflow import auto_allocate_processing_orders_fifo


@dataclass
class ValidatedReceivingLine:
    line_number: int
    item: InventoryItem | None
    location: InventoryLocation | None
    item_location: InventoryItemLocation | None
    warehouse: str
    inventory_location: str
    default_location: str | None
    quantity_received: Decimal
    unit_cost: Decimal
    lot_number: str | None
    expiry_date: date | None
    notes: str | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.item is not None and self.location is not None


def validate_direct_receipt(payload: DirectReceiptRequest, db: Session) -> tuple[list[ValidatedReceivingLine], list[str], list[str]]:
    receipt_errors: list[str] = []
    warnings: list[str] = []
    warehouse = (payload.warehouse or "").strip()
    if not warehouse:
        receipt_errors.append("Warehouse is required for direct receiving.")
    if not payload.lines:
        receipt_errors.append("At least one receiving line is required.")

    lines: list[ValidatedReceivingLine] = []
    for index, line in enumerate(payload.lines, start=1):
        line_errors = []
        line_warnings = []
        quantity = to_decimal(line.quantity_received)
        unit_cost = to_decimal(line.unit_cost)
        inventory_location = (line.inventory_location or "").strip()
        if not inventory_location:
            line_errors.append("Inventory Location is required.")
        if quantity <= 0:
            line_errors.append("Quantity Received must be greater than zero.")

        item, item_errors = find_receiving_item(db, line.item_id, line.sku, line.barcode)
        line_errors.extend(item_errors)
        location = find_active_location(db, warehouse, inventory_location) if warehouse and inventory_location else None
        item_location = find_item_location(db, item.id, warehouse, inventory_location) if item is not None else None
        if warehouse and inventory_location and location is None:
            line_errors.append("Inventory Location must exist and be active for the selected warehouse.")
        if item is not None and item.unit_cost in (None, Decimal("0")) and unit_cost > 0:
            line_warnings.append("Receipt unit cost is stored on the receipt line and movement; item Unit Cost is not overwritten.")

        lines.append(
            ValidatedReceivingLine(
                line_number=index,
                item=item,
                location=location,
                item_location=item_location,
                warehouse=warehouse,
                inventory_location=inventory_location,
                default_location=(line.default_location or inventory_location or "").strip() or None,
                quantity_received=quantity,
                unit_cost=unit_cost,
                lot_number=line.lot_number,
                expiry_date=line.expiry_date,
                notes=line.notes,
                warnings=line_warnings,
                errors=line_errors,
            )
        )
    return lines, receipt_errors, warnings


def build_direct_receipt_preview(payload: DirectReceiptRequest, db: Session) -> DirectReceiptPreviewResponse:
    lines, receipt_errors, warnings = validate_direct_receipt(payload, db)
    preview_lines: list[DirectReceiptLinePreview] = []
    total_quantity = Decimal("0")
    total_value = Decimal("0")
    errors = [*receipt_errors]

    for line in lines:
        previous_item_stock = line.item.in_stock if line.item is not None else Decimal("0")
        new_item_stock = previous_item_stock + line.quantity_received if line.item is not None else Decimal("0")
        previous_location_stock = line.item_location.in_stock if line.item_location is not None else Decimal("0")
        new_location_stock = previous_location_stock + line.quantity_received if line.item is not None else Decimal("0")
        line_value = line.quantity_received * line.unit_cost
        if line.is_valid:
            total_quantity += line.quantity_received
            total_value += line_value
        errors.extend([f"Line {line.line_number}: {error}" for error in line.errors])
        preview_lines.append(
            DirectReceiptLinePreview(
                line_number=line.line_number,
                item_id=line.item.id if line.item else None,
                inventory_item_location_id=line.item_location.id if line.item_location else None,
                sku=line.item.sku if line.item else None,
                barcode=line.item.barcode if line.item else None,
                description=line.item.description if line.item else None,
                warehouse=line.warehouse,
                inventory_location=line.inventory_location,
                quantity_received=float(line.quantity_received),
                previous_in_stock=float(previous_location_stock),
                new_in_stock=float(new_location_stock),
                previous_location_in_stock=float(previous_location_stock),
                new_location_in_stock=float(new_location_stock),
                previous_item_in_stock=float(previous_item_stock),
                new_item_in_stock=float(new_item_stock),
                unit_cost=float(line.unit_cost),
                line_value=float(line_value),
                status="valid" if line.is_valid else "invalid",
                warnings=line.warnings,
                errors=line.errors,
            )
        )

    return DirectReceiptPreviewResponse(
        total_lines=len(lines),
        valid_lines=sum(1 for line in lines if line.is_valid),
        invalid_lines=len(receipt_errors) + sum(1 for line in lines if not line.is_valid),
        total_quantity=float(total_quantity),
        estimated_inventory_value=float(total_value),
        errors=errors,
        warnings=[*warnings, *[f"Line {line.line_number}: {warning}" for line in lines for warning in line.warnings]],
        preview_lines=preview_lines,
    )


def commit_direct_receipt(payload: DirectReceiptRequest, db: Session) -> tuple[Receipt, int, Decimal, Decimal, list[str]]:
    preview = build_direct_receipt_preview(payload, db)
    if preview.invalid_lines > 0:
        raise HTTPException(status_code=400, detail=preview.model_dump())

    lines, _, warnings = validate_direct_receipt(payload, db)
    now = datetime.now(timezone.utc)
    received_date = date.today()
    receipt_number = generate_direct_receipt_number(db, now)
    receipt = Receipt(
        receipt_number=receipt_number,
        receipt_type="direct",
        status="posted",
        warehouse=payload.warehouse,
        reference_number=payload.reference_number,
        notes=payload.notes,
        created_by=payload.created_by or "system",
        received_by=payload.created_by or "system",
        received_date=received_date,
        received_at=now,
    )
    db.add(receipt)
    db.flush()

    total_quantity = Decimal("0")
    total_value = Decimal("0")
    movement_count = 0
    for line in lines:
        item = line.item
        change = receive_to_location(
            db,
            item,
            line.warehouse,
            line.inventory_location,
            line.quantity_received,
            unit_cost=line.unit_cost,
            reference_number=receipt.receipt_number,
            reference_type="direct_receipt",
            reference_id=receipt.id,
            notes=line.notes,
            created_by=payload.created_by or "system",
        )
        item.default_location = line.default_location or item.default_location
        apply_calculated_fields(item)

        line_value = line.quantity_received * line.unit_cost
        receipt_item = ReceiptItem(
            receipt_id=receipt.id,
            inventory_item_id=item.id,
            inventory_location_id=line.location.id if line.location else None,
            inventory_item_location_id=change.item_location.id,
            sku=item.sku,
            category=item.category,
            description=item.description,
            quantity=line.quantity_received,
            quantity_received=line.quantity_received,
            uom=item.unit_of_measurement,
            unit_cost=line.unit_cost,
            unit_cost_total=line_value,
            sales_price=item.sales_price,
            weight=item.weight,
            brand=item.brand,
            client=item.client,
            lot_number=line.lot_number,
            expiration_date=line.expiry_date,
            warehouse=line.warehouse,
            inventory_location_name=line.inventory_location,
            default_location=line.default_location,
            received_date=received_date,
            po_or_receipt_number=receipt.receipt_number,
            name=item.description,
            notes=line.notes,
        )
        db.add(receipt_item)
        total_quantity += line.quantity_received
        total_value += calculate_inventory_value(line.quantity_received, line.unit_cost)
        movement_count += 1

    auto_allocate_processing_orders_fifo(db, source=f"direct-receipt:{receipt.receipt_number}")
    db.commit()
    db.refresh(receipt)
    return receipt, movement_count, total_quantity, total_value, warnings


def find_receiving_item(db: Session, item_id: int | None, sku: str | None, barcode: str | None) -> tuple[InventoryItem | None, list[str]]:
    errors: list[str] = []
    id_match = db.get(InventoryItem, item_id) if item_id is not None else None
    sku_match = db.scalars(select(InventoryItem).where(InventoryItem.sku == sku)).first() if sku else None
    barcode_match = db.scalars(select(InventoryItem).where(InventoryItem.barcode == barcode)).first() if barcode else None
    matches = [match for match in [id_match, sku_match, barcode_match] if match is not None]
    if len({match.id for match in matches}) > 1:
        errors.append("Item identifiers match different existing items.")
        return None, errors
    item = matches[0] if matches else None
    if item is None:
        errors.append("No matching item was found. Direct receiving does not create items.")
    return item, errors


def find_active_location(db: Session, warehouse: str, inventory_location: str) -> InventoryLocation | None:
    return db.scalars(
        select(InventoryLocation).where(
            InventoryLocation.warehouse == warehouse,
            InventoryLocation.active.is_(True),
            or_(InventoryLocation.location_code == inventory_location, InventoryLocation.location_name == inventory_location),
        )
    ).first()


def generate_direct_receipt_number(db: Session, now: datetime) -> str:
    prefix = f"DR-{now:%Y%m%d}"
    count = db.scalar(select(func.count(Receipt.id)).where(Receipt.receipt_number.like(f"{prefix}-%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def receipt_to_read(receipt: Receipt) -> ReceiptRead:
    total_quantity = sum((item.quantity_received or item.quantity or Decimal("0")) for item in receipt.items)
    return ReceiptRead(
        id=receipt.id,
        receipt_number=receipt.receipt_number,
        receipt_type=receipt.receipt_type,
        status=receipt.status,
        warehouse=receipt.warehouse,
        reference_number=receipt.reference_number,
        notes=receipt.notes,
        created_by=receipt.created_by or receipt.received_by,
        received_at=receipt.received_at,
        created_at=receipt.created_at,
        total_lines=len(receipt.items),
        total_quantity=float(total_quantity),
    )


def receipt_to_detail(receipt: Receipt) -> ReceiptDetail:
    base = receipt_to_read(receipt).model_dump()
    base["lines"] = [
        ReceiptLineRead(
            id=item.id,
            item_id=item.inventory_item_id,
            inventory_item_location_id=item.inventory_item_location_id,
            sku=item.sku,
            barcode=item.inventory_item.barcode if item.inventory_item else None,
            description=item.description,
            warehouse=item.warehouse,
            inventory_location=item.inventory_location_name or (item.inventory_location.location_code if item.inventory_location else None),
            default_location=item.default_location,
            quantity_received=float(item.quantity_received or item.quantity or Decimal("0")),
            unit_cost=float(item.unit_cost) if item.unit_cost is not None else None,
            lot_number=item.lot_number,
            expiry_date=item.expiration_date,
            notes=item.notes,
            created_at=item.created_at,
        )
        for item in receipt.items
    ]
    return ReceiptDetail.model_validate(base)


def to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return Decimal("0")
