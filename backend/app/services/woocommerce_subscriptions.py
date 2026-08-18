from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.inventory import InventoryItem
from app.models.performance import bump_metric_version
from app.models.woocommerce import WooCommerceSyncRun, WooSubscriptionLineSnapshot
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_order_reconciliation import woo_pagination


SUBSCRIPTION_SYNC_TYPE = "subscriptions"
SUBSCRIPTION_SYNC_INTERVAL = timedelta(minutes=15)
EDMONTON_TZ = ZoneInfo("America/Edmonton")


def process_subscription_sync_if_due(
    settings: Settings,
    *,
    db_factory=SessionLocal,
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now(timezone.utc)
    with db_factory() as db:
        latest_attempt = db.scalar(
            select(WooCommerceSyncRun)
            .where(WooCommerceSyncRun.sync_type == SUBSCRIPTION_SYNC_TYPE)
            .order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
        )
        if latest_attempt and aware_utc(latest_attempt.started_at) > now - SUBSCRIPTION_SYNC_INTERVAL:
            return False
        run = WooCommerceSyncRun(
            sync_type=SUBSCRIPTION_SYNC_TYPE,
            status="running",
            started_at=now,
            created_by="woocommerce-worker",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        try:
            client = WooCommerceClient(effective_woocommerce_settings(db, settings))
            subscriptions = fetch_active_subscriptions(client)
            snapshots, skipped = normalize_subscription_lines(subscriptions, now)
            if skipped:
                raise ValueError(
                    f"WooCommerce returned {skipped} invalid or incomplete subscription line(s); the last complete snapshot was kept."
                )
            db.execute(delete(WooSubscriptionLineSnapshot))
            db.add_all(snapshots)
            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.total_remote_records = len(subscriptions)
            run.created_count = len(snapshots)
            run.matched_count = len(snapshots)
            run.skipped_count = skipped
            run.error_count = skipped
            run.notes = "Active WooCommerce subscription snapshot refreshed."
            bump_metric_version(db)
            db.commit()
        except (ValueError, WooCommerceClientError) as error:
            db.rollback()
            run = db.get(WooCommerceSyncRun, run.id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_count = 1
            run.notes = str(error)[:1000]
            bump_metric_version(db)
            db.commit()
        return True


def fetch_active_subscriptions(client: WooCommerceClient) -> list[dict[str, Any]]:
    per_page = min(max(int(client.page_size), 1), 100)
    subscriptions: dict[int, dict[str, Any]] = {}
    page = 1
    while True:
        batch = client.list_subscriptions(page=page, per_page=per_page, status="active")
        for subscription in batch:
            if not isinstance(subscription, dict):
                raise ValueError("WooCommerce returned an invalid subscription record.")
            subscription_id = positive_int(subscription.get("id"))
            status = str(subscription.get("status") or "").casefold().removeprefix("wc-")
            if not subscription_id or status != "active":
                raise ValueError("WooCommerce returned an invalid active subscription record.")
            subscriptions[subscription_id] = subscription
        total_pages, _ = woo_pagination(getattr(client, "last_response_headers", {}))
        if (total_pages is not None and page >= total_pages) or (
            total_pages is None and len(batch) < per_page
        ):
            break
        page += 1
    return list(subscriptions.values())


def normalize_subscription_lines(
    subscriptions: list[dict[str, Any]],
    synced_at: datetime,
) -> tuple[list[WooSubscriptionLineSnapshot], int]:
    rows: dict[tuple[int, int], WooSubscriptionLineSnapshot] = {}
    skipped = 0
    for subscription in subscriptions:
        subscription_id = positive_int(subscription.get("id"))
        if not subscription_id:
            skipped += 1
            continue
        billing = subscription.get("billing") if isinstance(subscription.get("billing"), dict) else {}
        customer_name = " ".join(
            value.strip()
            for value in (str(billing.get("first_name") or ""), str(billing.get("last_name") or ""))
            if value.strip()
        ) or None
        line_items = subscription.get("line_items")
        if not isinstance(line_items, list) or not line_items:
            skipped += 1
            continue
        for line in line_items:
            if not isinstance(line, dict):
                skipped += 1
                continue
            line_id = positive_int(line.get("id"))
            product_id = positive_int(line.get("product_id"))
            if not line_id or not product_id:
                skipped += 1
                continue
            quantity = positive_decimal(line.get("quantity"))
            if quantity is None:
                skipped += 1
                continue
            next_payment_gmt = subscription.get("next_payment_date_gmt")
            rows[(subscription_id, line_id)] = WooSubscriptionLineSnapshot(
                woo_subscription_id=subscription_id,
                woo_line_item_id=line_id,
                status="active",
                next_payment_at=parse_woo_datetime(
                    next_payment_gmt or subscription.get("next_payment_date"),
                    default_timezone=timezone.utc if next_payment_gmt else EDMONTON_TZ,
                ),
                customer_name=customer_name,
                customer_email=(str(billing.get("email") or "").strip().casefold() or None),
                subscription_total=decimal_value(subscription.get("total")),
                currency=(str(subscription.get("currency") or "").strip().upper() or None),
                woo_product_id=product_id,
                woo_variation_id=positive_int(line.get("variation_id")),
                sku=(str(line.get("sku") or "").strip() or None),
                product_name=(str(line.get("name") or "").strip() or None),
                quantity_per_renewal=quantity,
                synced_at=synced_at,
            )
    return list(rows.values()), skipped


def build_subscription_data(db: Session, target_date: date | None = None) -> dict[str, Any]:
    target_date = target_date or datetime.now(EDMONTON_TZ).date()
    completed_run = db.scalar(
        select(WooCommerceSyncRun)
        .where(
            WooCommerceSyncRun.sync_type == SUBSCRIPTION_SYNC_TYPE,
            WooCommerceSyncRun.status == "completed",
        )
        .order_by(WooCommerceSyncRun.completed_at.desc(), WooCommerceSyncRun.id.desc())
    )
    if completed_run is None:
        refresh_status, freshness_warning = subscription_freshness(db, None)
        return {
            "available": False,
            "summary": {
                "subscription_data_available": False,
                "active_subscriptions_count": None,
                "subscription_products_count": None,
                "upcoming_7_days_count": None,
                "upcoming_30_days_count": None,
                "upcoming_7_day_units": None,
                "upcoming_30_day_units": None,
                "stockout_risk_product_count": None,
                "last_synced_at": None,
                "refresh_status": refresh_status,
            },
            "subscription_rows": [],
            "product_rows": [],
            "warnings": [freshness_warning or {
                "code": "missing_subscription_data",
                "severity": "info",
                "message": "No successful WooCommerce subscription snapshot is available yet.",
            }],
        }

    snapshots = list(
        db.scalars(
            select(WooSubscriptionLineSnapshot)
            .where(WooSubscriptionLineSnapshot.status == "active")
            .order_by(
                WooSubscriptionLineSnapshot.next_payment_at.asc().nullslast(),
                WooSubscriptionLineSnapshot.woo_subscription_id,
                WooSubscriptionLineSnapshot.woo_line_item_id,
            )
        ).all()
    )
    # ponytail: Pongo's catalog is small; narrow this query if catalog size makes it measurable.
    items = list(db.scalars(select(InventoryItem)).all())
    remote_items: dict[tuple[int, int | None], list[InventoryItem]] = defaultdict(list)
    sku_items: dict[str, list[InventoryItem]] = defaultdict(list)
    for item in items:
        if item.woo_product_id:
            remote_items[(item.woo_product_id, item.woo_variation_id)].append(item)
        if item.sku and item.sku.strip():
            sku_items[item.sku.strip().casefold()].append(item)

    subscription_rows: list[dict[str, Any]] = []
    products: dict[tuple[Any, ...], dict[str, Any]] = {}
    upcoming_7_ids: set[int] = set()
    upcoming_30_ids: set[int] = set()
    overdue_count = 0
    unmapped_count = 0
    for snapshot in snapshots:
        item, match_status = match_subscription_item(snapshot, remote_items, sku_items)
        if item is None:
            unmapped_count += 1
        stock_item = item if match_status in {"mapped", "sku_fallback"} else None
        quantity = Decimal(snapshot.quantity_per_renewal or 0)
        next_date = local_date(snapshot.next_payment_at)
        due_7 = next_date is not None and target_date <= next_date < target_date + timedelta(days=7)
        due_30 = next_date is not None and target_date <= next_date < target_date + timedelta(days=30)
        if next_date is None or next_date < target_date:
            overdue_count += 1
        if due_7:
            upcoming_7_ids.add(snapshot.woo_subscription_id)
        if due_30:
            upcoming_30_ids.add(snapshot.woo_subscription_id)
        key = (
            "item",
            item.id,
        ) if item else (
            "woo",
            snapshot.woo_product_id,
            snapshot.woo_variation_id,
            (snapshot.sku or "").casefold(),
        )
        product = products.setdefault(
            key,
            {
                "item_id": item.id if item else None,
                "woo_product_id": snapshot.woo_product_id,
                "woo_variation_id": snapshot.woo_variation_id,
                "sku": (item.sku if item else None) or snapshot.sku or "",
                "product_name": (item.description if item else None) or snapshot.product_name or "",
                "brand": item.brand if item else "",
                "category": item.category if item else "",
                "match_status": match_status,
                "current_in_stock": number(stock_item.in_stock) if stock_item else None,
                "current_allocated": number(stock_item.allocated) if stock_item else None,
                "current_sellable": number(stock_item.sellable) if stock_item else None,
                "active_subscription_ids": set(),
                "total_units_per_renewal": Decimal("0"),
                "upcoming_7_day_units": Decimal("0"),
                "upcoming_30_day_units": Decimal("0"),
                "next_renewal_date": None,
                "schedule_incomplete": False,
            },
        )
        product["active_subscription_ids"].add(snapshot.woo_subscription_id)
        product["total_units_per_renewal"] += quantity
        if due_7:
            product["upcoming_7_day_units"] += quantity
        if due_30:
            product["upcoming_30_day_units"] += quantity
        if next_date is None or next_date < target_date:
            product["schedule_incomplete"] = True
        if next_date and (product["next_renewal_date"] is None or next_date < product["next_renewal_date"]):
            product["next_renewal_date"] = next_date
        subscription_rows.append(
            {
                "subscription_id": snapshot.woo_subscription_id,
                "line_item_id": snapshot.woo_line_item_id,
                "customer_name": snapshot.customer_name,
                "customer": snapshot.customer_name,
                "customer_email": snapshot.customer_email,
                "email": snapshot.customer_email,
                "status": snapshot.status,
                "next_payment_date": next_date.isoformat() if next_date else None,
                "subscription_total": number(snapshot.subscription_total),
                "currency": snapshot.currency,
                "sku": (item.sku if item else None) or snapshot.sku or "",
                "product_name": (item.description if item else None) or snapshot.product_name or "",
                "quantity_due": number(quantity),
                "current_in_stock": number(stock_item.in_stock) if stock_item else None,
                "current_sellable": number(stock_item.sellable) if stock_item else None,
                "match_status": match_status,
                "due_within_30_days": due_30,
                "product_key": key,
            }
        )

    product_rows = []
    product_status_by_key = {}
    for key, product in products.items():
        sellable = Decimal(str(product["current_sellable"])) if product["current_sellable"] is not None else None
        upcoming = product["upcoming_30_day_units"]
        schedule_incomplete = product.pop("schedule_incomplete")
        shortfall = max(Decimal("0"), upcoming - sellable) if sellable is not None and not schedule_incomplete else None
        product.update(
            active_subscriptions=len(product.pop("active_subscription_ids")),
            total_units_per_renewal=number(product["total_units_per_renewal"]),
            upcoming_7_day_units=number(product["upcoming_7_day_units"]),
            upcoming_30_day_units=number(upcoming),
            next_renewal_date=(product["next_renewal_date"].isoformat() if product["next_renewal_date"] else None),
            projected_sellable_30_days=number(sellable - upcoming) if sellable is not None and not schedule_incomplete else None,
            projected_shortfall_30_days=number(shortfall),
            stockout_risk=(
                "Schedule incomplete"
                if schedule_incomplete
                else ("At risk" if shortfall and shortfall > 0 else "Covered")
                if sellable is not None
                else "Stock unavailable"
            ),
        )
        product_rows.append(product)
        product_status_by_key[key] = (
            product["projected_shortfall_30_days"],
            product["stockout_risk"],
        )
    for row in subscription_rows:
        row["projected_shortfall_30_days"], row["stockout_risk"] = product_status_by_key[
            row.pop("product_key")
        ]
    product_rows.sort(
        key=lambda row: (
            row["stockout_risk"] != "At risk",
            row["next_renewal_date"] or "9999-12-31",
            row["product_name"],
        )
    )
    subscription_rows.sort(
        key=lambda row: (
            row.get("stockout_risk") != "At risk",
            row["next_payment_date"] or "9999-12-31",
            row["product_name"],
        )
    )
    last_good_at = aware_utc(completed_run.completed_at or completed_run.started_at)
    refresh_status, freshness_warning = subscription_freshness(db, last_good_at)
    warnings = []
    if freshness_warning:
        warnings.append(freshness_warning)
    if completed_run.skipped_count:
        warnings.append({
            "code": "subscription_lines_skipped",
            "severity": "warning",
            "message": f"{completed_run.skipped_count} subscription line(s) had invalid or incomplete WooCommerce data.",
        })
    if unmapped_count:
        warnings.append({
            "code": "subscription_products_unmapped",
            "severity": "warning",
            "message": f"{unmapped_count} active subscription line(s) are not mapped to a Pongo inventory item.",
        })
    if overdue_count:
        warnings.append({
            "code": "subscription_next_payment_missing_or_past_due",
            "severity": "warning",
            "message": f"{overdue_count} active subscription line(s) have no future WooCommerce next-payment date.",
        })
    return {
        "available": True,
        "summary": {
            "subscription_data_available": True,
            "active_subscriptions_count": completed_run.total_remote_records,
            "subscription_products_count": len(product_rows),
            "upcoming_7_days_count": len(upcoming_7_ids),
            "upcoming_30_days_count": len(upcoming_30_ids),
            "upcoming_7_day_units": number(sum((Decimal(str(row["upcoming_7_day_units"])) for row in product_rows), Decimal("0"))),
            "upcoming_30_day_units": number(sum((Decimal(str(row["upcoming_30_day_units"])) for row in product_rows), Decimal("0"))),
            "stockout_risk_product_count": sum(1 for row in product_rows if row["stockout_risk"] == "At risk"),
            "last_synced_at": completed_run.completed_at.isoformat() if completed_run.completed_at else None,
            "refresh_status": refresh_status,
        },
        "subscription_rows": subscription_rows,
        "product_rows": product_rows,
        "warnings": warnings,
    }


def match_subscription_item(
    snapshot: WooSubscriptionLineSnapshot,
    remote_items: dict[tuple[int, int | None], list[InventoryItem]],
    sku_items: dict[str, list[InventoryItem]],
) -> tuple[InventoryItem | None, str]:
    matches = remote_items.get((snapshot.woo_product_id, snapshot.woo_variation_id), [])
    if len(matches) == 1:
        item = matches[0]
        if not item.active:
            return item, "inactive"
        if item.non_inventory:
            return item, "non_inventory"
        return item, "mapped"
    if len(matches) > 1:
        return None, "ambiguous"
    sku_matches = sku_items.get((snapshot.sku or "").strip().casefold(), []) if snapshot.sku else []
    if len(sku_matches) == 1:
        item = sku_matches[0]
        if item.woo_product_id and (
            item.woo_product_id != snapshot.woo_product_id
            or item.woo_variation_id != snapshot.woo_variation_id
        ):
            return None, "identity_conflict"
        if not item.active:
            return item, "inactive"
        if item.non_inventory:
            return item, "non_inventory"
        return item, "sku_fallback"
    return None, "ambiguous" if len(sku_matches) > 1 else "unmapped"


def overlay_subscription_freshness(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    summary = dict(payload.get("summary") or {})
    refresh_status, warning = subscription_freshness(db, summary.get("last_synced_at"))
    summary["refresh_status"] = refresh_status
    replaced_codes = {"subscription_refresh_failed", "subscription_snapshot_stale"}
    if warning and warning["code"] == "subscription_refresh_failed" and not summary.get("last_synced_at"):
        replaced_codes.add("missing_subscription_data")
    warnings = [
        item
        for item in payload.get("data_quality", payload.get("warnings", []))
        if item.get("code") not in replaced_codes
    ]
    if warning:
        warnings.append(warning)
    result = {**payload, "summary": summary}
    result["data_quality" if "data_quality" in payload else "warnings"] = warnings
    return result


def subscription_freshness(
    db: Session,
    last_good_at: datetime | str | None,
) -> tuple[str, dict[str, str] | None]:
    latest_attempt = db.scalar(
        select(WooCommerceSyncRun)
        .where(WooCommerceSyncRun.sync_type == SUBSCRIPTION_SYNC_TYPE)
        .order_by(WooCommerceSyncRun.started_at.desc(), WooCommerceSyncRun.id.desc())
    )
    parsed_last_good = (
        aware_utc(last_good_at)
        if isinstance(last_good_at, datetime)
        else parse_woo_datetime(last_good_at)
    )
    if parsed_last_good is None:
        if latest_attempt and latest_attempt.status == "failed":
            return "failed", {
                "code": "subscription_refresh_failed",
                "severity": "warning",
                "message": "The WooCommerce subscription refresh failed and no complete snapshot is available yet.",
            }
        return "unavailable", None
    if (
        latest_attempt
        and latest_attempt.status == "failed"
        and aware_utc(latest_attempt.started_at) > parsed_last_good
    ):
        return "failed", {
            "code": "subscription_refresh_failed",
            "severity": "warning",
            "message": "The latest WooCommerce subscription refresh failed; showing the last complete snapshot.",
        }
    if parsed_last_good < datetime.now(timezone.utc) - (SUBSCRIPTION_SYNC_INTERVAL * 2):
        return "stale", {
            "code": "subscription_snapshot_stale",
            "severity": "warning",
            "message": "The WooCommerce subscription snapshot is older than 30 minutes.",
        }
    return "current", None


def positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def positive_decimal(value: Any) -> Decimal | None:
    result = decimal_value(value)
    return result if result is not None and result > 0 else None


def parse_woo_datetime(value: Any, *, default_timezone=timezone.utc) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_timezone)
    return aware_utc(parsed)


def aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def local_date(value: datetime | None) -> date | None:
    return aware_utc(value).astimezone(EDMONTON_TZ).date() if value else None


def number(value: Any) -> int | float | None:
    if value is None:
        return None
    decimal = Decimal(str(value))
    return int(decimal) if decimal == decimal.to_integral_value() else float(decimal)
