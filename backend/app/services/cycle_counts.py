from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cycle_counts import CycleCount, CycleCountLine
from app.models.inventory import InventoryItem, InventoryLocation, MovementType, StockMovement
from app.schemas.cycle_counts import (
    CycleCountDetail,
    CycleCountLineRead,
    CycleCountPreviewLine,
    CycleCountPreviewResponse,
    CycleCountRead,
    CycleCountRequest,
)
from app.services.calculations import calculate_inventory_value
from app.services.items import apply_calculated_fields

CYCLE_COUNT_EXPORT_COLUMNS = [
    "Count Number",
    "Status",
    "Created At",
    "Posted At",
    "Warehouse",
    "Inventory Location",
    "SKU",
    "Barcode",
    "Description",
    "System Quantity",
    "Counted Quantity",
    "Variance Quantity",
    "Unit Cost",
    "Variance Value",
    "Notes",
]


@dataclass
class ValidatedCycleCountLine:
    line_number: int
    item: InventoryItem | None
    warehouse: str
    inventory_location: str | None
    counted_quantity: Decimal
    system_quantity: Decimal
    unit_cost: Decimal
    notes: str | None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.item is not None

    @property
    def variance_quantity(self) -> Decimal:
        return self.counted_quantity - self.system_quantity

    @property
    def variance_value(self) -> Decimal:
        return calculate_inventory_value(self.variance_quantity, self.unit_cost)


def validate_cycle_count(payload: CycleCountRequest, db: Session) -> tuple[list[ValidatedCycleCountLine], list[str], list[str]]:
    receipt_errors: list[str] = []
    warnings: list[str] = []
    warehouse = (payload.warehouse or "").strip()
    inventory_location = (payload.inventory_location or "").strip()
    count_type = payload.count_type or "selected_items"

    if not warehouse:
        receipt_errors.append("Warehouse is required for cycle count.")
    if count_type not in {"full_location", "selected_items"}:
        receipt_errors.append("Count Type must be full_location or selected_items.")
    if count_type == "full_location" and not inventory_location:
        receipt_errors.append("Inventory Location is required for full location cycle counts.")
    if not payload.lines:
        receipt_errors.append("At least one cycle count line is required.")

    location = None
    if warehouse and inventory_location:
        location = find_active_location(db, warehouse, inventory_location)
        if location is None:
            receipt_errors.append("Inventory Location must exist and be active for the selected warehouse.")

    lines: list[ValidatedCycleCountLine] = []
    for index, line in enumerate(payload.lines, start=1):
        line_errors = []
        counted_quantity = to_decimal(line.counted_quantity)
        if line.counted_quantity is None:
            line_errors.append("Counted Quantity is required.")
        if counted_quantity < 0:
            line_errors.append("Counted Quantity must be greater than or equal to zero.")

        item, item_errors = find_cycle_count_item(db, line.item_id, line.sku, line.barcode)
        line_errors.extend(item_errors)
        system_quantity = item.in_stock if item is not None else Decimal("0")
        unit_cost = item.unit_cost if item is not None and item.unit_cost is not None else Decimal("0")
        line_location = inventory_location or (item.inventory_location if item is not None else None)
        if location is not None:
            line_location = location.location_code or location.location_name or inventory_location

        lines.append(
            ValidatedCycleCountLine(
                line_number=index,
                item=item,
                warehouse=warehouse,
                inventory_location=line_location,
                counted_quantity=counted_quantity,
                system_quantity=system_quantity or Decimal("0"),
                unit_cost=unit_cost,
                notes=line.notes,
                errors=line_errors,
            )
        )
    return lines, receipt_errors, warnings


def build_cycle_count_preview(payload: CycleCountRequest, db: Session) -> CycleCountPreviewResponse:
    lines, header_errors, warnings = validate_cycle_count(payload, db)
    errors = [*header_errors]
    preview_lines: list[CycleCountPreviewLine] = []

    for line in lines:
        errors.extend([f"Line {line.line_number}: {error}" for error in line.errors])
        item = line.item
        preview_lines.append(
            CycleCountPreviewLine(
                line_number=line.line_number,
                item_id=item.id if item else None,
                sku=item.sku if item else None,
                barcode=item.barcode if item else None,
                description=item.description if item else None,
                warehouse=line.warehouse,
                inventory_location=line.inventory_location,
                system_quantity=float(line.system_quantity),
                counted_quantity=float(line.counted_quantity),
                variance_quantity=float(line.variance_quantity),
                unit_cost=float(line.unit_cost),
                variance_value=float(line.variance_value),
                status="valid" if line.is_valid else "invalid",
                warnings=line.warnings,
                errors=line.errors,
            )
        )

    totals = summarize_validated_lines([line for line in lines if line.is_valid])
    invalid_lines = len(header_errors) + sum(1 for line in lines if not line.is_valid)
    return CycleCountPreviewResponse(
        total_lines=len(lines),
        valid_lines=sum(1 for line in lines if line.is_valid),
        invalid_lines=invalid_lines,
        adjustment_lines=totals["adjustment_lines"],
        total_positive_variance=float(totals["total_positive_variance"]),
        total_negative_variance=float(totals["total_negative_variance"]),
        total_absolute_variance=float(totals["total_absolute_variance"]),
        total_variance_value=float(totals["total_variance_value"]),
        errors=errors,
        warnings=warnings,
        preview_lines=preview_lines,
    )


def commit_cycle_count(payload: CycleCountRequest, db: Session) -> tuple[CycleCount, int, dict[str, Decimal | int], list[str]]:
    preview = build_cycle_count_preview(payload, db)
    if preview.invalid_lines > 0:
        raise HTTPException(status_code=400, detail=preview.model_dump())

    lines, _, warnings = validate_cycle_count(payload, db)
    now = datetime.now(timezone.utc)
    count_number = generate_cycle_count_number(db, now)
    count = CycleCount(
        count_number=count_number,
        status="posted",
        warehouse=(payload.warehouse or "").strip(),
        inventory_location=(payload.inventory_location or "").strip() or None,
        count_type=payload.count_type or "selected_items",
        notes=payload.notes,
        created_by=payload.created_by or "system",
        posted_at=now,
    )
    db.add(count)
    db.flush()

    created_movements = 0
    for line in lines:
        item = db.get(InventoryItem, line.item.id)
        system_quantity = item.in_stock or Decimal("0")
        counted_quantity = line.counted_quantity
        variance_quantity = counted_quantity - system_quantity
        unit_cost = item.unit_cost or Decimal("0")
        variance_value = calculate_inventory_value(variance_quantity, unit_cost)
        line_location = (payload.inventory_location or "").strip() or item.inventory_location
        db.add(
            CycleCountLine(
                cycle_count_id=count.id,
                item_id=item.id,
                sku=item.sku,
                barcode=item.barcode,
                description=item.description,
                warehouse=(payload.warehouse or "").strip(),
                inventory_location=line_location,
                system_quantity=system_quantity,
                counted_quantity=counted_quantity,
                variance_quantity=variance_quantity,
                unit_cost=unit_cost,
                variance_value=variance_value,
                notes=line.notes,
            )
        )
        if variance_quantity != 0:
            item.in_stock = counted_quantity
            apply_calculated_fields(item)
            db.add(item)
            db.add(
                StockMovement(
                    inventory_item_id=item.id,
                    inventory_location_id=None,
                    sku=item.sku,
                    barcode=item.barcode,
                    movement_type=MovementType.cycle_count_adjustment,
                    quantity_change=variance_quantity,
                    old_stock=system_quantity,
                    new_stock=counted_quantity,
                    warehouse=(payload.warehouse or "").strip(),
                    inventory_location_name=line_location,
                    reference_number=count.count_number,
                    unit_cost=unit_cost,
                    reason="Cycle count adjustment",
                    notes=line.notes or payload.notes,
                    reference_type="cycle_count",
                    reference_id=count.id,
                    created_by=payload.created_by or "system",
                )
            )
            created_movements += 1

    db.commit()
    db.refresh(count)
    totals = summarize_count_lines(count.lines)
    return count, created_movements, totals, warnings


def summarize_validated_lines(lines: list[ValidatedCycleCountLine]) -> dict[str, Decimal | int]:
    totals: dict[str, Decimal | int] = {
        "adjustment_lines": 0,
        "total_positive_variance": Decimal("0"),
        "total_negative_variance": Decimal("0"),
        "total_absolute_variance": Decimal("0"),
        "total_variance_value": Decimal("0"),
    }
    for line in lines:
        add_variance_totals(totals, line.variance_quantity, line.variance_value)
    return totals


def summarize_count_lines(lines: list[CycleCountLine]) -> dict[str, Decimal | int]:
    totals: dict[str, Decimal | int] = {
        "adjustment_lines": 0,
        "total_positive_variance": Decimal("0"),
        "total_negative_variance": Decimal("0"),
        "total_absolute_variance": Decimal("0"),
        "total_variance_value": Decimal("0"),
    }
    for line in lines:
        add_variance_totals(totals, line.variance_quantity or Decimal("0"), line.variance_value or Decimal("0"))
    return totals


def add_variance_totals(totals: dict[str, Decimal | int], variance_quantity: Decimal, variance_value: Decimal) -> None:
    if variance_quantity != 0:
        totals["adjustment_lines"] += 1
    if variance_quantity > 0:
        totals["total_positive_variance"] += variance_quantity
    if variance_quantity < 0:
        totals["total_negative_variance"] += variance_quantity
    totals["total_absolute_variance"] += abs(variance_quantity)
    totals["total_variance_value"] += variance_value


def find_cycle_count_item(db: Session, item_id: int | None, sku: str | None, barcode: str | None) -> tuple[InventoryItem | None, list[str]]:
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
        errors.append("No matching item was found. Cycle count does not create items.")
    return item, errors


def find_active_location(db: Session, warehouse: str, inventory_location: str) -> InventoryLocation | None:
    return db.scalars(
        select(InventoryLocation).where(
            InventoryLocation.warehouse == warehouse,
            InventoryLocation.active.is_(True),
            or_(InventoryLocation.location_code == inventory_location, InventoryLocation.location_name == inventory_location),
        )
    ).first()


def generate_cycle_count_number(db: Session, now: datetime) -> str:
    prefix = f"CC-{now:%Y%m%d}"
    count = db.scalar(select(func.count(CycleCount.id)).where(CycleCount.count_number.like(f"{prefix}-%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def cycle_count_to_read(count: CycleCount) -> CycleCountRead:
    totals = summarize_count_lines(count.lines)
    return CycleCountRead(
        id=count.id,
        count_number=count.count_number,
        status=count.status,
        warehouse=count.warehouse,
        inventory_location=count.inventory_location,
        count_type=count.count_type,
        notes=count.notes,
        created_by=count.created_by,
        created_at=count.created_at,
        posted_at=count.posted_at,
        total_lines=len(count.lines),
        adjustment_lines=totals["adjustment_lines"],
        total_positive_variance=float(totals["total_positive_variance"]),
        total_negative_variance=float(totals["total_negative_variance"]),
        total_absolute_variance=float(totals["total_absolute_variance"]),
        total_variance_value=float(totals["total_variance_value"]),
    )


def cycle_count_to_detail(count: CycleCount) -> CycleCountDetail:
    base = cycle_count_to_read(count).model_dump()
    base["lines"] = [
        CycleCountLineRead(
            id=line.id,
            item_id=line.item_id,
            sku=line.sku,
            barcode=line.barcode,
            description=line.description,
            warehouse=line.warehouse,
            inventory_location=line.inventory_location,
            system_quantity=float(line.system_quantity),
            counted_quantity=float(line.counted_quantity),
            variance_quantity=float(line.variance_quantity),
            unit_cost=float(line.unit_cost) if line.unit_cost is not None else None,
            variance_value=float(line.variance_value),
            notes=line.notes,
            created_at=line.created_at,
        )
        for line in count.lines
    ]
    return CycleCountDetail.model_validate(base)


def cycle_count_line_to_export_row(count: CycleCount, line: CycleCountLine) -> dict[str, object]:
    return {
        "Count Number": count.count_number,
        "Status": count.status,
        "Created At": count.created_at.isoformat() if count.created_at else "",
        "Posted At": count.posted_at.isoformat() if count.posted_at else "",
        "Warehouse": line.warehouse or "",
        "Inventory Location": line.inventory_location or "",
        "SKU": line.sku or "",
        "Barcode": line.barcode or "",
        "Description": line.description or "",
        "System Quantity": line.system_quantity,
        "Counted Quantity": line.counted_quantity,
        "Variance Quantity": line.variance_quantity,
        "Unit Cost": line.unit_cost or Decimal("0"),
        "Variance Value": line.variance_value,
        "Notes": line.notes or "",
    }


def to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")
