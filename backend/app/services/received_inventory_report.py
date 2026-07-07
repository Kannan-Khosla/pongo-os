from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.receipts import Receipt, ReceiptItem
from app.schemas.reports import ReceivedInventoryReportRow
from app.services.calculations import calculate_inventory_value

RECEIVED_INVENTORY_CSV_COLUMNS = [
    "Receipt Number",
    "Receipt Type",
    "Status",
    "Received At",
    "Warehouse",
    "Inventory Location",
    "Default Location",
    "SKU",
    "Barcode",
    "Description",
    "Category",
    "Brand",
    "Quantity Received",
    "Unit Cost",
    "Total Received Value",
    "Reference Number",
    "Created By",
    "Line Notes",
    "Receipt Notes",
]


@dataclass(frozen=True)
class ReceivedInventoryFilters:
    date_from: date | None = None
    date_to: date | None = None
    warehouse: str | None = None
    inventory_location: str | None = None
    sku: str | None = None
    barcode: str | None = None
    category: str | None = None
    brand: str | None = None
    receipt_number: str | None = None
    reference_number: str | None = None
    created_by: str | None = None


def get_received_inventory_rows(db: Session, filters: ReceivedInventoryFilters) -> list[ReceivedInventoryReportRow]:
    statement = (
        select(ReceiptItem)
        .join(Receipt)
        .options(
            selectinload(ReceiptItem.receipt),
            selectinload(ReceiptItem.inventory_item),
            selectinload(ReceiptItem.inventory_location),
        )
        .order_by(Receipt.received_at.desc().nullslast(), Receipt.created_at.desc(), ReceiptItem.id.asc())
    )
    receipt_items = list(db.scalars(statement).all())
    rows = [receipt_item_to_report_row(receipt_item) for receipt_item in receipt_items]
    return [row for row in rows if row_matches_filters(row, filters)]


def receipt_item_to_report_row(receipt_item: ReceiptItem) -> ReceivedInventoryReportRow:
    receipt = receipt_item.receipt
    item = receipt_item.inventory_item
    quantity = receipt_item.quantity_received if receipt_item.quantity_received is not None else receipt_item.quantity
    unit_cost = receipt_item.unit_cost or Decimal("0")
    warehouse = receipt_item.warehouse or receipt.warehouse
    inventory_location = receipt_item.inventory_location.location_code if receipt_item.inventory_location else None
    total_value = calculate_inventory_value(quantity, unit_cost)
    return ReceivedInventoryReportRow(
        receipt_id=receipt.id,
        receipt_number=receipt.receipt_number,
        receipt_type=receipt.receipt_type,
        status=receipt.status,
        received_at=effective_received_at(receipt),
        created_at=receipt.created_at,
        warehouse=warehouse,
        inventory_location=inventory_location,
        default_location=receipt_item.default_location,
        sku=receipt_item.sku or (item.sku if item else None),
        barcode=item.barcode if item else None,
        description=receipt_item.description or (item.description if item else None),
        category=receipt_item.category or (item.category if item else None),
        brand=receipt_item.brand or (item.brand if item else None),
        quantity_received=float(quantity or Decimal("0")),
        unit_cost=float(unit_cost),
        total_received_value=float(total_value),
        reference_number=receipt.reference_number,
        created_by=receipt.created_by or receipt.received_by,
        line_notes=receipt_item.notes,
        receipt_notes=receipt.notes,
    )


def build_received_inventory_summary(rows: list[ReceivedInventoryReportRow], filters: ReceivedInventoryFilters) -> dict[str, object]:
    receipt_ids = {row.receipt_id for row in rows}
    skus = {row.sku for row in rows if row.sku}
    locations = {(row.warehouse or "", row.inventory_location or "") for row in rows if row.inventory_location or row.warehouse}
    summary: dict[str, object] = {
        "total_receipts": len(receipt_ids),
        "total_lines": len(rows),
        "total_quantity_received": sum(Decimal(str(row.quantity_received)) for row in rows),
        "total_received_value": sum(Decimal(str(row.total_received_value)) for row in rows),
        "unique_skus": len(skus),
        "unique_locations": len(locations),
        "date_from": filters.date_from.isoformat() if filters.date_from else None,
        "date_to": filters.date_to.isoformat() if filters.date_to else None,
        "by_warehouse": build_warehouse_groups(rows),
        "by_location": build_location_groups(rows),
        "by_sku": build_sku_groups(rows),
    }
    return summary


def build_warehouse_groups(rows: list[ReceivedInventoryReportRow]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for row in rows:
        warehouse = row.warehouse or ""
        group = groups.setdefault(warehouse, {"warehouse": warehouse, "total_lines": 0, "total_quantity_received": Decimal("0"), "total_received_value": Decimal("0")})
        add_group_totals(group, row)
    return sorted(groups.values(), key=lambda group: str(group["warehouse"]))


def build_location_groups(rows: list[ReceivedInventoryReportRow]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        warehouse = row.warehouse or ""
        inventory_location = row.inventory_location or ""
        group = groups.setdefault(
            (warehouse, inventory_location),
            {"warehouse": warehouse, "inventory_location": inventory_location, "total_lines": 0, "total_quantity_received": Decimal("0"), "total_received_value": Decimal("0")},
        )
        add_group_totals(group, row)
    return sorted(groups.values(), key=lambda group: (str(group["warehouse"]), str(group["inventory_location"])))


def build_sku_groups(rows: list[ReceivedInventoryReportRow]) -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    receipt_ids_by_sku: dict[str, set[int]] = {}
    for row in rows:
        sku = row.sku or ""
        group = groups.setdefault(
            sku,
            {
                "sku": sku,
                "barcode": row.barcode,
                "description": row.description,
                "brand": row.brand,
                "category": row.category,
                "total_quantity_received": Decimal("0"),
                "total_received_value": Decimal("0"),
                "receipt_count": 0,
            },
        )
        group["total_quantity_received"] += Decimal(str(row.quantity_received))
        group["total_received_value"] += Decimal(str(row.total_received_value))
        receipt_ids_by_sku.setdefault(sku, set()).add(row.receipt_id)
    for sku, group in groups.items():
        group["receipt_count"] = len(receipt_ids_by_sku.get(sku, set()))
    return sorted(groups.values(), key=lambda group: str(group["sku"]))


def received_inventory_row_to_csv(row: ReceivedInventoryReportRow) -> dict[str, object]:
    return {
        "Receipt Number": row.receipt_number,
        "Receipt Type": row.receipt_type or "",
        "Status": row.status or "",
        "Received At": row.received_at.isoformat() if row.received_at else "",
        "Warehouse": row.warehouse or "",
        "Inventory Location": row.inventory_location or "",
        "Default Location": row.default_location or "",
        "SKU": row.sku or "",
        "Barcode": row.barcode or "",
        "Description": row.description or "",
        "Category": row.category or "",
        "Brand": row.brand or "",
        "Quantity Received": row.quantity_received,
        "Unit Cost": row.unit_cost,
        "Total Received Value": row.total_received_value,
        "Reference Number": row.reference_number or "",
        "Created By": row.created_by or "",
        "Line Notes": row.line_notes or "",
        "Receipt Notes": row.receipt_notes or "",
    }


def row_matches_filters(row: ReceivedInventoryReportRow, filters: ReceivedInventoryFilters) -> bool:
    received_date = (row.received_at or row.created_at).date()
    if filters.date_from and received_date < filters.date_from:
        return False
    if filters.date_to and received_date > filters.date_to:
        return False
    return all(
        [
            text_matches(row.warehouse, filters.warehouse),
            text_matches(row.inventory_location, filters.inventory_location),
            text_matches(row.sku, filters.sku),
            text_matches(row.barcode, filters.barcode),
            text_matches(row.category, filters.category),
            text_matches(row.brand, filters.brand),
            text_matches(row.receipt_number, filters.receipt_number),
            text_matches(row.reference_number, filters.reference_number),
            text_matches(row.created_by, filters.created_by),
        ]
    )


def effective_received_at(receipt: Receipt) -> datetime:
    return receipt.received_at or receipt.created_at


def text_matches(value: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    return expected.casefold() in (value or "").casefold()


def add_group_totals(group: dict[str, object], row: ReceivedInventoryReportRow) -> None:
    group["total_lines"] += 1
    group["total_quantity_received"] += Decimal(str(row.quantity_received))
    group["total_received_value"] += Decimal(str(row.total_received_value))
