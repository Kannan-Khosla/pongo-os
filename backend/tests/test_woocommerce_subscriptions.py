from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.inventory import InventoryItem
from app.models.woocommerce import WooCommerceSyncRun, WooSubscriptionLineSnapshot
from app.services.woocommerce_client import WooCommerceClientError
from app.services.woocommerce_subscriptions import (
    build_subscription_data,
    fetch_active_subscriptions,
    normalize_subscription_lines,
    overlay_subscription_freshness,
    process_subscription_sync_if_due,
)
from app.services.metric_cache import current_metric_version
from tests.test_items_api import client, seed_item  # noqa: F401


def test_subscription_snapshot_joins_simple_and_variation_stock(client):
    simple = seed_item(
        client,
        sku="SUB-SIMPLE",
        wooProductId=101,
        **{"In Stock": 8, "Allocated": 2},
    )
    variation = seed_item(
        client,
        sku="SUB-VARIATION",
        wooProductId=200,
        wooVariationId=201,
        **{"In Stock": 1, "Allocated": 0},
    )
    synced_at = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
    with Session(client.test_engine) as db:
        db.add(
            WooCommerceSyncRun(
                sync_type="subscriptions",
                status="completed",
                started_at=synced_at,
                completed_at=synced_at,
                total_remote_records=2,
                created_count=2,
                matched_count=2,
            )
        )
        db.add_all(
            [
                WooSubscriptionLineSnapshot(
                    woo_subscription_id=9001,
                    woo_line_item_id=1,
                    status="active",
                    next_payment_at=datetime(2026, 7, 10, 12, tzinfo=timezone.utc),
                    woo_product_id=101,
                    sku="SUB-SIMPLE",
                    product_name="Simple subscription",
                    quantity_per_renewal=3,
                    synced_at=synced_at,
                ),
                WooSubscriptionLineSnapshot(
                    woo_subscription_id=9002,
                    woo_line_item_id=2,
                    status="active",
                    next_payment_at=datetime(2026, 7, 11, 12, tzinfo=timezone.utc),
                    woo_product_id=200,
                    woo_variation_id=201,
                    sku="SUB-VARIATION",
                    product_name="Variation subscription",
                    quantity_per_renewal=2,
                    synced_at=synced_at,
                ),
            ]
        )
        db.commit()

        data = build_subscription_data(db, date(2026, 7, 8))

    products = {row["sku"]: row for row in data["product_rows"]}
    assert data["summary"]["active_subscriptions_count"] == 2
    assert data["summary"]["upcoming_7_days_count"] == 2
    assert products["SUB-SIMPLE"]["item_id"] == simple["id"]
    assert products["SUB-SIMPLE"]["current_sellable"] == 6
    assert products["SUB-SIMPLE"]["stockout_risk"] == "Covered"
    assert products["SUB-VARIATION"]["item_id"] == variation["id"]
    assert products["SUB-VARIATION"]["stockout_risk"] == "At risk"


def test_missing_or_past_due_schedule_never_claims_stock_is_covered(client):
    for sku, woo_product_id in (("MISSING-DATE", 301), ("PAST-DUE", 302)):
        seed_item(client, sku=sku, wooProductId=woo_product_id, **{"In Stock": 20})
    synced_at = datetime(2026, 7, 8, 12, tzinfo=timezone.utc)
    with Session(client.test_engine) as db:
        db.add(
            WooCommerceSyncRun(
                sync_type="subscriptions",
                status="completed",
                started_at=synced_at,
                completed_at=synced_at,
                total_remote_records=2,
                created_count=2,
            )
        )
        db.add_all(
            [
                WooSubscriptionLineSnapshot(
                    woo_subscription_id=9101,
                    woo_line_item_id=1,
                    status="active",
                    next_payment_at=None,
                    woo_product_id=301,
                    sku="MISSING-DATE",
                    quantity_per_renewal=2,
                    synced_at=synced_at,
                ),
                WooSubscriptionLineSnapshot(
                    woo_subscription_id=9102,
                    woo_line_item_id=2,
                    status="active",
                    next_payment_at=datetime(2026, 7, 7, 12, tzinfo=timezone.utc),
                    woo_product_id=302,
                    sku="PAST-DUE",
                    quantity_per_renewal=3,
                    synced_at=synced_at,
                ),
            ]
        )
        db.commit()

        data = build_subscription_data(db, date(2026, 7, 8))

    products = {row["sku"]: row for row in data["product_rows"]}
    for sku in ("MISSING-DATE", "PAST-DUE"):
        assert products[sku]["stockout_risk"] == "Schedule incomplete"
        assert products[sku]["projected_sellable_30_days"] is None
        assert products[sku]["projected_shortfall_30_days"] is None


def test_failed_subscription_page_keeps_last_complete_snapshot(client, monkeypatch):
    old_sync = datetime.now(timezone.utc) - timedelta(hours=1)
    with Session(client.test_engine) as db:
        db.add(
            WooCommerceSyncRun(
                sync_type="subscriptions",
                status="completed",
                started_at=old_sync,
                completed_at=old_sync,
                total_remote_records=1,
                created_count=1,
            )
        )
        db.add(
            WooSubscriptionLineSnapshot(
                woo_subscription_id=8001,
                woo_line_item_id=1,
                status="active",
                woo_product_id=101,
                sku="LAST-GOOD",
                quantity_per_renewal=1,
                synced_at=old_sync,
            )
        )
        db.commit()

    class FailingClient:
        page_size = 1

        def __init__(self, _settings):
            pass

        def list_subscriptions(self, page=1, per_page=100, status="active"):
            if page == 1:
                return [{"id": 9001, "status": "active", "line_items": []}]
            raise WooCommerceClientError("Subscription page unavailable.")

    factory = sessionmaker(bind=client.test_engine, autoflush=False, autocommit=False)
    with factory() as db:
        version_before = current_metric_version(db)
    monkeypatch.setattr("app.services.woocommerce_subscriptions.WooCommerceClient", FailingClient)
    monkeypatch.setattr(
        "app.services.woocommerce_subscriptions.effective_woocommerce_settings",
        lambda *_args: SimpleNamespace(),
    )

    assert process_subscription_sync_if_due(SimpleNamespace(), db_factory=factory) is True

    with Session(client.test_engine) as db:
        snapshots = list(db.scalars(select(WooSubscriptionLineSnapshot)).all())
        latest = db.scalar(
            select(WooCommerceSyncRun)
            .where(WooCommerceSyncRun.sync_type == "subscriptions")
            .order_by(WooCommerceSyncRun.started_at.desc())
        )
        data = build_subscription_data(db)
        version_after = current_metric_version(db)
    assert [row.sku for row in snapshots] == ["LAST-GOOD"]
    assert latest.status == "failed"
    assert latest.notes == "Subscription page unavailable."
    assert version_after > version_before
    assert "subscription_refresh_failed" in {warning["code"] for warning in data["warnings"]}


def test_subscription_fetch_stops_at_reported_last_full_page():
    class ExactPageClient:
        page_size = 2
        last_response_headers = {}

        def __init__(self):
            self.pages = []

        def list_subscriptions(self, page=1, per_page=100, status="active"):
            self.pages.append(page)
            self.last_response_headers = {"X-WP-Total": "2", "X-WP-TotalPages": "1"}
            return [
                {"id": 1, "status": "active"},
                {"id": 2, "status": "active"},
            ]

    woo = ExactPageClient()

    assert len(fetch_active_subscriptions(woo)) == 2
    assert woo.pages == [1]

    class MalformedClient:
        page_size = 100
        last_response_headers = {"X-WP-Total": "1", "X-WP-TotalPages": "1"}

        def list_subscriptions(self, **_kwargs):
            return [None]

    with pytest.raises(ValueError, match="invalid subscription record"):
        fetch_active_subscriptions(MalformedClient())


def test_empty_success_replaces_snapshot_and_invalidates_metrics(client, monkeypatch):
    old_sync = datetime.now(timezone.utc) - timedelta(hours=1)
    factory = sessionmaker(bind=client.test_engine, autoflush=False, autocommit=False)
    with factory() as db:
        db.add(
            WooCommerceSyncRun(
                sync_type="subscriptions",
                status="completed",
                started_at=old_sync,
                completed_at=old_sync,
                total_remote_records=1,
            )
        )
        db.add(
            WooSubscriptionLineSnapshot(
                woo_subscription_id=8001,
                woo_line_item_id=1,
                status="active",
                woo_product_id=101,
                sku="OLD-SUBSCRIPTION",
                quantity_per_renewal=1,
                synced_at=old_sync,
            )
        )
        db.commit()
        version_before = current_metric_version(db)

    class EmptyClient:
        page_size = 100
        last_response_headers = {}

        def __init__(self, _settings):
            pass

        def list_subscriptions(self, page=1, per_page=100, status="active"):
            self.last_response_headers = {"X-WP-Total": "0", "X-WP-TotalPages": "0"}
            return []

    monkeypatch.setattr("app.services.woocommerce_subscriptions.WooCommerceClient", EmptyClient)
    monkeypatch.setattr(
        "app.services.woocommerce_subscriptions.effective_woocommerce_settings",
        lambda *_args: SimpleNamespace(),
    )

    assert process_subscription_sync_if_due(SimpleNamespace(), db_factory=factory) is True

    with factory() as db:
        assert list(db.scalars(select(WooSubscriptionLineSnapshot)).all()) == []
        assert current_metric_version(db) > version_before
        assert build_subscription_data(db)["summary"]["active_subscriptions_count"] == 0


def test_subscription_local_dates_use_edmonton_timezone_and_invalid_lines_fail_normalization():
    synced_at = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)
    snapshots, skipped = normalize_subscription_lines(
        [
            {
                "id": 1,
                "status": "active",
                "next_payment_date": "2026-08-18T00:30:00",
                "line_items": [{"id": 11, "product_id": 101, "quantity": 1}],
            },
            {"id": 2, "status": "active", "line_items": []},
        ],
        synced_at,
    )

    assert snapshots[0].next_payment_at == datetime(2026, 8, 18, 6, 30, tzinfo=timezone.utc)
    assert skipped == 1


def test_cached_subscription_payload_gets_live_freshness_overlay(client):
    old_sync = datetime.now(timezone.utc) - timedelta(hours=1)
    with Session(client.test_engine) as db:
        db.add(
            WooCommerceSyncRun(
                sync_type="subscriptions",
                status="completed",
                started_at=old_sync,
                completed_at=old_sync,
                total_remote_records=1,
            )
        )
        db.commit()
        payload = overlay_subscription_freshness(
            db,
            {
                "summary": {"last_synced_at": old_sync.isoformat(), "refresh_status": "current"},
                "data_quality": [],
            },
        )

    assert payload["summary"]["refresh_status"] == "stale"
    assert {warning["code"] for warning in payload["data_quality"]} == {"subscription_snapshot_stale"}


def test_subscription_mapping_does_not_guess_conflicting_or_inactive_stock(client):
    seed_item(client, sku="CONFLICT", wooProductId=501, **{"In Stock": 9, "Allocated": 0})
    inactive = seed_item(client, sku="INACTIVE", wooProductId=601, **{"In Stock": 9, "Allocated": 0})
    synced_at = datetime.now(timezone.utc)
    with Session(client.test_engine) as db:
        db.get(InventoryItem, inactive["id"]).active = False
        db.add(
            WooCommerceSyncRun(
                sync_type="subscriptions",
                status="completed",
                started_at=synced_at,
                completed_at=synced_at,
                total_remote_records=2,
                created_count=2,
            )
        )
        db.add_all(
            [
                WooSubscriptionLineSnapshot(
                    woo_subscription_id=9101,
                    woo_line_item_id=1,
                    status="active",
                    next_payment_at=synced_at + timedelta(days=1),
                    woo_product_id=999,
                    sku="CONFLICT",
                    product_name="Conflicting identity",
                    quantity_per_renewal=1,
                    synced_at=synced_at,
                ),
                WooSubscriptionLineSnapshot(
                    woo_subscription_id=9102,
                    woo_line_item_id=2,
                    status="active",
                    next_payment_at=synced_at + timedelta(days=1),
                    woo_product_id=601,
                    sku="INACTIVE",
                    product_name="Inactive item",
                    quantity_per_renewal=1,
                    synced_at=synced_at,
                ),
            ]
        )
        db.commit()

        rows = {row["sku"]: row for row in build_subscription_data(db)["product_rows"]}

    assert rows["CONFLICT"]["match_status"] == "identity_conflict"
    assert rows["CONFLICT"]["current_sellable"] is None
    assert rows["CONFLICT"]["stockout_risk"] == "Stock unavailable"
    assert rows["INACTIVE"]["match_status"] == "inactive"
    assert rows["INACTIVE"]["current_sellable"] is None
    assert rows["INACTIVE"]["stockout_risk"] == "Stock unavailable"
