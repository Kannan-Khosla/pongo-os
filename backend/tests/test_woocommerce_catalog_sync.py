from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models.auth import User
from app.models.inventory import InventoryItem, StockMovement
from app.models.woocommerce import WooCatalogSyncRow, WooCommerceSyncRun, WooItemMapping
from app.services.woocommerce_catalog_sync import (
    catalog_sync_run_read,
    process_next_catalog_sync,
    prune_catalog_stage_rows,
    record_catalog_failure,
    retry_after_seconds,
)
from app.services.woocommerce_client import WooCommerceClientError
from tests.test_items_api import client, seed_item  # noqa: F401


def product(product_id: int, sku: str, **overrides):
    value = {
        "id": product_id,
        "type": "simple",
        "sku": sku,
        "name": f"Woo item {product_id}",
        "description": f"Woo description {product_id}",
        "status": "publish",
        "purchasable": True,
        "manage_stock": True,
        "stock_quantity": 17,
        "stock_status": "instock",
        "regular_price": "12.99",
        "price": "12.99",
        "sale_price": "",
        "categories": [{"name": "Woo category"}],
        "attributes": [{"name": "Brand", "options": ["Woo brand"]}],
        "dimensions": {},
        "images": [],
        "meta_data": [],
    }
    value.update(overrides)
    return value


def variation(variation_id: int, sku: str, **overrides):
    value = {
        "id": variation_id,
        "sku": sku,
        "name": f"Variation {variation_id}",
        "status": "publish",
        "purchasable": False,
        "manage_stock": True,
        "stock_quantity": 0,
        "stock_status": "outofstock",
        "regular_price": "9.99",
        "price": "9.99",
        "sale_price": "",
        "attributes": [{"name": "Size", "option": "Small"}],
        "dimensions": {},
        "meta_data": [],
    }
    value.update(overrides)
    return value


class CatalogClient:
    configured = True

    def __init__(
        self,
        product_pages,
        variation_pages=None,
        *,
        delta_product_pages=None,
        product_total_pages=None,
        delta_product_total_pages=None,
        variation_total_pages=None,
    ):
        self.product_pages = product_pages
        self.delta_product_pages = delta_product_pages or {1: []}
        self.variation_pages = variation_pages or {}
        self.product_total_pages = product_total_pages or max(product_pages or {1: []})
        self.delta_product_total_pages = delta_product_total_pages or max(self.delta_product_pages)
        self.variation_total_pages = variation_total_pages or {}
        self.last_response_headers = {}
        self.calls = []
        self.write_calls = []
        self.open_count = 0
        self.close_count = 0

    def open(self):
        self.open_count += 1
        return self

    def close(self):
        self.close_count += 1

    def list_products(self, page=1, per_page=100, statuses=None, **kwargs):
        self.calls.append(("products", page, per_page, statuses, kwargs))
        delta = bool(kwargs.get("modified_after"))
        pages = self.delta_product_pages if delta else self.product_pages
        total_pages = self.delta_product_total_pages if delta else self.product_total_pages
        rows = list(pages.get(page, []))
        self.last_response_headers = {
            "x-wp-totalpages": str(total_pages),
            "x-wp-total": str(sum(len(values) for values in pages.values())),
        }
        return rows

    def list_product_variations(self, product_id, page=1, per_page=100, **kwargs):
        self.calls.append(("variations", product_id, page, per_page, kwargs))
        rows = list(self.variation_pages.get((product_id, page), []))
        total_pages = self.variation_total_pages.get(product_id, max(
            [candidate_page for candidate_id, candidate_page in self.variation_pages if candidate_id == product_id] or [1]
        ))
        self.last_response_headers = {
            "x-wp-totalpages": str(total_pages),
            "x-wp-total": str(sum(
                len(values) for (candidate_id, _), values in self.variation_pages.items() if candidate_id == product_id
            )),
        }
        return rows

    def page_has_more(self, page, returned_count, page_size):
        del returned_count, page_size
        return page < int(self.last_response_headers["x-wp-totalpages"])


class FailingCatalogClient(CatalogClient):
    def __init__(self, error, retry_after=None):
        super().__init__({1: []})
        self.error = error
        self.retry_after = retry_after

    def list_products(self, **kwargs):
        self.calls.append(("products", kwargs))
        self.last_response_headers = {"retry-after": self.retry_after} if self.retry_after else {}
        raise self.error


def catalog_settings():
    return Settings(
        _env_file=None,
        app_env="test",
        woocommerce_base_url="https://store.example",
        woocommerce_consumer_key="ck_test",
        woocommerce_consumer_secret="cs_test",
        woocommerce_allowed_host="store.example",
    )


def database_factory(test_client):
    return sessionmaker(bind=test_client.test_engine, autoflush=False, autocommit=False)


def work_once(test_client, fake):
    return process_next_catalog_sync(
        catalog_settings(),
        db_factory=database_factory(test_client),
        client_factory=lambda _settings: fake,
    )


def run_to_terminal(test_client, fake, *, limit=30):
    latest = None
    for _ in range(limit):
        latest = work_once(test_client, fake)
        with Session(test_client.test_engine) as db:
            run = db.scalar(
                select(WooCommerceSyncRun)
                .where(WooCommerceSyncRun.sync_type == "catalog")
                .order_by(WooCommerceSyncRun.id.desc())
            )
            if run and run.status in {"completed", "completed_with_attention", "paused", "failed", "cancelled"}:
                return run.id, run.status
    raise AssertionError(f"Catalog sync did not reach a terminal state; last worker result was {latest!r}")


def test_catalog_enqueue_is_immediate_idempotent_and_current_is_first_use_safe(client):
    assert client.get("/api/integrations/woocommerce/catalog-syncs/current").json() == {"run": None}

    first = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "catalog-browser-retry"},
    )
    repeat = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "catalog-browser-retry"},
    )
    other_key_while_active = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "another-click"},
    )
    mismatch = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "header-key"},
        json={"idempotency_key": "body-key"},
    )

    assert first.status_code == 202
    assert first.json()["status"] == "queued"
    assert first.json()["created_by"] == "pytest@example.com"
    assert first.json()["can_resolve"] is False
    assert repeat.json()["id"] == first.json()["id"]
    assert repeat.json()["deduplicated"] is True
    assert other_key_while_active.json()["id"] == first.json()["id"]
    assert mismatch.status_code == 409
    with Session(client.test_engine) as db:
        assert db.scalar(select(func.count(WooCommerceSyncRun.id)).where(WooCommerceSyncRun.sync_type == "catalog")) == 1


def test_demo_catalog_enqueue_is_blocked_before_a_run_is_inserted(client):
    with Session(client.test_engine) as db:
        user = db.scalar(select(User).where(User.email == "pytest@example.com"))
        user.access_level = "demo"
        db.commit()

    response = client.post("/api/integrations/woocommerce/catalog-syncs")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "demo_external_access_blocked"
    with Session(client.test_engine) as db:
        assert db.scalar(select(func.count(WooCommerceSyncRun.id)).where(WooCommerceSyncRun.sync_type == "catalog")) == 0


def test_catalog_sync_preserves_local_operations_and_covers_every_inventory_unit(client):
    existing = seed_item(
        client,
        sku="KEEP-ME",
        Barcode="LOCAL-BARCODE",
        Brand="Local brand",
        Description="Local description",
        **{"In Stock": 11, "Allocated": 3, "Unit Cost": 7.25},
    )
    with Session(client.test_engine) as db:
        stale = InventoryItem(
            client="Pongo",
            sku="STALE-WOO",
            woo_product_id=999,
            in_stock=2,
            allocated=0,
            sellable=2,
            active=True,
            non_inventory=False,
        )
        db.add(stale)
        db.flush()
        db.add(WooItemMapping(
            item_id=stale.id,
            woo_product_id=999,
            woo_variation_id=None,
            mapping_source="manual",
            active=True,
        ))
        stale_id = stale.id
        movement_count = int(db.scalar(select(func.count(StockMovement.id))) or 0)
        db.commit()

    parent = product(20, "PARENT", type="variable", name="Variable parent")
    fake = CatalogClient(
        {
            1: [
                product(10, "KEEP-ME", name="Remote overwrite attempt", stock_quantity=99),
                product(11, "NEW-SIMPLE", global_unique_id="001234567890"),
                parent,
                product(12, "", name="Missing SKU"),
            ]
        },
        {(20, 1): [variation(201, "VAR-OOS")]},
        product_total_pages=1,
        variation_total_pages={20: 1},
    )
    response = client.post("/api/integrations/woocommerce/catalog-syncs", headers={"Idempotency-Key": "full-run"})
    assert response.status_code == 202
    run_id, status = run_to_terminal(client, fake)

    assert status == "completed_with_attention"
    assert fake.write_calls == []
    assert [call[0] for call in fake.calls] == ["products", "variations", "products"]
    assert fake.calls[0][-1] == {"orderby": "id", "order": "asc"}
    assert fake.calls[1][-1] == {"orderby": "id", "order": "asc"}
    assert fake.calls[2][-1]["modified_after"]
    with Session(client.test_engine) as db:
        local = db.get(InventoryItem, existing["id"])
        assert local.id == existing["id"]
        assert local.description == "Local description"
        assert local.barcode == "LOCAL-BARCODE"
        assert local.brand == "Local brand"
        assert local.unit_cost == Decimal("7.25")
        assert local.in_stock == Decimal("11")
        assert local.allocated == Decimal("3")
        assert local.woo_product_id == 10

        new_simple = db.scalar(select(InventoryItem).where(InventoryItem.sku == "NEW-SIMPLE"))
        assert new_simple.barcode == "001234567890"
        assert new_simple.in_stock == 0
        assert new_simple.allocated == 0
        assert new_simple.on_order == 0
        assert db.scalar(select(InventoryItem).where(InventoryItem.sku == "PARENT")) is None
        out_of_stock = db.scalar(select(InventoryItem).where(InventoryItem.sku == "VAR-OOS"))
        assert out_of_stock is not None
        assert out_of_stock.woo_product_id == 20
        assert out_of_stock.woo_variation_id == 201
        assert out_of_stock.in_stock == 0
        assert db.scalar(select(InventoryItem).where(InventoryItem.description == "Missing SKU")) is None
        assert int(db.scalar(select(func.count(StockMovement.id))) or 0) == movement_count

        attention = list(db.scalars(select(WooCatalogSyncRow).where(
            WooCatalogSyncRow.sync_run_id == run_id,
            WooCatalogSyncRow.status == "needs_attention",
        )).all())
        assert {row.remote_type for row in attention} == {"simple", "missing_remote"}
        assert any("no SKU" in (row.message or "") for row in attention)
        assert any(row.local_item_id == stale_id and "not returned" in row.message for row in attention)
        run = db.get(WooCommerceSyncRun, run_id)
        assert catalog_sync_run_read(run).progress_percent == 100
        assert run.created_count == 2
        assert run.matched_count == 1
        assert run.conflict_count == 2

    latest = client.get("/api/items", params={"latest_woo_import": True}).json()
    assert latest["total"] == 2
    assert {item["SKU"] for item in latest["items"]} == {"NEW-SIMPLE", "VAR-OOS"}


def test_catalog_uses_incremental_cursor_and_periodic_full_reconciliation(client):
    first_fake = CatalogClient({1: [product(10, "FIRST-SKU")]})
    first = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "first-full-catalog"},
    )
    assert first.status_code == 202
    first_run_id, first_status = run_to_terminal(client, first_fake)
    assert first_status == "completed"

    new_product = product(11, "NEW-SKU")
    second_fake = CatalogClient(
        {1: [product(10, "FIRST-SKU"), new_product]},
        delta_product_pages={1: [new_product]},
    )
    second = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "second-incremental-catalog"},
    )
    assert second.status_code == 202
    second_run_id, second_status = run_to_terminal(client, second_fake)

    assert second_status == "completed"
    product_calls = [call for call in second_fake.calls if call[0] == "products"]
    assert len(product_calls) == 1
    assert product_calls[0][-1]["modified_after"]
    with Session(client.test_engine) as db:
        assert db.scalar(select(InventoryItem.id).where(InventoryItem.sku == "FIRST-SKU")) is not None
        new_item_id = db.scalar(select(InventoryItem.id).where(InventoryItem.sku == "NEW-SKU"))
        second_rows = list(db.scalars(select(WooCatalogSyncRow).where(
            WooCatalogSyncRow.sync_run_id == second_run_id,
        )).all())
        assert new_item_id is not None, [
            (row.sku, row.status, row.action, row.message) for row in second_rows
        ]
        second_run = db.get(WooCommerceSyncRun, second_run_id)
        assert second_run.progress["scan_mode"] == "delta"
        assert second_run.conflict_count == 0
        first_run = db.get(WooCommerceSyncRun, first_run_id)
        first_run.completed_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.commit()

    periodic = client.post(
        "/api/integrations/woocommerce/catalog-syncs",
        headers={"Idempotency-Key": "periodic-full-catalog"},
    )
    assert periodic.status_code == 202
    with Session(client.test_engine) as db:
        periodic_run = db.get(WooCommerceSyncRun, periodic.json()["id"])
        assert periodic_run.progress["scan_mode"] == "full"


def test_catalog_sync_seeds_only_a_blank_local_barcode_from_woo(client):
    blank = seed_item(client, sku="BLANK-BARCODE", Barcode="")
    preserved = seed_item(client, sku="KEEP-BARCODE", Barcode="MANUAL-KEEP")
    fake = CatalogClient({1: [
        product(801, "BLANK-BARCODE", global_unique_id="000801"),
        product(802, "KEEP-BARCODE", global_unique_id="REMOTE-802"),
    ]})
    client.post("/api/integrations/woocommerce/catalog-syncs")

    _, status = run_to_terminal(client, fake)

    assert status == "completed"
    with Session(client.test_engine) as db:
        assert db.get(InventoryItem, blank["id"]).barcode == "000801"
        assert db.get(InventoryItem, preserved["id"]).barcode == "MANUAL-KEEP"


def test_catalog_pages_and_variations_are_checkpointed_one_remote_call_per_cycle(client):
    products = [product(index, f"BOUNDARY-{index}") for index in range(1, 100)]
    parent = product(100, "PARENT-100", type="variable")
    variations = [variation(10_000 + index, f"VAR-{index}") for index in range(100)]
    fake = CatalogClient(
        {1: [*products, parent]},
        {(100, 1): variations},
        product_total_pages=1,
        variation_total_pages={100: 1},
    )
    run_id = client.post("/api/integrations/woocommerce/catalog-syncs").json()["id"]

    work_once(client, fake)
    assert [call[0] for call in fake.calls] == ["products"]
    with Session(client.test_engine) as db:
        run = db.get(WooCommerceSyncRun, run_id)
        assert run.status == "fetching_products"
        assert run.progress["active_product_page"] == 1
        assert run.progress["product_total_pages"] == 1
        assert catalog_sync_run_read(run).progress_percent == 25.0

    work_once(client, fake)
    assert [call[0] for call in fake.calls] == ["products", "variations"]
    with Session(client.test_engine) as db:
        run = db.get(WooCommerceSyncRun, run_id)
        assert run.status == "fetching_variations"
        assert run.progress["variation_parent_index"] == 1
        assert catalog_sync_run_read(run).progress_percent == 49.0

    work_once(client, fake)
    assert [call[0] for call in fake.calls] == ["products", "variations"]
    assert not any(call[0] == "products" and call[1] == 2 for call in fake.calls)
    assert not any(call[0] == "variations" and call[2] == 2 for call in fake.calls)

    # Finishing the full pass is a database-only step; the following bounded
    # cycle performs exactly one final modified-since reconciliation page.
    work_once(client, fake)
    assert [call[0] for call in fake.calls] == ["products", "variations", "products"]
    assert fake.calls[-1][-1]["modified_after"]

    with Session(client.test_engine) as db:
        run = db.get(WooCommerceSyncRun, run_id)
        run.status = "fetching_products"
        run.progress = {
            "stage": "fetching_products",
            "scan_pass": "full",
            "active_product_page": 1,
            "product_total_pages": 4,
            "pending_variation_parent_keys": [],
        }
        assert catalog_sync_run_read(run).progress_percent == 12.5


def test_final_modified_since_pass_captures_product_added_during_full_walk(client):
    fake = CatalogClient(
        {1: [product(901, "BEFORE-SCAN", name="Original name")]},
        delta_product_pages={1: [
            product(901, "BEFORE-SCAN", name="Changed during scan"),
            product(902, "ADDED-DURING-SCAN"),
        ]},
    )
    client.post("/api/integrations/woocommerce/catalog-syncs")

    _, status = run_to_terminal(client, fake)

    assert status == "completed"
    with Session(client.test_engine) as db:
        assert db.scalar(select(InventoryItem).where(InventoryItem.sku == "ADDED-DURING-SCAN")) is not None
        changed = db.scalar(select(InventoryItem).where(InventoryItem.sku == "BEFORE-SCAN"))
        assert changed.woo_name == "Changed during scan"
        assert db.scalar(select(func.count(WooCatalogSyncRow.id))) == 2


def test_delta_parent_recheck_captures_variation_added_at_exact_page_boundary(client):
    parent = product(950, "PARENT-950", type="variable")
    initial = [variation(20_000 + index, f"BOUNDARY-VAR-{index}") for index in range(100)]
    added = variation(20_100, "VAR-ADDED-DURING-SCAN")

    class GrowingVariationClient(CatalogClient):
        def __init__(self):
            super().__init__(
                {1: [parent]},
                delta_product_pages={1: [parent]},
            )
            self.first_parent_pass_complete = False

        def list_product_variations(self, product_id, page=1, per_page=100, **kwargs):
            self.calls.append(("variations", product_id, page, per_page, kwargs))
            if not self.first_parent_pass_complete:
                self.first_parent_pass_complete = True
                self.last_response_headers = {"x-wp-totalpages": "1", "x-wp-total": "100"}
                return list(initial)
            self.last_response_headers = {"x-wp-totalpages": "2", "x-wp-total": "101"}
            return list(initial) if page == 1 else [added]

    fake = GrowingVariationClient()
    client.post("/api/integrations/woocommerce/catalog-syncs")

    _, status = run_to_terminal(client, fake, limit=40)

    assert status == "completed"
    variation_calls = [call for call in fake.calls if call[0] == "variations"]
    assert [call[2] for call in variation_calls] == [1, 1, 2]
    with Session(client.test_engine) as db:
        item = db.scalar(select(InventoryItem).where(InventoryItem.sku == "VAR-ADDED-DURING-SCAN"))
        assert item is not None
        assert item.woo_product_id == 950
        assert item.woo_variation_id == 20_100


def test_catalog_retry_after_is_persisted_and_bounded(client):
    client.post("/api/integrations/woocommerce/catalog-syncs")
    fake = FailingCatalogClient(WooCommerceClientError("rate limited", status_code=429), retry_after="120")
    before = datetime.now(timezone.utc)

    result = work_once(client, fake)

    assert result.status == "waiting_retry"
    retry_at = datetime.fromisoformat(result.progress["next_retry_at"])
    assert 115 <= (retry_at - before).total_seconds() <= 125
    assert retry_after_seconds("999999") == 3600
    assert retry_after_seconds("not a date") is None


def test_malformed_attention_can_be_skipped_and_human_decisions_are_retained(client):
    with Session(client.test_engine) as db:
        run = WooCommerceSyncRun(
            sync_type="catalog",
            status="completed_with_attention",
            total_remote_records=1,
            conflict_count=1,
            completed_at=datetime.now(timezone.utc),
            progress={"stage": "completed_with_attention", "scan_complete": True},
        )
        db.add(run)
        db.flush()
        row = WooCatalogSyncRow(
            sync_run_id=run.id,
            remote_key="malformed:manual",
            remote_type="malformed",
            status="needs_attention",
            action="attention",
            raw_payload={"product": {"name": "No remote ID"}},
        )
        db.add(row)
        db.commit()
        run_id, row_id = run.id, row.id

    resolved = client.post(
        f"/api/integrations/woocommerce/catalog-syncs/{run_id}/rows/{row_id}/resolve",
        json={"action": "skip"},
    )
    assert resolved.status_code == 200, resolved.text
    run_to_terminal(client, CatalogClient({1: []}))

    with Session(client.test_engine) as db:
        row = db.get(WooCatalogSyncRow, row_id)
        assert row.status == "skipped"
        assert row.resolution_action == "skip"
        row.updated_at = datetime.now(timezone.utc) - timedelta(days=31)
        automatic = WooCatalogSyncRow(
            sync_run_id=run_id,
            remote_key="product:auto-old",
            remote_type="simple",
            status="unchanged",
            action="unchanged",
            raw_payload={"product": product(500, "OLD")},
            updated_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        unresolved = WooCatalogSyncRow(
            sync_run_id=run_id,
            remote_key="product:attention-old",
            remote_type="simple",
            status="needs_attention",
            action="attention",
            raw_payload={"product": product(501, "ATTENTION")},
            updated_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        db.add_all([automatic, unresolved])
        db.commit()
        automatic_id, unresolved_id = automatic.id, unresolved.id
        assert prune_catalog_stage_rows(db) == 1
        db.commit()
        assert db.get(WooCatalogSyncRow, automatic_id) is None
        assert db.get(WooCatalogSyncRow, unresolved_id) is not None
        assert db.get(WooCatalogSyncRow, row_id) is not None


def test_explicit_link_rejects_non_inventory_and_active_other_run(client):
    with Session(client.test_engine) as db:
        non_inventory = InventoryItem(
            sku="SERVICE",
            in_stock=0,
            allocated=0,
            sellable=0,
            active=True,
            non_inventory=True,
        )
        old = WooCommerceSyncRun(
            sync_type="catalog",
            status="completed_with_attention",
            conflict_count=1,
            completed_at=datetime.now(timezone.utc),
            progress={"stage": "completed_with_attention"},
        )
        db.add_all([non_inventory, old])
        db.flush()
        row = WooCatalogSyncRow(
            sync_run_id=old.id,
            remote_key="product:700",
            remote_type="simple",
            woo_product_id=700,
            sku="SERVICE",
            normalized_sku="service",
            status="needs_attention",
            action="attention",
            raw_payload={"product": product(700, "SERVICE")},
        )
        db.add(row)
        db.commit()
        old_id, row_id, item_id = old.id, row.id, non_inventory.id

    rejected = client.post(
        f"/api/integrations/woocommerce/catalog-syncs/{old_id}/rows/{row_id}/resolve",
        json={"action": "link", "item_id": item_id},
    )
    assert rejected.status_code == 409
    assert "Non-inventory" in rejected.text

    with Session(client.test_engine) as db:
        active = WooCommerceSyncRun(sync_type="catalog", status="queued", progress={"stage": "queued"})
        db.add(active)
        db.commit()
    blocked_by_active = client.post(
        f"/api/integrations/woocommerce/catalog-syncs/{old_id}/rows/{row_id}/resolve",
        json={"action": "skip"},
    )
    assert blocked_by_active.status_code == 409
    assert "active catalog sync" in blocked_by_active.text


def test_resolution_that_loses_a_mapping_race_can_be_resolved_again(client):
    target = seed_item(client, sku="RACE-TARGET", Barcode="")
    with Session(client.test_engine) as db:
        run = WooCommerceSyncRun(
            sync_type="catalog",
            status="completed_with_attention",
            conflict_count=1,
            completed_at=datetime.now(timezone.utc),
            progress={"stage": "completed_with_attention"},
        )
        db.add(run)
        db.flush()
        row = WooCatalogSyncRow(
            sync_run_id=run.id,
            remote_key="product:880",
            remote_type="simple",
            woo_product_id=880,
            sku="RACE-TARGET",
            normalized_sku="race-target",
            status="needs_attention",
            action="attention",
            raw_payload={"product": product(880, "RACE-TARGET")},
        )
        db.add(row)
        db.commit()
        run_id, row_id = run.id, row.id

    queued = client.post(
        f"/api/integrations/woocommerce/catalog-syncs/{run_id}/rows/{row_id}/resolve",
        json={"action": "link", "item_id": target["id"]},
    )
    assert queued.status_code == 200
    with Session(client.test_engine) as db:
        db.add(WooItemMapping(
            item_id=target["id"],
            woo_product_id=881,
            active=True,
            mapping_source="manual",
        ))
        db.commit()
    _, status = run_to_terminal(client, CatalogClient({1: []}))
    assert status == "completed_with_attention"
    with Session(client.test_engine) as db:
        row = db.get(WooCatalogSyncRow, row_id)
        assert row.status == "needs_attention"
        assert row.resolution_action is None
        assert "failed" in row.message
        conflict = db.scalar(select(WooItemMapping).where(WooItemMapping.item_id == target["id"]))
        conflict.active = False
        db.commit()

    retried = client.post(
        f"/api/integrations/woocommerce/catalog-syncs/{run_id}/rows/{row_id}/resolve",
        json={"action": "link", "item_id": target["id"]},
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["resolution_action"] == "link"


def test_catalog_cancel_is_idempotent_and_prevents_network_work(client):
    run_id = client.post("/api/integrations/woocommerce/catalog-syncs").json()["id"]

    first = client.post(f"/api/integrations/woocommerce/catalog-syncs/{run_id}/cancel")
    repeat = client.post(f"/api/integrations/woocommerce/catalog-syncs/{run_id}/cancel")
    fake = CatalogClient({1: [product(990, "NEVER-FETCHED")]})

    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"
    assert repeat.status_code == 200
    assert work_once(client, fake) is None
    assert fake.calls == []


def test_catalog_partial_unique_indexes_cover_active_phase_and_global_variation_identity(client):
    with Session(client.test_engine) as db:
        db.add(WooCommerceSyncRun(sync_type="catalog", status="fetching_variations", progress={"stage": "fetching_variations"}))
        db.commit()
        db.add(WooCommerceSyncRun(sync_type="catalog", status="queued", progress={"stage": "queued"}))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        first = InventoryItem(sku="VAR-A", in_stock=0, allocated=0, sellable=0, active=True, non_inventory=False)
        second = InventoryItem(sku="VAR-B", in_stock=0, allocated=0, sellable=0, active=True, non_inventory=False)
        db.add_all([first, second])
        db.flush()
        db.add(WooItemMapping(item_id=first.id, woo_product_id=100, woo_variation_id=555, active=True))
        db.commit()
        db.add(WooItemMapping(item_id=second.id, woo_product_id=200, woo_variation_id=555, active=True))
        with pytest.raises(IntegrityError):
            db.commit()


def test_completed_with_attention_has_no_generic_resume(client):
    with Session(client.test_engine) as db:
        run = WooCommerceSyncRun(
            sync_type="catalog",
            status="completed_with_attention",
            completed_at=datetime.now(timezone.utc),
            progress={"stage": "completed_with_attention"},
        )
        db.add(run)
        db.commit()
        run_id = run.id

    response = client.post(f"/api/integrations/woocommerce/catalog-syncs/{run_id}/resume")
    assert response.status_code == 409
    assert "paused or failed" in response.text


def test_terminal_failures_pause_and_can_resume(client):
    with Session(client.test_engine) as db:
        run = WooCommerceSyncRun(sync_type="catalog", status="fetching_products", progress={"stage": "fetching_products"})
        db.add(run)
        db.commit()
        run_id = run.id
        record_catalog_failure(db, run_id, WooCommerceClientError("unauthorized", status_code=401))
        assert db.get(WooCommerceSyncRun, run_id).status == "paused"

    response = client.post(f"/api/integrations/woocommerce/catalog-syncs/{run_id}/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert response.json()["attempt_count"] == 0
