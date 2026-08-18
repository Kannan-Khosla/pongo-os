from __future__ import annotations

import csv
import hashlib
import hmac
import html
import json
import smtplib
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from email.message import EmailMessage
from io import BytesIO, StringIO
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.fulfillments import Fulfillment, FulfillmentLine
from app.models.inventory import InventoryItem, InventoryItemLocation, MovementType, StockMovement
from app.models.orders import Order, OrderItem
from app.models.receipts import Receipt, ReceiptItem
from app.models.reporting import ReportDelivery, ReportRun
from app.services.insights import build_insight
from app.services.woocommerce_subscriptions import build_subscription_data

REPORT_TIMEZONE = "America/Edmonton"
REPORT_TZ = ZoneInfo(REPORT_TIMEZONE)
DEFINITION_VERSION = 3
FAILED_ORDER_STATUSES = {"failed", "cancelled", "canceled", "refunded", "trash"}
TERMINAL_ORDER_STATUSES = FAILED_ORDER_STATUSES | {"completed", "closed", "fulfilled"}
SALES_RECOGNIZED_WOO_STATUSES = {"processing", "completed"}
RECEIVING_MOVEMENTS = {
    MovementType.receiving.value,
    MovementType.receive_direct.value,
    MovementType.direct_receiving.value,
}
USAGE_MOVEMENTS = {
    MovementType.pick_stock_reduction.value,
    MovementType.fulfillment.value,
    MovementType.fulfill_order.value,
}
TRANSFER_MOVEMENTS = {MovementType.transfer_in.value, MovementType.transfer_out.value}


REPORT_CATALOG = [
    {
        "key": "inventory-cost-category",
        "title": "Current Cost of Inventory by Category",
        "short_title": "Cost by Category",
        "category": "inventory",
        "description": "Current location stock valued at the current item unit cost, grouped by category.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "snapshot",
    },
    {
        "key": "inventory-cost-sku",
        "title": "Current Cost of Inventory by SKU",
        "short_title": "Cost by SKU",
        "category": "inventory",
        "description": "Current quantity, allocation, sellable stock, unit cost and extended cost per inventory item.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "snapshot",
    },
    {
        "key": "inventory-in-stock",
        "title": "Inventory in Stock",
        "short_title": "In Stock",
        "category": "inventory",
        "description": "All physical inventory with a positive current stock balance.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "snapshot",
    },
    {
        "key": "inventory-usage",
        "title": "Inventory Usage Summary",
        "short_title": "Usage Summary",
        "category": "inventory",
        "description": "Opening, received, used, adjusted, transferred and closing quantities over a selected period.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "unallocated-order-items",
        "title": "Unallocated Order Items",
        "short_title": "Unallocated Items",
        "category": "orders",
        "description": "Active order lines where ordered quantity remains unallocated.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "delivered-inventory",
        "title": "Delivered Inventory",
        "short_title": "Delivered Inventory",
        "category": "operations",
        "description": "Inventory posted through Pongo fulfillment during the selected period.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "received-inventory",
        "title": "Received Inventory",
        "short_title": "Received Inventory",
        "category": "operations",
        "description": "Committed receipt quantities and costs during the selected period.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "inventory-export",
        "title": "Inventory Export",
        "short_title": "Inventory Export",
        "category": "inventory",
        "description": "Location-level export of the current inventory snapshot.",
        "formats": ["csv", "google_sheets", "email"],
        "filters": ["warehouse", "inventory_location", "brand", "category", "sku"],
        "date_mode": "snapshot",
    },
    {
        "key": "inventory-forecast",
        "title": "Inventory Forecast",
        "short_title": "Inventory Forecast",
        "category": "intelligence",
        "description": "Demand velocity, estimated days remaining and stockout risk by SKU.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "incomplete-orders",
        "title": "Incomplete Orders",
        "short_title": "Incomplete Orders",
        "category": "orders",
        "description": "Allocated operational orders that have not been fully completed.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "status"],
        "date_mode": "range",
    },
    {
        "key": "order-summary",
        "title": "Order Summary",
        "short_title": "Order Summary",
        "category": "orders",
        "description": "Orders placed in the selected period, whether fulfilled or not.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "status", "customer_email"],
        "date_mode": "range",
    },
    {
        "key": "daily-item-orders",
        "title": "Daily Item Orders",
        "short_title": "Daily Item Orders",
        "category": "orders",
        "description": "Daily ordered, allocated and fulfilled quantities by SKU.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "detailed-customer-orders",
        "title": "Detailed Customer Orders",
        "short_title": "Customer Orders",
        "category": "orders",
        "description": "Customer, address, order, item, quantity and workflow detail.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "status", "customer_email", "sku"],
        "date_mode": "range",
    },
    {
        "key": "executive-weekly",
        "title": "Executive Weekly Report",
        "short_title": "Executive Weekly",
        "category": "executive",
        "description": "Revenue, inventory health, movement, fulfillment performance, forecast risks and priority actions.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "brand", "category"],
        "date_mode": "range",
    },
    {
        "key": "reorder-intelligence",
        "title": "Reorder Intelligence",
        "short_title": "Reorder Intelligence",
        "category": "intelligence",
        "description": "Demand, days of stock, suggested reorder quantity and slow/dead-stock warnings.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "po-received",
        "title": "PO Received",
        "short_title": "PO Received",
        "category": "operations",
        "description": "Receipt lines grouped by their PO or external reference number.",
        "formats": ["pdf", "csv", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "warehouse", "brand", "category", "sku"],
        "date_mode": "range",
    },
    {
        "key": "sales-by-sku",
        "title": "Sales by SKU",
        "short_title": "Sales Report",
        "category": "executive",
        "description": "SKU sales and quantities for a custom period with current inventory balances.",
        "formats": ["csv", "pdf", "google_sheets", "email"],
        "filters": ["start_date", "end_date", "brand", "category", "sku"],
        "date_mode": "range",
    },
]
REPORTS_BY_KEY = {report["key"]: report for report in REPORT_CATALOG}


def list_report_catalog(settings: Settings | None = None) -> dict[str, Any]:
    return {
        "reports": REPORT_CATALOG,
        "timezone": REPORT_TIMEZONE,
        "google_sheets_configured": bool(
            settings
            and settings.google_reports_client_id
            and settings.google_reports_client_secret
            and settings.google_reports_refresh_token
        ),
        "email_configured": bool(settings and settings.smtp_host and settings.smtp_from_email),
    }


def create_report_run(
    db: Session,
    report_key: str,
    raw_filters: dict[str, Any] | None,
    generated_by: str | None = "reporting-ui",
    *,
    row_page: int = 1,
    row_page_size: int = 100,
) -> dict[str, Any]:
    run = create_report_run_record(db, report_key, raw_filters, generated_by)
    persist_report_artifacts(run)
    db.commit()
    db.refresh(run)
    return report_run_to_dict(run, row_page=row_page, row_page_size=row_page_size)


def create_report_run_record(
    db: Session,
    report_key: str,
    raw_filters: dict[str, Any] | None,
    generated_by: str | None = "reporting-ui",
) -> ReportRun:
    definition = REPORTS_BY_KEY.get(report_key)
    if not definition:
        raise KeyError(report_key)
    filters = normalize_filters(raw_filters or {}, definition["date_mode"])
    payload = BUILDERS[report_key](db, filters)
    payload["data_quality"] = dedupe_warnings(payload.get("data_quality") or [])
    payload = {
        "report": definition,
        "definition_version": DEFINITION_VERSION,
        "timezone": REPORT_TIMEZONE,
        "filters": filters,
        **payload,
    }
    payload = decode_html_entities(payload)
    encoded_payload = jsonable_encoder(payload)
    data_hash = report_payload_hash(encoded_payload)
    run = ReportRun(
        report_key=report_key,
        title=definition["title"],
        definition_version=DEFINITION_VERSION,
        timezone=REPORT_TIMEZONE,
        filters=filters,
        payload=encoded_payload,
        row_count=len(encoded_payload.get("rows") or []),
        data_hash=data_hash,
        generated_by=generated_by,
    )
    db.add(run)
    db.flush()
    return run


def get_report_run(db: Session, run_id: str) -> ReportRun | None:
    run = db.get(ReportRun, run_id)
    if run is not None:
        verify_report_run(run)
    return run


def report_run_to_dict(
    run: ReportRun,
    *,
    row_page: int = 1,
    row_page_size: int = 100,
) -> dict[str, Any]:
    """Return a bounded preview without changing the immutable report evidence.

    The stored payload, evidence hash, and persisted CSV/PDF artifacts always
    contain the complete report. Pagination is applied only to the response
    copy returned to interactive clients.
    """
    verify_report_run(run)
    payload = dict(run.payload or {})
    all_rows = payload.get("rows") or []
    total = len(all_rows)
    total_pages = (total + row_page_size - 1) // row_page_size if total else 0
    effective_page = min(row_page, max(total_pages, 1))
    start = (effective_page - 1) * row_page_size
    rows = all_rows[start : start + row_page_size]
    payload["rows"] = rows
    return {
        "run_id": run.id,
        "generated_at": run.generated_at.isoformat() if run.generated_at else None,
        "generated_by": run.generated_by,
        "data_hash": run.data_hash,
        "row_count": run.row_count,
        **payload,
        "row_pagination": {
            "page": effective_page,
            "page_size": row_page_size,
            "total": total,
            "total_pages": total_pages,
            "returned_count": len(rows),
            "has_previous": effective_page > 1,
            "has_next": effective_page < total_pages,
        },
    }


class ReportIntegrityError(RuntimeError):
    pass


class ReportArtifactUnavailableError(RuntimeError):
    pass


def report_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(jsonable_encoder(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_report_run(run: ReportRun) -> None:
    actual = report_payload_hash(run.payload or {})
    if not hmac.compare_digest(actual, run.data_hash or ""):
        raise ReportIntegrityError(f"Stored report run {run.id} failed SHA-256 integrity verification.")


def persist_report_artifacts(run: ReportRun) -> None:
    csv_artifact = report_csv_bytes(run)
    pdf_artifact = report_pdf_bytes(run)
    run.csv_artifact = csv_artifact
    run.csv_artifact_hash = hashlib.sha256(csv_artifact).hexdigest()
    run.pdf_artifact = pdf_artifact
    run.pdf_artifact_hash = hashlib.sha256(pdf_artifact).hexdigest()


def report_artifact_bytes(run: ReportRun, artifact_format: str) -> bytes:
    verify_report_run(run)
    if artifact_format not in {"csv", "pdf"}:
        raise ValueError("Report artifact format must be CSV or PDF.")
    artifact = getattr(run, f"{artifact_format}_artifact")
    expected_hash = getattr(run, f"{artifact_format}_artifact_hash")
    if artifact is None or not expected_hash:
        raise ReportArtifactUnavailableError(
            "This report predates persisted downloads. Refresh the report to create a verified artifact."
        )
    actual_hash = hashlib.sha256(artifact).hexdigest()
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise ReportIntegrityError(
            f"Stored {artifact_format.upper()} artifact for report run {run.id} failed SHA-256 integrity verification."
        )
    return artifact


def normalize_filters(raw: dict[str, Any], date_mode: str) -> dict[str, Any]:
    clean = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in raw.items()
        if value not in (None, "", [])
    }
    today = datetime.now(REPORT_TZ).date()
    if date_mode == "range":
        start = parse_date(clean.get("start_date")) or today - timedelta(days=29)
        end = parse_date(clean.get("end_date")) or today
        if start > end:
            raise ValueError("Start date must be on or before end date.")
        clean["start_date"] = start.isoformat()
        clean["end_date"] = end.isoformat()
    return clean


def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise ValueError(f"Invalid date: {value}") from exc
    return None


def local_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(REPORT_TZ).date()


def in_date_range(value: datetime | date | None, filters: dict[str, Any]) -> bool:
    day = local_date(value)
    if day is None:
        return False
    start = parse_date(filters.get("start_date"))
    end = parse_date(filters.get("end_date"))
    return (start is None or day >= start) and (end is None or day <= end)


def D(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def qty(value: Any) -> str:
    return f"{D(value).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP):f}"


def money(value: Any) -> str:
    return f"{D(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):f}"


def number(value: Any) -> str:
    return f"{D(value).normalize():f}"


def percent(value: Any) -> str:
    return f"{D(value).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP):f}"


def text_matches(actual: Any, expected: Any, *, contains: bool = False) -> bool:
    if expected in (None, ""):
        return True
    left = str(actual or "").strip().casefold()
    right = str(expected).strip().casefold()
    return right in left if contains else left == right


def scoped_inventory_locations(
    db: Session, filters: dict[str, Any]
) -> list[tuple[InventoryItemLocation | None, InventoryItem]]:
    statement = (
        select(InventoryItemLocation, InventoryItem)
        .select_from(InventoryItem)
        .outerjoin(
            InventoryItemLocation,
            and_(
                InventoryItemLocation.inventory_item_id == InventoryItem.id,
                InventoryItemLocation.active.is_(True),
            ),
        )
        .where(InventoryItem.active.is_(True), InventoryItem.non_inventory.is_not(True))
    )
    rows = []
    for location, item in db.execute(statement).all():
        if not text_matches(location.warehouse if location else None, filters.get("warehouse")):
            continue
        if not text_matches(location.inventory_location if location else None, filters.get("inventory_location")):
            continue
        if not text_matches(item.brand, filters.get("brand")):
            continue
        if not text_matches(item.category, filters.get("category")):
            continue
        if not text_matches(item.sku, filters.get("sku"), contains=True):
            continue
        rows.append((location, item))
    return rows


def inventory_by_item(
    db: Session, filters: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[int, dict[str, Any]] = {}
    sku_counts: dict[str, set[int]] = defaultdict(set)
    for location, item in scoped_inventory_locations(db, filters):
        row = grouped.setdefault(
            item.id,
            {
                "item_id": item.id,
                "sku": item.sku or "",
                "barcode": item.barcode or "",
                "name": item.woo_name or item.description or "Unnamed item",
                "brand": item.brand or "Unspecified",
                "category": item.category or "Uncategorized",
                "unit_cost": item.unit_cost,
                "sales_price": item.sales_price,
                "in_stock": Decimal("0"),
                "allocated": Decimal("0"),
                "sellable": Decimal("0"),
                "on_order": Decimal("0"),
                "par_level": D(item.par_level),
                "lead_time_days": item.default_lead_time_days or 7,
                "locations": [],
            },
        )
        if location is not None:
            row["in_stock"] += D(location.in_stock)
            row["allocated"] += D(location.allocated)
            row["sellable"] += D(location.sellable)
            row["on_order"] += D(location.on_order)
            row["locations"].append(
                {
                    "warehouse": location.warehouse or "",
                    "inventory_location": location.inventory_location or "",
                    "in_stock": D(location.in_stock),
                    "allocated": D(location.allocated),
                    "sellable": D(location.sellable),
                }
            )
        if item.sku:
            sku_counts[item.sku.strip().casefold()].add(item.id)
    warnings = []
    missing_cost = sum(1 for row in grouped.values() if not positive_cost(row["unit_cost"]))
    locationless = sum(1 for row in grouped.values() if not row["locations"])
    duplicate_records = sum(max(0, len(ids) - 1) for ids in sku_counts.values())
    if missing_cost:
        warnings.append(
            quality_warning(
                "missing_cost",
                "Inventory cost is incomplete",
                f"{missing_cost} inventory item(s) have no positive unit cost and are excluded from valued totals.",
                missing_cost,
            )
        )
    if locationless:
        warnings.append(
            quality_warning(
                "locationless_inventory",
                "Inventory location is missing",
                f"{locationless} active inventory item(s) have no active location row and are shown with zero scoped stock.",
                locationless,
            )
        )
    if duplicate_records:
        warnings.append(
            quality_warning(
                "duplicate_sku",
                "Duplicate SKU records",
                f"{duplicate_records} additional inventory record(s) share a SKU. They remain separate to avoid hiding physical stock.",
                duplicate_records,
            )
        )
    for row in grouped.values():
        key = (row["sku"] or "").strip().casefold()
        row["duplicate_sku"] = bool(key and len(sku_counts[key]) > 1)
    return list(grouped.values()), warnings


def positive_cost(value: Any) -> bool:
    return value is not None and D(value) > 0


def quality_warning(code: str, title: str, message: str, count: int | None = None) -> dict[str, Any]:
    return {"code": code, "severity": "warning", "title": title, "message": message, "count": count}


def column(key: str, label: str, kind: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "type": kind}


def metric(key: str, label: str, value: Any, kind: str = "number", detail: str | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "type": kind, "detail": detail}


def chart(
    title: str,
    rows: list[dict[str, Any]],
    category_key: str,
    value_key: str,
    kind: str = "bar",
) -> dict[str, Any]:
    return {
        "title": title,
        "type": kind,
        "category_key": category_key,
        "value_key": value_key,
        "rows": rows,
    }


def insight(
    severity: str,
    title: str,
    evidence: str,
    action: str,
    href: str | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "action": action,
        "href": href,
    }


def build_inventory_cost_category(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    items, warnings = inventory_by_item(db, filters)
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item["category"]
        group = groups.setdefault(
            key,
            {
                "category": key,
                "item_ids": set(),
                "in_stock": Decimal("0"),
                "allocated": Decimal("0"),
                "sellable": Decimal("0"),
                "inventory_cost": Decimal("0"),
                "missing_cost_items": 0,
            },
        )
        group["item_ids"].add(item["item_id"])
        group["in_stock"] += item["in_stock"]
        group["allocated"] += item["allocated"]
        group["sellable"] += item["sellable"]
        if not positive_cost(item["unit_cost"]):
            group["missing_cost_items"] += 1
        else:
            group["inventory_cost"] += item["in_stock"] * D(item["unit_cost"])
    rows = [
        {
            "category": group["category"],
            "sku_count": len(group["item_ids"]),
            "in_stock": qty(group["in_stock"]),
            "allocated": qty(group["allocated"]),
            "sellable": qty(group["sellable"]),
            "inventory_cost": money(group["inventory_cost"]),
            "missing_cost_items": group["missing_cost_items"],
        }
        for group in groups.values()
    ]
    rows.sort(key=lambda row: D(row["inventory_cost"]), reverse=True)
    total_cost = sum((D(row["inventory_cost"]) for row in rows), Decimal("0"))
    return {
        "kpis": [
            metric("inventory_cost", "Inventory cost", money(total_cost), "currency"),
            metric("units", "Units in stock", qty(sum((item["in_stock"] for item in items), Decimal("0"))), "quantity"),
            metric("categories", "Categories", str(len(rows))),
            metric("missing_cost", "Items missing cost", str(sum(row["missing_cost_items"] for row in rows))),
        ],
        "charts": [chart("Inventory value by category", rows[:12], "category", "inventory_cost")],
        "columns": [
            column("category", "Category"),
            column("sku_count", "Items", "integer"),
            column("in_stock", "In stock", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("sellable", "Sellable", "quantity"),
            column("inventory_cost", "Inventory cost", "currency"),
            column("missing_cost_items", "Missing cost", "integer"),
        ],
        "rows": rows,
        "insights": valuation_insights(items, total_cost),
        "data_quality": warnings,
        "definitions": [
            "Inventory cost equals current location in-stock quantity multiplied by the current item unit cost.",
            "Items without unit cost remain visible but do not contribute to valued totals.",
        ],
    }


def build_inventory_cost_sku(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    items, warnings = inventory_by_item(db, filters)
    rows = []
    for item in items:
        extended = item["in_stock"] * D(item["unit_cost"]) if positive_cost(item["unit_cost"]) else None
        rows.append(
            {
                "item_id": item["item_id"],
                "sku": item["sku"],
                "name": item["name"],
                "brand": item["brand"],
                "category": item["category"],
                "in_stock": qty(item["in_stock"]),
                "allocated": qty(item["allocated"]),
                "sellable": qty(item["sellable"]),
                "unit_cost": money(item["unit_cost"]) if positive_cost(item["unit_cost"]) else None,
                "inventory_cost": None if extended is None else money(extended),
                "location_count": len(item["locations"]),
                "duplicate_sku": item["duplicate_sku"],
            }
        )
    rows.sort(key=lambda row: (row["sku"] or "", row["item_id"]))
    total_cost = sum((D(row["inventory_cost"]) for row in rows if row["inventory_cost"] is not None), Decimal("0"))
    return {
        "kpis": [
            metric("inventory_cost", "Inventory cost", money(total_cost), "currency"),
            metric("items", "Inventory items", str(len(rows))),
            metric("units", "Units in stock", qty(sum((item["in_stock"] for item in items), Decimal("0"))), "quantity"),
            metric("missing_cost", "Items missing cost", str(sum(1 for item in items if not positive_cost(item["unit_cost"])))),
        ],
        "charts": [chart("Highest inventory value", sorted([row for row in rows if row["inventory_cost"]], key=lambda row: D(row["inventory_cost"]), reverse=True)[:12], "sku", "inventory_cost")],
        "columns": [
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("in_stock", "In stock", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("sellable", "Sellable", "quantity"),
            column("unit_cost", "Unit cost", "currency"),
            column("inventory_cost", "Inventory cost", "currency"),
            column("location_count", "Locations", "integer"),
            column("duplicate_sku", "Duplicate SKU", "boolean"),
        ],
        "rows": rows,
        "insights": valuation_insights(items, total_cost),
        "data_quality": warnings,
        "definitions": [
            "Each inventory record remains separate even when a duplicate SKU exists.",
            "Inventory cost equals current in-stock quantity multiplied by current unit cost.",
        ],
    }


def valuation_insights(items: list[dict[str, Any]], total_cost: Decimal) -> list[dict[str, Any]]:
    ranked = sorted(
        [item for item in items if positive_cost(item["unit_cost"])],
        key=lambda item: item["in_stock"] * D(item["unit_cost"]),
        reverse=True,
    )
    findings = []
    if ranked and total_cost:
        top = ranked[0]
        value = top["in_stock"] * D(top["unit_cost"])
        share = value / total_cost * Decimal("100")
        findings.append(
            insight(
                "info",
                f"{top['sku'] or top['name']} carries the highest inventory value",
                f"{money(value)} represents {percent(share)}% of the valued inventory in this report.",
                "Review its demand and storage exposure.",
                f"#/inventory/all?search={top['sku']}",
            )
        )
    missing = sum(1 for item in items if not positive_cost(item["unit_cost"]))
    if missing:
        findings.append(
            insight(
                "warning",
                "Valuation is incomplete",
                f"{missing} item(s) have no positive current unit cost.",
                "Complete missing costs before using the total for bookkeeping.",
                "#/inventory/all?data_quality=missing_cost",
            )
        )
    return findings


def build_inventory_in_stock(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    payload = build_inventory_cost_sku(db, filters)
    payload["rows"] = [row for row in payload["rows"] if D(row["in_stock"]) > 0]
    payload["kpis"][1] = metric("items", "Items in stock", str(len(payload["rows"])))
    payload["definitions"] = ["Includes inventory records with current physical in-stock quantity greater than zero."]
    return payload


def build_inventory_export(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    missing_cost = 0
    for location, item in scoped_inventory_locations(db, filters):
        if not positive_cost(item.unit_cost):
            missing_cost += 1
        in_stock = location.in_stock if location else 0
        allocated = location.allocated if location else 0
        sellable = location.sellable if location else 0
        on_order = location.on_order if location else 0
        rows.append(
            {
                "item_id": item.id,
                "sku": item.sku or "",
                "barcode": item.barcode or "",
                "name": item.woo_name or item.description or "",
                "brand": item.brand or "",
                "category": item.category or "",
                "warehouse": location.warehouse if location else "",
                "inventory_location": location.inventory_location if location else "",
                "in_stock": qty(in_stock),
                "allocated": qty(allocated),
                "sellable": qty(sellable),
                "on_order": qty(on_order),
                "unit_cost": money(item.unit_cost) if positive_cost(item.unit_cost) else None,
                "sales_price": None if item.sales_price is None else money(item.sales_price),
                "woo_product_id": item.woo_product_id,
                "woo_variation_id": item.woo_variation_id,
                "active": bool(item.active),
            }
        )
    rows.sort(key=lambda row: (row["sku"], row["warehouse"], row["inventory_location"]))
    return {
        "kpis": [
            metric("rows", "Location rows", str(len(rows))),
            metric("units", "Units in stock", qty(sum((D(row["in_stock"]) for row in rows), Decimal("0"))), "quantity"),
            metric("sellable", "Sellable units", qty(sum((D(row["sellable"]) for row in rows), Decimal("0"))), "quantity"),
            metric("missing_cost", "Rows missing cost", str(missing_cost)),
        ],
        "charts": [],
        "columns": [
            column("sku", "SKU"),
            column("barcode", "Barcode"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("warehouse", "Warehouse"),
            column("inventory_location", "Location"),
            column("in_stock", "In stock", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("sellable", "Sellable", "quantity"),
            column("on_order", "On order", "quantity"),
            column("unit_cost", "Unit cost", "currency"),
            column("sales_price", "Sales price", "currency"),
            column("woo_product_id", "Woo product ID", "integer"),
            column("woo_variation_id", "Woo variation ID", "integer"),
            column("active", "Active", "boolean"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [quality_warning("missing_cost", "Cost data is incomplete", f"{missing_cost} row(s) have no unit cost.", missing_cost)] if missing_cost else [],
        "definitions": ["Location-level current inventory snapshot. This export does not mutate inventory or WooCommerce."],
    }


def scoped_orders(db: Session, filters: dict[str, Any]) -> list[Order]:
    orders = list(db.scalars(
        select(Order)
        .where(or_(Order.is_historical_snapshot.is_(False), Order.historical_source_present.is_(True)))
        .options(selectinload(Order.items))
    ).unique().all())
    scoped = []
    for order in orders:
        placed = order.placed_on or order.date_created or order.created_at
        if "start_date" in filters and not in_date_range(placed, filters):
            continue
        status = order_status(order)
        if filters.get("status") and not text_matches(status, filters["status"]):
            continue
        if filters.get("customer_email") and not text_matches(order.customer_email, filters["customer_email"], contains=True):
            continue
        scoped.append(order)
    return scoped


def order_status(order: Order) -> str:
    return str(order.local_status or order.status or order.woo_status or "unknown").strip().lower()


def order_day(order: Order) -> date | None:
    return local_date(order.placed_on or order.date_created or order.created_at)


def line_quantity(line: OrderItem) -> Decimal:
    return D(line.quantity_ordered or line.ordered_qty)


def line_allocated(line: OrderItem) -> Decimal:
    return D(line.quantity_allocated or line.allocated_qty)


def line_fulfilled(line: OrderItem) -> Decimal:
    return D(line.quantity_fulfilled or line.fulfilled_qty)


def line_matches_filters(line: OrderItem, filters: dict[str, Any]) -> bool:
    item = line.inventory_item
    return (
        text_matches(line.sku or (item.sku if item else None), filters.get("sku"), contains=True)
        and text_matches((item.brand if item else None) or line.brand, filters.get("brand"))
        and text_matches(item.category if item else None, filters.get("category"))
    )


def build_unallocated_items(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for order in scoped_orders(db, filters):
        if order.is_historical_snapshot or order_status(order) in TERMINAL_ORDER_STATUSES:
            continue
        for line in order.items:
            if not line_matches_filters(line, filters):
                continue
            unallocated = max(Decimal("0"), line_quantity(line) - line_allocated(line))
            if unallocated <= 0:
                continue
            item = line.inventory_item
            rows.append(
                {
                    "order_id": order.id,
                    "order_number": order.order_number or order.woo_order_number or str(order.id),
                    "placed_on": order_day(order).isoformat() if order_day(order) else "",
                    "customer": order.customer_name or "",
                    "sku": line.sku or (item.sku if item else ""),
                    "name": line.name or line.description or (item.woo_name if item else ""),
                    "brand": (item.brand if item else None) or line.brand or "",
                    "ordered": qty(line_quantity(line)),
                    "allocated": qty(line_allocated(line)),
                    "unallocated": qty(unallocated),
                    "current_sellable": qty(item.sellable if item else 0),
                    "exception": line.allocation_exception_reason or order.allocation_exception_reason or "",
                    "order_status": order_status(order),
                }
            )
    rows.sort(key=lambda row: (row["placed_on"], row["order_number"]))
    shortage = sum((D(row["unallocated"]) for row in rows), Decimal("0"))
    return {
        "kpis": [
            metric("lines", "Unallocated lines", str(len(rows))),
            metric("units", "Unallocated units", qty(shortage), "quantity"),
            metric("orders", "Affected orders", str(len({row["order_id"] for row in rows}))),
            metric("sellable", "Sellable against shortage", qty(sum((D(row["current_sellable"]) for row in rows), Decimal("0"))), "quantity"),
        ],
        "charts": [chart("Unallocated units by SKU", aggregate_chart_rows(rows, "sku", "unallocated"), "sku", "unallocated")],
        "columns": [
            column("order_number", "Order"),
            column("placed_on", "Placed", "date"),
            column("customer", "Customer"),
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("ordered", "Ordered", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("unallocated", "Unallocated", "quantity"),
            column("current_sellable", "Sellable now", "quantity"),
            column("order_status", "Status", "status"),
            column("exception", "Exception"),
        ],
        "rows": rows,
        "insights": [
            insight(
                "critical" if shortage else "success",
                "Allocation demand requires attention" if shortage else "No unallocated demand",
                f"{qty(shortage)} unit(s) remain unallocated across {len({row['order_id'] for row in rows})} order(s).",
                "Open the affected orders and resolve stock or mapping exceptions." if shortage else "No action required.",
                "#/orders/open",
            )
        ],
        "data_quality": [],
        "definitions": ["Unallocated quantity equals ordered quantity minus allocated quantity on active, non-terminal orders."],
    }


def build_incomplete_orders(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for order in scoped_orders(db, filters):
        if order.is_historical_snapshot or order_status(order) in TERMINAL_ORDER_STATUSES:
            continue
        ordered = sum((line_quantity(line) for line in order.items), Decimal("0"))
        allocated = sum((line_allocated(line) for line in order.items), Decimal("0"))
        picked = sum((D(line.quantity_picked or line.picked_qty) for line in order.items), Decimal("0"))
        fulfilled = sum((line_fulfilled(line) for line in order.items), Decimal("0"))
        if (allocated <= 0 and picked <= 0) or fulfilled >= ordered:
            continue
        rows.append(
            {
                "order_id": order.id,
                "order_number": order.order_number or order.woo_order_number or str(order.id),
                "placed_on": order_day(order).isoformat() if order_day(order) else "",
                "customer": order.customer_name or "",
                "status": order_status(order),
                "allocation_status": order.allocation_status or "",
                "pick_status": order.pick_status or "",
                "ordered": qty(ordered),
                "allocated": qty(allocated),
                "picked": qty(picked),
                "fulfilled": qty(fulfilled),
                "remaining": qty(max(Decimal("0"), ordered - fulfilled)),
                "total": money(order.total),
                "exception": order.allocation_exception_reason or "",
            }
        )
    rows.sort(key=lambda row: row["placed_on"])
    return {
        "kpis": [
            metric("orders", "Incomplete orders", str(len(rows))),
            metric("remaining", "Units remaining", qty(sum((D(row["remaining"]) for row in rows), Decimal("0"))), "quantity"),
            metric("picked", "Units picked", qty(sum((D(row["picked"]) for row in rows), Decimal("0"))), "quantity"),
            metric("value", "Order value", money(sum((D(row["total"]) for row in rows), Decimal("0"))), "currency"),
        ],
        "charts": [chart("Remaining units by order", rows[:15], "order_number", "remaining")],
        "columns": [
            column("order_number", "Order"),
            column("placed_on", "Placed", "date"),
            column("customer", "Customer"),
            column("status", "Status", "status"),
            column("allocation_status", "Allocation", "status"),
            column("pick_status", "Picking", "status"),
            column("ordered", "Ordered", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("picked", "Picked", "quantity"),
            column("fulfilled", "Fulfilled", "quantity"),
            column("remaining", "Remaining", "quantity"),
            column("total", "Order value", "currency"),
            column("exception", "Exception"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [],
        "definitions": ["Includes active orders with allocated or picked quantity greater than zero and fulfilled quantity below ordered quantity."],
    }


def build_order_summary(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    unallocated_units = Decimal("0")
    for order in scoped_orders(db, filters):
        ordered = sum((line_quantity(line) for line in order.items), Decimal("0"))
        allocated = sum((line_allocated(line) for line in order.items), Decimal("0"))
        picked = sum((D(line.quantity_picked or line.picked_qty) for line in order.items), Decimal("0"))
        fulfilled = sum((line_fulfilled(line) for line in order.items), Decimal("0"))
        unallocated = Decimal("0") if order.is_historical_snapshot or order_status(order) in TERMINAL_ORDER_STATUSES else max(Decimal("0"), ordered - max(allocated, picked, fulfilled))
        unallocated_units += unallocated
        rows.append(
            {
                "order_id": order.id,
                "order_number": order.order_number or order.woo_order_number or str(order.id),
                "placed_on": order_day(order).isoformat() if order_day(order) else "",
                "customer": order.customer_name or "",
                "customer_email": order.customer_email or "",
                "status": order_status(order),
                "woo_status": order.woo_status or "",
                "items": len(order.items),
                "units_ordered": qty(ordered),
                "units_allocated": qty(allocated),
                "units_fulfilled": qty(fulfilled),
                "units_unallocated": qty(unallocated),
                "subtotal": money(order.subtotal),
                "discount": money(order.discount_total),
                "shipping": money(order.shipping_total),
                "tax": money(order.tax_total),
                "total": money(order.total),
                "currency": order.currency or "CAD",
            }
        )
    rows.sort(key=lambda row: row["placed_on"], reverse=True)
    status_rows = aggregate_count_rows(rows, "status")
    return {
        "kpis": [
            metric("orders", "Orders placed", str(len(rows))),
            metric("order_total", "Gross order total", money(sum((D(row["total"]) for row in rows), Decimal("0"))), "currency"),
            metric("units", "Units ordered", qty(sum((D(row["units_ordered"]) for row in rows), Decimal("0"))), "quantity"),
            metric("unallocated", "Unallocated units", qty(unallocated_units), "quantity"),
        ],
        "charts": [chart("Orders by status", status_rows, "status", "count", "donut")],
        "columns": [
            column("order_number", "Order"),
            column("placed_on", "Placed", "date"),
            column("customer", "Customer"),
            column("customer_email", "Email"),
            column("status", "Local status", "status"),
            column("woo_status", "Woo status", "status"),
            column("items", "Lines", "integer"),
            column("units_ordered", "Ordered", "quantity"),
            column("units_allocated", "Allocated", "quantity"),
            column("units_fulfilled", "Fulfilled", "quantity"),
            column("units_unallocated", "Unallocated", "quantity"),
            column("subtotal", "Subtotal", "currency"),
            column("discount", "Discount", "currency"),
            column("shipping", "Shipping", "currency"),
            column("tax", "Tax", "currency"),
            column("total", "Total", "currency"),
            column("currency", "Currency"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [],
        "definitions": ["Includes every order placed in the selected period, regardless of fulfillment status. Unallocated demand is reported only for active orders."],
    }


def build_daily_item_orders(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for order in scoped_orders(db, filters):
        day = order_day(order)
        if not day:
            continue
        for line in order.items:
            if not line_matches_filters(line, filters):
                continue
            item = line.inventory_item
            sku = line.sku or (item.sku if item else "") or f"line-{line.id}"
            key = (day.isoformat(), sku)
            row = groups.setdefault(
                key,
                {
                    "date": day.isoformat(),
                    "sku": sku,
                    "name": line.name or line.description or (item.woo_name if item else ""),
                    "brand": (item.brand if item else None) or line.brand or "",
                    "category": item.category if item else "",
                    "orders": set(),
                    "ordered": Decimal("0"),
                    "allocated": Decimal("0"),
                    "fulfilled": Decimal("0"),
                    "net_sales": Decimal("0"),
                },
            )
            row["orders"].add(order.id)
            row["ordered"] += line_quantity(line)
            row["allocated"] += line_allocated(line)
            row["fulfilled"] += line_fulfilled(line)
            if order_status(order) not in FAILED_ORDER_STATUSES:
                row["net_sales"] += D(line.line_total or line.total_price)
    rows = [
        {
            **{key: value for key, value in row.items() if key not in {"orders", "ordered", "allocated", "fulfilled", "net_sales"}},
            "order_count": len(row["orders"]),
            "ordered": qty(row["ordered"]),
            "allocated": qty(row["allocated"]),
            "fulfilled": qty(row["fulfilled"]),
            "outstanding": qty(max(Decimal("0"), row["ordered"] - row["fulfilled"])),
            "net_sales": money(row["net_sales"]),
        }
        for row in groups.values()
    ]
    rows.sort(key=lambda row: (row["date"], row["sku"]), reverse=True)
    daily = aggregate_chart_rows(rows, "date", "ordered")
    return {
        "kpis": [
            metric("days", "Days reported", str(len({row["date"] for row in rows}))),
            metric("units", "Units ordered", qty(sum((D(row["ordered"]) for row in rows), Decimal("0"))), "quantity"),
            metric("fulfilled", "Units fulfilled", qty(sum((D(row["fulfilled"]) for row in rows), Decimal("0"))), "quantity"),
            metric("sales", "Net merchandise sales", money(sum((D(row["net_sales"]) for row in rows), Decimal("0"))), "currency"),
        ],
        "charts": [chart("Units ordered by day", daily, "date", "ordered", "line")],
        "columns": [
            column("date", "Date", "date"),
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("order_count", "Orders", "integer"),
            column("ordered", "Ordered", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("fulfilled", "Fulfilled", "quantity"),
            column("outstanding", "Outstanding", "quantity"),
            column("net_sales", "Net sales", "currency"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [],
        "definitions": ["Sales excludes failed, cancelled and refunded orders. Ordered quantities include all statuses."],
    }


def build_detailed_customer_orders(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for order in scoped_orders(db, filters):
        for line in order.items:
            if not line_matches_filters(line, filters):
                continue
            item = line.inventory_item
            rows.append(
                {
                    "order_number": order.order_number or order.woo_order_number or str(order.id),
                    "placed_on": order_day(order).isoformat() if order_day(order) else "",
                    "status": order_status(order),
                    "customer": order.customer_name or "",
                    "email": order.customer_email or "",
                    "phone": order.customer_phone or order.shipping_phone or order.billing_phone or "",
                    "company": order.company or "",
                    "address": ", ".join(part for part in [order.shipping_address_1, order.shipping_address_2, order.shipping_city, order.shipping_state, order.shipping_zip] if part),
                    "sku": line.sku or (item.sku if item else ""),
                    "name": line.name or line.description or (item.woo_name if item else ""),
                    "brand": (item.brand if item else None) or line.brand or "",
                    "ordered": qty(line_quantity(line)),
                    "allocated": qty(line_allocated(line)),
                    "picked": qty(line.quantity_picked or line.picked_qty),
                    "fulfilled": qty(line_fulfilled(line)),
                    "line_total": money(line.line_total or line.total_price),
                    "currency": order.currency or "CAD",
                }
            )
    rows.sort(key=lambda row: (row["placed_on"], row["order_number"]), reverse=True)
    return {
        "kpis": [
            metric("orders", "Orders", str(len({row["order_number"] for row in rows}))),
            metric("customers", "Customers", str(len({row["email"].casefold() for row in rows if row["email"]}))),
            metric("lines", "Order lines", str(len(rows))),
            metric("line_total", "Line total", money(sum((D(row["line_total"]) for row in rows), Decimal("0"))), "currency"),
        ],
        "charts": [],
        "columns": [
            column("order_number", "Order"),
            column("placed_on", "Placed", "date"),
            column("status", "Status", "status"),
            column("customer", "Customer"),
            column("email", "Email"),
            column("phone", "Phone"),
            column("company", "Company"),
            column("address", "Shipping address"),
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("ordered", "Ordered", "quantity"),
            column("allocated", "Allocated", "quantity"),
            column("picked", "Picked", "quantity"),
            column("fulfilled", "Fulfilled", "quantity"),
            column("line_total", "Line total", "currency"),
            column("currency", "Currency"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [],
        "definitions": ["Contains normalized customer and order fields stored in Pongo. Raw WooCommerce payload fields are not exported."],
    }


def received_rows(db: Session, filters: dict[str, Any]) -> list[dict[str, Any]]:
    statement = (
        select(ReceiptItem, Receipt, InventoryItem)
        .join(Receipt, ReceiptItem.receipt_id == Receipt.id)
        .join(InventoryItem, ReceiptItem.inventory_item_id == InventoryItem.id, isouter=True)
    )
    rows = []
    for line, receipt, item in db.execute(statement).all():
        received_on = line.received_date or receipt.received_date or local_date(line.created_at)
        if not in_date_range(received_on, filters):
            continue
        if not text_matches(line.warehouse, filters.get("warehouse")):
            continue
        if not text_matches(line.inventory_location_name, filters.get("inventory_location")):
            continue
        if not text_matches((item.brand if item else None) or line.brand, filters.get("brand")):
            continue
        if not text_matches((item.category if item else None) or line.category, filters.get("category")):
            continue
        if not text_matches(line.sku or (item.sku if item else None), filters.get("sku"), contains=True):
            continue
        quantity_received = D(line.quantity_received or line.quantity)
        unit_cost = line.unit_cost if positive_cost(line.unit_cost) else None
        total_cost = line.unit_cost_total if positive_cost(line.unit_cost_total) else None
        if unit_cost is None and total_cost is not None and quantity_received > 0:
            unit_cost = D(total_cost) / quantity_received
        if total_cost is None and unit_cost is not None:
            total_cost = quantity_received * D(unit_cost)
        rows.append(
            {
                "receipt_number": receipt.receipt_number,
                "po_reference": line.po_or_receipt_number or receipt.reference_number or "",
                "received_date": received_on.isoformat() if received_on else "",
                "sku": line.sku or (item.sku if item else ""),
                "name": line.name or line.description or (item.woo_name if item else ""),
                "brand": (item.brand if item else None) or line.brand or "",
                "category": (item.category if item else None) or line.category or "",
                "warehouse": line.warehouse or receipt.warehouse or "",
                "inventory_location": line.inventory_location_name or "",
                "quantity_received": qty(quantity_received),
                "unit_cost": None if unit_cost is None else money(unit_cost),
                "total_cost": None if total_cost is None else money(total_cost),
                "received_by": receipt.received_by or receipt.created_by or "",
                "status": receipt.status or line.line_status or "",
            }
        )
    rows.sort(key=lambda row: (row["received_date"], row["receipt_number"]), reverse=True)
    return rows


def build_received_inventory(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    rows = received_rows(db, filters)
    missing_cost = sum(1 for row in rows if row["total_cost"] is None)
    return {
        "kpis": [
            metric("receipts", "Receipts", str(len({row["receipt_number"] for row in rows}))),
            metric("units", "Units received", qty(sum((D(row["quantity_received"]) for row in rows), Decimal("0"))), "quantity"),
            metric("cost", "Received cost", money(sum((D(row["total_cost"]) for row in rows if row["total_cost"] is not None), Decimal("0"))), "currency"),
            metric("skus", "SKUs received", str(len({row["sku"] for row in rows if row["sku"]}))),
        ],
        "charts": [chart("Units received by date", aggregate_chart_rows(rows, "received_date", "quantity_received"), "received_date", "quantity_received", "line")],
        "columns": [
            column("receipt_number", "Receipt"),
            column("po_reference", "PO / reference"),
            column("received_date", "Received", "date"),
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("warehouse", "Warehouse"),
            column("inventory_location", "Location"),
            column("quantity_received", "Quantity", "quantity"),
            column("unit_cost", "Unit cost", "currency"),
            column("total_cost", "Total cost", "currency"),
            column("received_by", "Received by"),
            column("status", "Status", "status"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [quality_warning("missing_receipt_cost", "Received cost is incomplete", f"{missing_cost} receipt line(s) have no cost.", missing_cost)] if missing_cost else [],
        "definitions": ["Uses committed receipt records and their effective received date."],
    }


def build_po_received(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    payload = build_received_inventory(db, filters)
    no_reference = sum(1 for row in payload["rows"] if not row["po_reference"])
    payload["kpis"][0] = metric("references", "PO / references", str(len({row["po_reference"] for row in payload["rows"] if row["po_reference"]})))
    if no_reference:
        payload["data_quality"].append(
            quality_warning(
                "missing_po_reference",
                "PO/reference is missing",
                f"{no_reference} received line(s) cannot be grouped to a PO/reference.",
                no_reference,
            )
        )
    payload["definitions"] = [
        "This is a receipt-reference report, not purchase-order reconciliation.",
        "Pongo does not currently store ordered PO quantities or PO remaining balances.",
    ]
    return payload


def build_delivered_inventory(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    statement = (
        select(FulfillmentLine, Fulfillment, Order, InventoryItem)
        .join(Fulfillment, FulfillmentLine.fulfillment_id == Fulfillment.id)
        .join(Order, FulfillmentLine.order_id == Order.id)
        .join(InventoryItem, FulfillmentLine.item_id == InventoryItem.id)
    )
    rows = []
    for line, fulfillment, order, item in db.execute(statement).all():
        delivered_at = fulfillment.posted_at or fulfillment.created_at
        if fulfillment.status != "posted" or not in_date_range(delivered_at, filters):
            continue
        if not text_matches(line.warehouse, filters.get("warehouse")):
            continue
        if not text_matches(line.inventory_location, filters.get("inventory_location")):
            continue
        if not text_matches(item.brand, filters.get("brand")):
            continue
        if not text_matches(item.category, filters.get("category")):
            continue
        if not text_matches(line.sku or item.sku, filters.get("sku"), contains=True):
            continue
        unit_cost = line.unit_cost if positive_cost(line.unit_cost) else None
        cost = D(line.quantity_to_fulfill) * D(unit_cost) if unit_cost is not None else None
        rows.append(
            {
                "fulfillment_number": fulfillment.fulfillment_number,
                "fulfilled_date": local_date(delivered_at).isoformat() if local_date(delivered_at) else "",
                "order_number": fulfillment.woo_order_number or order.order_number or str(order.id),
                "customer": order.customer_name or "",
                "sku": line.sku or item.sku or "",
                "name": line.description or item.woo_name or item.description or "",
                "brand": item.brand or "",
                "category": item.category or "",
                "warehouse": line.warehouse or "",
                "inventory_location": line.inventory_location or "",
                "quantity_delivered": qty(line.quantity_to_fulfill),
                "unit_cost": None if unit_cost is None else money(unit_cost),
                "delivered_cost": None if cost is None else money(cost),
                "created_by": fulfillment.created_by or "",
            }
        )
    rows.sort(key=lambda row: (row["fulfilled_date"], row["fulfillment_number"]), reverse=True)
    return {
        "kpis": [
            metric("fulfillments", "Fulfillments", str(len({row["fulfillment_number"] for row in rows}))),
            metric("orders", "Orders", str(len({row["order_number"] for row in rows}))),
            metric("units", "Units delivered", qty(sum((D(row["quantity_delivered"]) for row in rows), Decimal("0"))), "quantity"),
            metric("cost", "Delivered inventory cost", money(sum((D(row["delivered_cost"]) for row in rows if row["delivered_cost"] is not None), Decimal("0"))), "currency"),
        ],
        "charts": [chart("Units delivered by date", aggregate_chart_rows(rows, "fulfilled_date", "quantity_delivered"), "fulfilled_date", "quantity_delivered", "line")],
        "columns": [
            column("fulfillment_number", "Fulfillment"),
            column("fulfilled_date", "Fulfilled", "date"),
            column("order_number", "Order"),
            column("customer", "Customer"),
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("warehouse", "Warehouse"),
            column("inventory_location", "Location"),
            column("quantity_delivered", "Quantity", "quantity"),
            column("unit_cost", "Unit cost", "currency"),
            column("delivered_cost", "Delivered cost", "currency"),
            column("created_by", "Posted by"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [
            quality_warning(
                "fulfillment_not_carrier_delivery",
                "Delivery definition",
                "Pongo currently records fulfillment posting, not physical carrier/customer delivery confirmation.",
            ),
            *(
                [quality_warning("missing_fulfillment_cost", "Delivered cost is incomplete", f"{sum(1 for row in rows if row['delivered_cost'] is None)} fulfillment line(s) have no historical unit cost.")]
                if any(row["delivered_cost"] is None for row in rows)
                else []
            ),
        ],
        "definitions": ["Delivered means inventory posted through a completed Pongo fulfillment. Cost uses the unit cost frozen on that fulfillment line."],
    }


def build_inventory_usage(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    items, warnings = inventory_by_item(db, filters)
    item_map = {item["item_id"]: item for item in items}
    movement_groups: dict[int, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    all_movements = list(db.scalars(select(StockMovement).order_by(StockMovement.created_at.asc())).all())
    end = parse_date(filters["end_date"])
    missing_scope_metadata = 0
    for movement in all_movements:
        if movement.inventory_item_id not in item_map:
            continue
        day = local_date(movement.created_at)
        if day is None:
            continue
        if filters.get("warehouse"):
            if not movement.warehouse:
                missing_scope_metadata += 1
                continue
            if not text_matches(movement.warehouse, filters["warehouse"]):
                continue
        if filters.get("inventory_location"):
            if not movement.inventory_location_name:
                missing_scope_metadata += 1
                continue
            if not text_matches(movement.inventory_location_name, filters["inventory_location"]):
                continue
        value = movement.movement_type.value if hasattr(movement.movement_type, "value") else str(movement.movement_type)
        change = D(movement.quantity_change)
        if day > end:
            movement_groups[movement.inventory_item_id]["after_period"] += change
            continue
        if not in_date_range(day, filters):
            continue
        movement_groups[movement.inventory_item_id]["net"] += change
        if value in RECEIVING_MOVEMENTS and change > 0:
            movement_groups[movement.inventory_item_id]["received"] += change
        elif value in USAGE_MOVEMENTS and change < 0:
            movement_groups[movement.inventory_item_id]["used"] += -change
        elif value in TRANSFER_MOVEMENTS:
            movement_groups[movement.inventory_item_id]["transfers"] += change
        else:
            movement_groups[movement.inventory_item_id]["adjustments"] += change
    rows = []
    for item in items:
        values = movement_groups[item["item_id"]]
        closing = item["in_stock"] - values["after_period"]
        opening = closing - values["net"]
        rows.append(
            {
                "sku": item["sku"],
                "name": item["name"],
                "brand": item["brand"],
                "category": item["category"],
                "opening_stock": qty(opening),
                "received": qty(values["received"]),
                "used": qty(values["used"]),
                "adjustments": qty(values["adjustments"]),
                "net_transfers": qty(values["transfers"]),
                "closing_stock": qty(closing),
                "net_change": qty(values["net"]),
            }
        )
    rows.sort(key=lambda row: D(row["used"]), reverse=True)
    return {
        "kpis": [
            metric("opening", "Opening stock", qty(sum((D(row["opening_stock"]) for row in rows), Decimal("0"))), "quantity"),
            metric("received", "Received", qty(sum((D(row["received"]) for row in rows), Decimal("0"))), "quantity"),
            metric("used", "Used", qty(sum((D(row["used"]) for row in rows), Decimal("0"))), "quantity"),
            metric("closing", "Closing stock", qty(sum((D(row["closing_stock"]) for row in rows), Decimal("0"))), "quantity"),
        ],
        "charts": [chart("Highest inventory usage", rows[:12], "sku", "used")],
        "columns": [
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("opening_stock", "Opening", "quantity"),
            column("received", "Received", "quantity"),
            column("used", "Used", "quantity"),
            column("adjustments", "Adjustments", "quantity"),
            column("net_transfers", "Net transfers", "quantity"),
            column("closing_stock", "Closing", "quantity"),
            column("net_change", "Net change", "quantity"),
        ],
        "rows": rows,
        "insights": [],
        "data_quality": [
            *warnings,
            *(
                [quality_warning("movement_scope_metadata", "Historical movement scope is incomplete", f"{missing_scope_metadata} movement(s) lacked warehouse/location metadata and were excluded from the scoped usage report.", missing_scope_metadata)]
                if missing_scope_metadata
                else []
            ),
        ],
        "definitions": [
            "Opening and closing balances are reconstructed from the current balance and audited stock movements.",
            "Used quantity includes pick stock reductions and direct fulfillment stock reductions.",
            "Opening balances are classified as adjustments, not received inventory.",
        ],
    }


def forecast_payload(db: Session, filters: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    params = {**filters, "limit": 1000, "offset": 0}
    result = build_insight(db, "inventory-forecasting", params).model_dump(mode="json")
    rows = result.get("rows") or []
    warnings = result.get("data_quality") or []
    return rows, warnings


def build_inventory_forecast(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    source_rows, warnings = forecast_payload(db, filters)
    rows = []
    for row in source_rows:
        rows.append(
            {
                "sku": row.get("sku") or "",
                "name": row.get("product_title") or row.get("description") or "",
                "brand": row.get("brand") or "",
                "category": row.get("category") or "",
                "sellable": qty(row.get("current_sellable")),
                "sold_7d": qty(row.get("units_sold_7d")),
                "sold_30d": qty(row.get("units_sold_30d")),
                "sold_60d": qty(row.get("units_sold_60d")),
                "sold_90d": qty(row.get("units_sold_90d")),
                "daily_velocity": None if row.get("daily_velocity") is None else qty(row.get("daily_velocity")),
                "days_of_stock": None if row.get("days_of_stock_left") is None else number(row.get("days_of_stock_left")),
                "lead_time_days": row.get("lead_time_days"),
                "forecast_30d": None if row.get("forecasted_30_day_demand") is None else qty(row.get("forecasted_30_day_demand")),
                "suggested_reorder": None if row.get("suggested_reorder_qty") is None else qty(row.get("suggested_reorder_qty")),
                "risk": row.get("risk_level") or "insufficient_history",
                "forecast_status": row.get("forecast_status") or "",
            }
        )
    high_risk = [row for row in rows if row["risk"] == "high"]
    overstock = [row for row in rows if row["risk"] == "overstock"]
    return {
        "kpis": [
            metric("items", "Items forecast", str(len(rows))),
            metric("high_risk", "High stockout risk", str(len(high_risk))),
            metric("overstock", "Overstock risk", str(len(overstock))),
            metric("history", "Insufficient history", str(sum(1 for row in rows if row["forecast_status"] == "insufficient_history"))),
        ],
        "charts": [chart("Days of stock remaining", [row for row in rows if row["days_of_stock"] is not None][:15], "sku", "days_of_stock")],
        "columns": [
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("sellable", "Sellable", "quantity"),
            column("sold_7d", "Sold 7d", "quantity"),
            column("sold_30d", "Sold 30d", "quantity"),
            column("sold_60d", "Sold 60d", "quantity"),
            column("sold_90d", "Sold 90d", "quantity"),
            column("daily_velocity", "Daily velocity", "quantity"),
            column("days_of_stock", "Days of stock", "number"),
            column("lead_time_days", "Lead time", "integer"),
            column("forecast_30d", "Forecast 30d", "quantity"),
            column("suggested_reorder", "Suggested reorder", "quantity"),
            column("risk", "Risk", "status"),
            column("forecast_status", "Forecast status", "status"),
        ],
        "rows": rows,
        "insights": forecast_insights(rows),
        "data_quality": warnings,
        "definitions": [
            "Version 1 uses recent successful-order velocity and current sellable stock.",
            "Items without recent sales are marked insufficient history rather than assigned a fabricated forecast.",
        ],
    }


def build_reorder_intelligence(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    payload = build_inventory_forecast(db, filters)
    inventory, inventory_warnings = inventory_by_item(db, filters)
    by_sku = {item["sku"].strip().casefold(): item for item in inventory if item["sku"]}
    for row in payload["rows"]:
        item = by_sku.get(row["sku"].strip().casefold())
        row["on_order"] = qty(item["on_order"] if item else 0)
        row["par_level"] = qty(item["par_level"] if item else 0)
        sold_90d = D(row["sold_90d"])
        row["movement_class"] = "dead" if sold_90d <= 0 and D(row["sellable"]) > 0 else ("slow" if sold_90d > 0 and sold_90d < 3 else "active")
        suggested = D(row["suggested_reorder"]) if row["suggested_reorder"] is not None else Decimal("0")
        row["net_reorder"] = qty(max(Decimal("0"), suggested - D(row["on_order"])))
    payload["columns"].extend(
        [
            column("on_order", "On order", "quantity"),
            column("par_level", "Par level", "quantity"),
            column("net_reorder", "Net reorder", "quantity"),
            column("movement_class", "Movement class", "status"),
        ]
    )
    payload["kpis"][2] = metric("dead_stock", "No sales in 90d", str(sum(1 for row in payload["rows"] if row["movement_class"] == "dead")))
    payload["data_quality"].extend(inventory_warnings)
    payload["definitions"].append("Net reorder subtracts the current on-order quantity from the suggested reorder quantity.")
    return payload


def forecast_insights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    high = [row for row in rows if row["risk"] == "high"]
    dead = [row for row in rows if row.get("movement_class") == "dead" or (D(row["sold_90d"]) <= 0 and D(row["sellable"]) > 0)]
    findings = []
    if high:
        suggested = sum((D(row["suggested_reorder"]) for row in high if row["suggested_reorder"] is not None), Decimal("0"))
        findings.append(
            insight(
                "critical",
                f"{len(high)} SKU(s) may stock out inside lead time",
                f"The current model recommends {qty(suggested)} units across the high-risk group.",
                "Review the high-risk SKUs and confirm supplier lead times.",
                "#/insights/inventory-forecasting",
            )
        )
    if dead:
        findings.append(
            insight(
                "warning",
                f"{len(dead)} stocked SKU(s) have no recent sales",
                "These items hold sellable inventory but show no successful-order demand in the 90-day window.",
                "Review markdown, return, transfer or discontinuation options.",
            )
        )
    return findings


def build_sales_by_sku(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    inventory, inventory_warnings = inventory_by_item(db, filters)
    inventory_by_id = {item["item_id"]: item for item in inventory}
    subscription_data = build_subscription_data(db)
    subscriptions_by_item = {
        row["item_id"]: row
        for row in subscription_data["product_rows"]
        if row["item_id"] is not None
    }
    subscriptions_by_remote: dict[tuple[int, int | None], list[dict[str, Any]]] = defaultdict(list)
    subscription_skus: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for subscription in subscription_data["product_rows"]:
        subscriptions_by_remote[
            (subscription["woo_product_id"], subscription["woo_variation_id"])
        ].append(subscription)
        if subscription["sku"]:
            subscription_skus[subscription["sku"].strip().casefold()].append(subscription)
    groups: dict[Any, dict[str, Any]] = {}
    partial_refund_total = Decimal("0")
    for order in scoped_orders(db, filters):
        if not is_recognized_sales_order(order):
            continue
        refunds = (order.raw_woo_payload or {}).get("refunds") or []
        partial_refund_total += sum((abs(D(refund.get("total"))) for refund in refunds if isinstance(refund, dict)), Decimal("0"))
        for line in order.items:
            if not line_matches_filters(line, filters):
                continue
            item = line.inventory_item
            normalized_sku = (line.sku or "").strip().casefold()
            key = (
                f"item:{line.inventory_item_id}"
                if line.inventory_item_id
                else f"woo:{line.woo_product_id}:{line.woo_variation_id or 0}"
                if line.woo_product_id
                else f"sku:{normalized_sku}"
                if normalized_sku
                else f"line:{line.id}"
            )
            row = groups.setdefault(
                key,
                {
                    "item_id": line.inventory_item_id,
                    "sku": line.sku or (item.sku if item else ""),
                    "name": line.name or line.description or (item.woo_name if item else ""),
                    "brand": (item.brand if item else None) or line.brand or "",
                    "category": item.category if item else "",
                    "woo_identities": set(),
                    "orders": set(),
                    "quantity_sold": Decimal("0"),
                    "net_sales": Decimal("0"),
                },
            )
            if line.woo_product_id:
                row["woo_identities"].add((line.woo_product_id, line.woo_variation_id or None))
            row["orders"].add(order.id)
            row["quantity_sold"] += line_quantity(line)
            row["net_sales"] += D(line.line_total or line.total_price)
    rows = []
    for row in groups.values():
        exact_matches = {
            subscription["item_id"] or (
                subscription["woo_product_id"],
                subscription["woo_variation_id"],
                subscription["sku"],
            ): subscription
            for identity in row["woo_identities"]
            for subscription in subscriptions_by_remote.get(identity, [])
        }
        subscription = next(iter(exact_matches.values())) if len(exact_matches) == 1 else None
        if subscription is None and row["item_id"] is not None and not row["woo_identities"]:
            subscription = subscriptions_by_item.get(row["item_id"])
        if subscription is None and row["item_id"] is None and not row["woo_identities"]:
            sku_matches = [
                candidate
                for candidate in subscription_skus.get(str(row["sku"] or "").strip().casefold(), [])
                if candidate["match_status"] in {"mapped", "sku_fallback"}
            ]
            subscription = sku_matches[0] if len(sku_matches) == 1 else None
        current = inventory_by_id.get(row["item_id"] or (subscription or {}).get("item_id"))
        subscription_status = (
            "Unknown"
            if not subscription_data["available"]
            else "Active" if subscription else "Not active"
        )
        rows.append(
            {
                "sku": row["sku"],
                "name": row["name"],
                "brand": row["brand"],
                "category": row["category"],
                "order_count": len(row["orders"]),
                "quantity_sold": qty(row["quantity_sold"]),
                "net_sales": money(row["net_sales"]),
                "average_unit_price": money(row["net_sales"] / row["quantity_sold"] if row["quantity_sold"] else 0),
                "current_in_stock": qty(current["in_stock"]) if current else None,
                "current_allocated": qty(current["allocated"]) if current else None,
                "current_sellable": qty(current["sellable"]) if current else None,
                "is_subscription_product": bool(subscription),
                "subscription_status": subscription_status,
                "active_subscriptions": subscription["active_subscriptions"] if subscription else 0 if subscription_data["available"] else None,
                "upcoming_30_day_units": (
                    qty(subscription["upcoming_30_day_units"])
                    if subscription
                    else qty(0) if subscription_data["available"] else None
                ),
                "subscription_stockout_risk": subscription["stockout_risk"] if subscription else "Not applicable" if subscription_data["available"] else "Unknown",
            }
        )
    rows.sort(key=lambda row: D(row["quantity_sold"]), reverse=True)
    warnings = list(inventory_warnings)
    warnings.extend(
        quality_warning(
            warning["code"],
            warning["code"].replace("_", " ").title(),
            warning["message"],
        )
        for warning in subscription_data["warnings"]
    )
    if partial_refund_total:
        warnings.append(
            quality_warning(
                "partial_refunds_not_allocated_to_sku",
                "Partial refunds require reconciliation",
                f"{money(partial_refund_total)} in WooCommerce refund summaries cannot be reliably allocated to individual SKUs from the stored order snapshot.",
            )
        )
    return {
        "kpis": [
            metric("sales", "Net merchandise sales", money(sum((D(row["net_sales"]) for row in rows), Decimal("0"))), "currency"),
            metric("units", "Units sold", qty(sum((D(row["quantity_sold"]) for row in rows), Decimal("0"))), "quantity"),
            metric("skus", "SKUs sold", str(len(rows))),
            metric("refunds", "Unallocated refund summary", money(partial_refund_total), "currency"),
        ],
        "charts": [chart("Top-selling SKUs", rows[:12], "sku", "quantity_sold")],
        "columns": [
            column("sku", "SKU"),
            column("name", "Item"),
            column("brand", "Brand"),
            column("category", "Category"),
            column("subscription_status", "Subscription"),
            column("active_subscriptions", "Active subscriptions", "integer"),
            column("upcoming_30_day_units", "Units due in 30 days", "quantity"),
            column("subscription_stockout_risk", "Subscription stock"),
            column("order_count", "Orders", "integer"),
            column("quantity_sold", "Quantity sold", "quantity"),
            column("net_sales", "Net merchandise sales", "currency"),
            column("average_unit_price", "Average unit price", "currency"),
            column("current_in_stock", "Current stock", "quantity"),
            column("current_allocated", "Current allocated", "quantity"),
            column("current_sellable", "Current sellable", "quantity"),
        ],
        "rows": rows,
        "insights": sales_insights(rows),
        "data_quality": warnings,
        "definitions": [
            "WooCommerce sales include only processing and completed orders. Manual orders include processing, completed or fulfilled statuses.",
            "Net merchandise sales uses order-line totals and excludes shipping and tax.",
            "Current stock columns are a report-generation-time snapshot, not the historical stock at sale time.",
            "Subscription highlights use the latest complete active WooCommerce subscription snapshot available when this immutable report was generated.",
            "Subscription stock risk compares official next-renewal units due within 30 days with current Pongo sellable stock.",
        ],
    }


def is_recognized_sales_order(order: Order) -> bool:
    if order.woo_status:
        return order.woo_status.strip().casefold() in SALES_RECOGNIZED_WOO_STATUSES
    return order_status(order) in {"processing", "completed", "fulfilled"}


def sales_insights(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    top = rows[0]
    return [
        insight(
            "info",
            f"{top['sku'] or top['name']} is the highest-volume SKU",
            f"{top['quantity_sold']} units produced {top['net_sales']} in merchandise sales.",
            "Compare current sellable stock with its recent velocity.",
            f"#/inventory/all?search={top['sku']}",
        )
    ]


def build_executive_weekly(db: Session, filters: dict[str, Any]) -> dict[str, Any]:
    sales = build_sales_by_sku(db, filters)
    valuation = build_inventory_cost_category(db, {key: value for key, value in filters.items() if key not in {"start_date", "end_date"}})
    incomplete = build_incomplete_orders(db, filters)
    forecast = build_inventory_forecast(db, filters)
    brand_rows = aggregate_chart_rows(sales["rows"], "brand", "net_sales")
    category_rows = aggregate_chart_rows(sales["rows"], "category", "net_sales")
    rows = []
    for source, source_rows in (("brand", brand_rows), ("category", category_rows)):
        for row in source_rows:
            rows.append(
                {
                    "dimension": source,
                    "name": row[source],
                    "net_sales": money(row["net_sales"]),
                    "period_start": filters["start_date"],
                    "period_end": filters["end_date"],
                }
            )
    findings = [
        *sales["insights"],
        *valuation["insights"],
        *forecast["insights"],
    ]
    remaining = D(incomplete["kpis"][1]["value"])
    if remaining:
        findings.insert(
            0,
            insight(
                "critical",
                "Incomplete fulfillment requires attention",
                f"{incomplete['kpis'][0]['value']} order(s) have {qty(remaining)} units remaining.",
                "Review incomplete orders before the next fulfillment cycle.",
                "#/reports/incomplete-orders",
            ),
        )
    return {
        "kpis": [
            sales["kpis"][0],
            sales["kpis"][1],
            valuation["kpis"][0],
            incomplete["kpis"][0],
            forecast["kpis"][1],
            metric("actions", "Priority actions", str(len(findings))),
        ],
        "charts": [
            chart("Revenue by brand", brand_rows[:10], "brand", "net_sales"),
            chart("Revenue by category", category_rows[:10], "category", "net_sales"),
        ],
        "columns": [
            column("dimension", "Dimension"),
            column("name", "Name"),
            column("net_sales", "Net sales", "currency"),
            column("period_start", "Period start", "date"),
            column("period_end", "Period end", "date"),
        ],
        "rows": rows,
        "insights": findings[:10],
        "data_quality": dedupe_warnings([*sales["data_quality"], *valuation["data_quality"], *forecast["data_quality"]]),
        "definitions": [
            "Executive metrics combine frozen outputs from sales, valuation, incomplete-order and inventory-forecast calculations.",
            "Inventory value is a current snapshot; revenue and units use the selected report period.",
        ],
    }


def aggregate_chart_rows(rows: list[dict[str, Any]], category_key: str, value_key: str) -> list[dict[str, Any]]:
    grouped: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        key = str(row.get(category_key) or "Unspecified")
        grouped[key] += D(row.get(value_key))
    result = [{category_key: key, value_key: number(value)} for key, value in grouped.items()]
    result.sort(key=lambda row: D(row[value_key]), reverse=True)
    return result


def aggregate_count_rows(rows: list[dict[str, Any]], category_key: str) -> list[dict[str, Any]]:
    grouped: dict[str, int] = defaultdict(int)
    for row in rows:
        grouped[str(row.get(category_key) or "Unspecified")] += 1
    return [{category_key: key, "count": value} for key, value in sorted(grouped.items(), key=lambda item: item[1], reverse=True)]


def dedupe_warnings(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = {}
    for warning in warnings:
        code = warning.get("code") or warning.get("title") or "report_data_quality"
        normalized = {
            **warning,
            "code": code,
            "title": warning.get("title") or str(code).replace("_", " ").title(),
            "message": warning.get("message") or warning.get("detail") or "Review this report disclosure.",
        }
        deduped[code] = normalized
    return list(deduped.values())


def decode_html_entities(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: decode_html_entities(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_html_entities(item) for item in value]
    return html.unescape(value) if isinstance(value, str) else value


BUILDERS: dict[str, Callable[[Session, dict[str, Any]], dict[str, Any]]] = {
    "inventory-cost-category": build_inventory_cost_category,
    "inventory-cost-sku": build_inventory_cost_sku,
    "inventory-in-stock": build_inventory_in_stock,
    "inventory-usage": build_inventory_usage,
    "unallocated-order-items": build_unallocated_items,
    "delivered-inventory": build_delivered_inventory,
    "received-inventory": build_received_inventory,
    "inventory-export": build_inventory_export,
    "inventory-forecast": build_inventory_forecast,
    "incomplete-orders": build_incomplete_orders,
    "order-summary": build_order_summary,
    "daily-item-orders": build_daily_item_orders,
    "detailed-customer-orders": build_detailed_customer_orders,
    "executive-weekly": build_executive_weekly,
    "reorder-intelligence": build_reorder_intelligence,
    "po-received": build_po_received,
    "sales-by-sku": build_sales_by_sku,
}


def report_csv_bytes(run: ReportRun) -> bytes:
    verify_report_run(run)
    payload = run.payload or {}
    columns = payload.get("columns") or []
    fieldnames = [column["key"] for column in columns]
    metadata_fields = ["report_run_id", "report_generated_at", "report_data_hash"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[*metadata_fields, *fieldnames], extrasaction="ignore")
    writer.writeheader()
    for row in payload.get("rows") or [{}]:
        writer.writerow(
            {
                "report_run_id": run.id,
                "report_generated_at": run.generated_at.isoformat() if run.generated_at else "",
                "report_data_hash": run.data_hash,
                **row,
            }
        )
    return buffer.getvalue().encode("utf-8-sig")


def report_pdf_bytes(run: ReportRun) -> bytes:
    verify_report_run(run)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            KeepTogether,
            LongTable,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("PDF generation is not installed on the backend.") from exc
    payload = run.payload or {}
    report = payload.get("report") or {}
    columns = payload.get("columns") or []
    rows = payload.get("rows") or []
    kpis = payload.get("kpis") or []
    warnings = payload.get("data_quality") or []
    findings = payload.get("insights") or []
    filters = ", ".join(
        f"{key.replace('_', ' ').title()}: {value}"
        for key, value in (payload.get("filters") or {}).items()
    ) or "Current snapshot"
    def safe(value: Any) -> str:
        text = html.unescape(str(value or ""))
        for source, replacement in (("\u2011", "-"), ("\u2013", "-"), ("\u2014", "-"), ("\u2022", "-"), ("\u2026", "...")):
            text = text.replace(source, replacement)
        return html.escape(text)
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="PongoTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=24,
            textColor=colors.HexColor("#17182a"),
            alignment=TA_LEFT,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PongoSmall",
            parent=styles["BodyText"],
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#5f6176"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="PongoCell",
            parent=styles["BodyText"],
            fontSize=6.2,
            leading=7.4,
            textColor=colors.HexColor("#17182a"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="PongoHeader",
            parent=styles["PongoCell"],
            fontName="Helvetica-Bold",
            textColor=colors.white,
        )
    )

    def footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d8d9e4"))
        canvas.line(document.leftMargin, 0.42 * inch, letter[1] - document.rightMargin, 0.42 * inch)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#66687b"))
        canvas.drawString(document.leftMargin, 0.25 * inch, f"Pongo OS - Run {run.id}")
        canvas.drawRightString(
            letter[1] - document.rightMargin,
            0.25 * inch,
            f"Page {canvas.getPageNumber()} - SHA-256 {run.data_hash[:16]}...",
        )
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(letter),
        leftMargin=0.35 * inch,
        rightMargin=0.35 * inch,
        topMargin=0.35 * inch,
        bottomMargin=0.55 * inch,
        title=str(report.get("title") or run.title),
        author="Pongo OS",
        subject=f"Verified report run {run.id}",
    )
    story = [
        Paragraph("PONGO OS - VERIFIED REPORT SNAPSHOT", styles["PongoSmall"]),
        Paragraph(safe(report.get("title") or run.title), styles["PongoTitle"]),
        Paragraph(
            f"Generated {safe(run.generated_at.isoformat() if run.generated_at else '')} - "
            f"{REPORT_TIMEZONE}<br/>{safe(filters)}",
            styles["PongoSmall"],
        ),
        Spacer(1, 10),
    ]
    if kpis:
        kpi_cells = [
            Paragraph(
                f"<font size='6'>{safe(item.get('label'))}</font><br/>"
                f"<b><font size='12'>{safe(display_value(item.get('value'), item.get('type')))}</font></b>",
                styles["BodyText"],
            )
            for item in kpis
        ]
        kpi_table = Table([kpi_cells], colWidths=[document.width / len(kpi_cells)] * len(kpi_cells))
        kpi_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f4f0")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d9e4")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d9e4")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.extend([kpi_table, Spacer(1, 10)])
    for item in findings:
        story.append(
            KeepTogether(
                [
                    Paragraph(f"<b>{safe(item.get('title'))}</b>", styles["BodyText"]),
                    Paragraph(safe(item.get("evidence")), styles["PongoSmall"]),
                    Paragraph(f"Action: {safe(item.get('action') or 'Review')}", styles["PongoSmall"]),
                    Spacer(1, 5),
                ]
            )
        )
    if warnings:
        story.extend(
            [
                Paragraph("<b>Data-quality disclosures</b>", styles["BodyText"]),
                *[
                    Paragraph(
                        f"- <b>{safe(item.get('title'))}</b> - {safe(item.get('message'))}",
                        styles["PongoSmall"],
                    )
                    for item in warnings
                ],
                Spacer(1, 8),
            ]
        )
    if columns:
        table_rows = [
            [Paragraph(safe(item.get("label") or item.get("key")), styles["PongoHeader"]) for item in columns],
            *[
                [
                    Paragraph(safe(display_value(row.get(item["key"]), item.get("type"))), styles["PongoCell"])
                    for item in columns
                ]
                for row in rows
            ],
        ]
        column_width = document.width / max(1, len(columns))
        report_table = LongTable(
            table_rows,
            repeatRows=1,
            colWidths=[column_width] * len(columns),
            splitByRow=True,
        )
        report_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#11124e")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7fa")]),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#e2e3eb")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(report_table)
    story.extend(
        [
            PageBreak(),
            Paragraph("Audit record", styles["PongoTitle"]),
            Paragraph(f"Report run ID: {safe(run.id)}", styles["PongoSmall"]),
            Paragraph(f"Definition version: {run.definition_version}", styles["PongoSmall"]),
            Paragraph(f"SHA-256: {safe(run.data_hash)}", styles["PongoSmall"]),
            Paragraph(f"Rows: {run.row_count}", styles["PongoSmall"]),
            Paragraph(f"Filters: {safe(filters)}", styles["PongoSmall"]),
        ]
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def display_value(value: Any, kind: str | None = None) -> str:
    if value in (None, ""):
        return "—"
    if kind == "currency":
        return f"${D(value):,.2f}"
    if kind == "quantity":
        return f"{D(value):,.3f}".rstrip("0").rstrip(".")
    if kind == "boolean":
        return "Yes" if bool(value) else "No"
    return str(value)


def google_sheets_status(settings: Settings) -> dict[str, Any]:
    configured = bool(
        settings.google_reports_client_id
        and settings.google_reports_client_secret
        and settings.google_reports_refresh_token
    )
    return {"configured": configured, "folder_configured": bool(settings.google_reports_folder_id)}


def publish_report_to_google_sheets(
    db: Session,
    run: ReportRun,
    settings: Settings,
    share_with: list[str] | None = None,
) -> dict[str, Any]:
    verify_report_run(run)
    if not google_sheets_status(settings)["configured"]:
        raise RuntimeError("Google Sheets is not configured on the backend.")
    token = google_access_token(settings)
    payload = run.payload or {}
    generated_at = run.generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    title = f"Pongo — {run.title} — {generated_at.astimezone(REPORT_TZ).date().isoformat()}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30) as client:
        created = client.post(
            "https://sheets.googleapis.com/v4/spreadsheets",
            headers=headers,
            json={
                "properties": {"title": title, "locale": "en_CA", "timeZone": REPORT_TIMEZONE},
                "sheets": [
                    {"properties": {"title": "Report", "gridProperties": {"frozenRowCount": 1}}},
                    {"properties": {"title": "Audit"}},
                ],
            },
        )
        created.raise_for_status()
        spreadsheet = created.json()
        spreadsheet_id = spreadsheet["spreadsheetId"]
        columns = payload.get("columns") or []
        report_values = [
            [item["label"] for item in columns],
            *[
                [sheet_value(row.get(item["key"]), item.get("type")) for item in columns]
                for row in payload.get("rows") or []
            ],
        ]
        audit_values = [
            ["Field", "Value"],
            ["Report", run.title],
            ["Report run ID", run.id],
            ["Definition version", run.definition_version],
            ["Generated at", run.generated_at.isoformat() if run.generated_at else ""],
            ["Timezone", run.timezone],
            ["SHA-256", run.data_hash],
            ["Filters", json.dumps(run.filters, sort_keys=True)],
            ["Rows", run.row_count],
        ]
        update = client.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate",
            headers=headers,
            json={
                "valueInputOption": "RAW",
                "data": [
                    {"range": "Report!A1", "majorDimension": "ROWS", "values": report_values},
                    {"range": "Audit!A1", "majorDimension": "ROWS", "values": audit_values},
                ],
            },
        )
        update.raise_for_status()
        report_sheet_id = spreadsheet["sheets"][0]["properties"]["sheetId"]
        formatting_requests: list[dict[str, Any]] = [
            {
                "repeatCell": {
                    "range": {"sheetId": report_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.067, "green": 0.071, "blue": 0.306},
                            "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            },
            {
                "autoResizeDimensions": {
                    "dimensions": {"sheetId": report_sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": max(1, len(columns))}
                }
            },
        ]
        if report_values and columns:
            formatting_requests.append(
                {
                    "setBasicFilter": {
                        "filter": {
                            "range": {
                                "sheetId": report_sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": len(report_values),
                                "startColumnIndex": 0,
                                "endColumnIndex": len(columns),
                            }
                        }
                    }
                }
            )
        formatted = client.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
            headers=headers,
            json={"requests": formatting_requests},
        )
        formatted.raise_for_status()
        if settings.google_reports_folder_id:
            move = client.patch(
                f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}",
                headers=headers,
                params={"addParents": settings.google_reports_folder_id, "fields": "id,parents"},
                json={},
            )
            move.raise_for_status()
        for recipient in share_with or []:
            permission = client.post(
                f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}/permissions",
                headers=headers,
                params={"sendNotificationEmail": "true"},
                json={"type": "user", "role": "writer", "emailAddress": recipient},
            )
            permission.raise_for_status()
            db.add(ReportDelivery(report_run_id=run.id, channel="google_sheets", recipient=recipient, status="sent", external_url=spreadsheet["spreadsheetUrl"]))
    if not share_with:
        db.add(ReportDelivery(report_run_id=run.id, channel="google_sheets", status="created", external_url=spreadsheet["spreadsheetUrl"]))
    db.commit()
    return {"spreadsheet_id": spreadsheet_id, "url": spreadsheet["spreadsheetUrl"], "shared_with": share_with or []}


def google_access_token(settings: Settings) -> str:
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": settings.google_reports_client_id,
            "client_secret": settings.google_reports_client_secret,
            "refresh_token": settings.google_reports_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def sheet_value(value: Any, kind: str | None = None) -> Any:
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    if kind not in {"currency", "quantity", "number", "integer", "percent"}:
        return text
    try:
        return float(text) if "." in text else int(text)
    except (TypeError, ValueError):
        return text


def email_report(
    db: Session,
    run: ReportRun,
    settings: Settings,
    recipients: list[str],
    formats: list[str],
    subject: str | None = None,
    message: str | None = None,
    google_sheet_url: str | None = None,
) -> dict[str, Any]:
    verify_report_run(run)
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("Email sharing is not configured on the backend.")
    allowed_formats = [item for item in formats if item in {"csv", "pdf"}]
    if not allowed_formats and not google_sheet_url:
        raise ValueError("Choose CSV, PDF, or include a Google Sheet link.")
    if google_sheet_url and db.scalar(
        select(ReportDelivery.id).where(
            ReportDelivery.report_run_id == run.id,
            ReportDelivery.channel == "google_sheets",
            ReportDelivery.status.in_({"created", "sent"}),
            ReportDelivery.external_url == google_sheet_url,
        )
    ) is None:
        raise ValueError("Google Sheet link does not belong to this verified report run.")
    email = EmailMessage()
    email["From"] = settings.smtp_from_email
    email["To"] = ", ".join(recipients)
    email["Subject"] = subject or f"Pongo report: {run.title}"
    body = message or "A Pongo OS report has been shared with you."
    body += f"\n\nReport: {run.title}\nGenerated: {run.generated_at.isoformat() if run.generated_at else ''}\nRun ID: {run.id}\nSHA-256: {run.data_hash}"
    if google_sheet_url:
        body += f"\nGoogle Sheet: {google_sheet_url}"
    email.set_content(body)
    safe_name = run.report_key.replace("_", "-")
    if "csv" in allowed_formats:
        email.add_attachment(report_artifact_bytes(run, "csv"), maintype="text", subtype="csv", filename=f"pongo-{safe_name}-{run.id}.csv")
    if "pdf" in allowed_formats:
        email.add_attachment(report_artifact_bytes(run, "pdf"), maintype="application", subtype="pdf", filename=f"pongo-{safe_name}-{run.id}.pdf")
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                smtp_login_and_send(smtp, settings, email)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                smtp_login_and_send(smtp, settings, email)
    except Exception as exc:
        for recipient in recipients:
            db.add(ReportDelivery(report_run_id=run.id, channel="email", recipient=recipient, status="failed", error=str(exc)[:1000]))
        db.commit()
        raise
    for recipient in recipients:
        db.add(ReportDelivery(report_run_id=run.id, channel="email", recipient=recipient, status="sent", external_url=google_sheet_url))
    db.commit()
    return {"status": "sent", "recipients": recipients, "formats": allowed_formats, "google_sheet_url": google_sheet_url}


def smtp_login_and_send(smtp: smtplib.SMTP, settings: Settings, email: EmailMessage) -> None:
    if settings.smtp_username:
        smtp.login(settings.smtp_username, settings.smtp_password)
    smtp.send_message(email)
