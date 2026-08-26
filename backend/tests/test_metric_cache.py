from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models.orders import Order
from app.models.performance import MetricCache
from app.services.metric_cache import cached_metric_payload
from app.services.metric_cache import current_metric_version
from tests.test_items_api import client, seed_item  # noqa: F401


def test_metric_cache_reuses_current_payload_and_invalidates_after_stock_source_change(client):
    override = app.dependency_overrides[get_db]()
    db = next(override)
    calls = 0

    def build():
        nonlocal calls
        calls += 1
        return {"build": calls}

    try:
        assert cached_metric_payload(db, "test:accuracy", {}, build) == {"build": 1}
        assert cached_metric_payload(db, "test:accuracy", {}, build) == {"build": 1}

        seed_item(client, sku="CACHE-INVALIDATION")

        assert cached_metric_payload(db, "test:accuracy", {}, build) == {"build": 1}
        cached = db.scalar(select(MetricCache).where(MetricCache.namespace == "test:accuracy"))
        assert cached.refresh_requested_at is not None
        assert cached_metric_payload(db, "test:accuracy", {}, build, force_refresh=True) == {"build": 2}
    finally:
        override.close()


def test_sync_bookkeeping_does_not_invalidate_metrics(client):
    override = app.dependency_overrides[get_db]()
    db = next(override)
    try:
        order = Order(
            woo_order_id=900001,
            status="processing",
            woo_status="processing",
            local_status="processing",
            raw_woo_payload={"refunds": []},
        )
        db.add(order)
        db.commit()
        cached_metric_payload(db, "test:no-op-sync", {}, lambda: {"value": 1})
        version = current_metric_version(db)

        db.refresh(order)
        order.last_synced_at = datetime.now(timezone.utc)
        order.raw_woo_payload = {"refunds": []}
        db.commit()

        assert current_metric_version(db) == version
        assert cached_metric_payload(db, "test:no-op-sync", {}, lambda: {"value": 2}) == {"value": 1}
    finally:
        override.close()


def test_metric_warming_builds_only_one_stale_key_per_cycle(client, monkeypatch):
    from app.services import metric_warming

    override = app.dependency_overrides[get_db]()
    db = next(override)
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    built = []

    def targets(session, _today):
        for name in ("one", "two"):
            yield name, name, {}, lambda name=name: cached_metric_payload(
                session, name, {}, lambda: built.append(name) or {"name": name}, force_refresh=True
            )

    monkeypatch.setattr(metric_warming, "SessionLocal", factory)
    monkeypatch.setattr(metric_warming, "standard_metric_targets", targets)
    settings = SimpleNamespace(admin_timezone="America/Edmonton")
    try:
        assert metric_warming.warm_next_standard_metric(settings) is True
        assert built == ["one"]
        assert db.scalar(select(MetricCache).where(MetricCache.namespace == "two")) is None
        assert metric_warming.warm_next_standard_metric(settings) is True
        assert built == ["one", "two"]
    finally:
        override.close()


def test_worker_refreshes_requested_custom_metric(client, monkeypatch):
    from app.services import metric_warming

    override = app.dependency_overrides[get_db]()
    db = next(override)
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    try:
        cached_metric_payload(db, "insight:overview", {"sku": "700"}, lambda: {"value": 1})
        db.add(Order(woo_order_id=900002, status="processing", woo_status="processing", local_status="processing"))
        db.commit()
        assert cached_metric_payload(db, "insight:overview", {"sku": "700"}, lambda: {"value": 2}) == {"value": 1}

        monkeypatch.setattr(metric_warming, "SessionLocal", factory)
        monkeypatch.setattr(
            metric_warming,
            "get_cached_insight",
            lambda session, dashboard, params, force_refresh=False: cached_metric_payload(
                session,
                f"insight:{dashboard}",
                params,
                lambda: {"value": 2},
                force_refresh=force_refresh,
            ),
        )
        assert metric_warming.warm_next_requested_metric() is True
        refreshed = db.scalar(select(MetricCache).where(MetricCache.namespace == "insight:overview"))
        db.refresh(refreshed)
        assert refreshed.payload == {"value": 2}
        assert refreshed.refresh_requested_at is None
    finally:
        override.close()


def test_worker_prioritizes_stock_and_only_warms_when_idle(monkeypatch):
    from app.workers import woocommerce as worker

    calls = []

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    settings = SimpleNamespace()
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "SessionLocal", DummySession)
    monkeypatch.setattr(worker, "ensure_automatic_order_sync_job", lambda *_args: None)
    monkeypatch.setattr(worker, "ensure_daily_full_stock_sync_job", lambda *_args: None)
    monkeypatch.setattr(worker, "process_next_order_sync_job", lambda *_args: calls.append("order"))
    monkeypatch.setattr(worker, "process_next_stock_sync_job", lambda *_args: calls.append("stock") or object())
    monkeypatch.setattr(worker, "process_next_report_job", lambda: calls.append("report"))
    monkeypatch.setattr(worker, "process_next_order_history_import", lambda *_args: calls.append("history"))
    monkeypatch.setattr(worker, "warm_metrics", lambda *_args: calls.append("warm"))

    assert worker.run_cycle() is True
    assert calls == ["order", "stock"]


def test_worker_keeps_live_subscriptions_ahead_of_one_catalog_step(monkeypatch):
    from app.workers import woocommerce as worker

    calls = []

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    settings = SimpleNamespace()
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "SessionLocal", DummySession)
    monkeypatch.setattr(worker, "ensure_automatic_order_sync_job", lambda *_args: None)
    monkeypatch.setattr(worker, "ensure_daily_full_stock_sync_job", lambda *_args: None)
    monkeypatch.setattr(worker, "process_next_order_sync_job", lambda *_args: calls.append("order"))
    monkeypatch.setattr(worker, "process_next_stock_sync_job", lambda *_args: calls.append("stock"))
    monkeypatch.setattr(worker, "process_next_item_import_job", lambda: calls.append("item-import"))
    monkeypatch.setattr(worker, "process_subscription_sync_if_due", lambda *_args: calls.append("subscriptions") or True)
    monkeypatch.setattr(worker, "process_next_catalog_sync", lambda *_args, **_kwargs: calls.append("catalog") or object())
    monkeypatch.setattr(worker, "process_next_report_job", lambda: calls.append("report"))

    assert worker.run_cycle() is True
    assert calls == ["order", "stock", "item-import", "subscriptions"]

    calls.clear()
    monkeypatch.setattr(worker, "process_subscription_sync_if_due", lambda *_args: calls.append("subscriptions") or False)
    assert worker.run_cycle() is True
    assert calls == ["order", "stock", "item-import", "subscriptions", "catalog"]
    assert worker._catalog_step_completed is True


def test_worker_reuses_catalog_http_pool_until_credentials_change(monkeypatch):
    from app.workers import woocommerce as worker

    instances = []

    class FakeClient:
        def __init__(self, settings):
            self.settings = settings
            self.open_count = 0
            self.close_count = 0
            instances.append(self)

        def open(self):
            self.open_count += 1
            return self

        def close(self):
            self.close_count += 1

    first_settings = SimpleNamespace(
        woocommerce_base_url="https://store.example",
        woocommerce_consumer_key="ck_one",
        woocommerce_consumer_secret="cs_one",
    )
    changed_settings = SimpleNamespace(
        woocommerce_base_url="https://store.example",
        woocommerce_consumer_key="ck_two",
        woocommerce_consumer_secret="cs_two",
    )
    worker._catalog_client = None
    worker._catalog_client_fingerprint = None
    monkeypatch.setattr(worker, "WooCommerceClient", FakeClient)

    first = worker.pooled_catalog_client(first_settings)
    second_page = worker.pooled_catalog_client(first_settings)
    replacement = worker.pooled_catalog_client(changed_settings)

    assert first is second_page
    assert first.open_count == 1
    assert first.close_count == 1
    assert replacement is not first
    assert replacement.open_count == 1
    worker._catalog_client = None
    worker._catalog_client_fingerprint = None
