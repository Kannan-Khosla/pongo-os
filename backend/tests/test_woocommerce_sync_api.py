import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from tests.test_items_api import client, seed_item  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.models.orders import Order
from app.models.woocommerce import WooCommerceConfiguration
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_configuration import save_woocommerce_configuration, settings_with_persisted_woocommerce_configuration
from app.api.routes.woocommerce import woo_status_payload


class FakeWooClient:
    configured = True

    def __init__(self, records=None):
        self.records = records or []
        self.write_called = False

    def fetch_all_sellable_products_and_variations(self, statuses=None, limit=None):
        records = self.records
        return records[:limit] if limit else records

    def fetch_sellable_product_batch(self, page, per_page, statuses=None):
        return (self.records, False) if page == 1 else ([], False)

    def check_connection(self):
        return None


def test_woocommerce_credentials_use_basic_auth_and_never_enter_error_urls(monkeypatch):
    captured = {}

    def reject(method, url, **kwargs):
        captured.update(kwargs)
        request = httpx.Request(method, url, params=kwargs["params"])
        return httpx.Response(401, request=request, json={"message": "denied"})

    monkeypatch.setattr("app.services.woocommerce_client.httpx.request", reject)
    client = WooCommerceClient(Settings(
        _env_file=None,
        woocommerce_base_url="https://store.example",
        woocommerce_allowed_host="store.example",
        woocommerce_consumer_key="ck_must_not_leak",
        woocommerce_consumer_secret="cs_must_not_leak",
    ))

    with pytest.raises(WooCommerceClientError) as raised:
        client.check_connection()

    assert isinstance(captured["auth"], httpx.BasicAuth)
    assert "consumer_key" not in captured["params"]
    assert "consumer_secret" not in captured["params"]
    assert "ck_must_not_leak" not in repr(raised.value.__cause__)
    assert "cs_must_not_leak" not in repr(raised.value.__cause__)


def test_woocommerce_connection_check_requires_product_and_order_access(monkeypatch):
    paths = []

    def accept(method, url, **kwargs):
        paths.append(url)
        request = httpx.Request(method, url, params=kwargs["params"])
        return httpx.Response(200, request=request, json=[])

    monkeypatch.setattr("app.services.woocommerce_client.httpx.request", accept)
    client = WooCommerceClient(Settings(
        _env_file=None,
        woocommerce_base_url="https://store.example",
        woocommerce_allowed_host="store.example",
        woocommerce_consumer_key="ck_test",
        woocommerce_consumer_secret="cs_test",
    ))

    client.check_connection()

    assert paths == [
        "https://store.example/wp-json/wc/v3/products",
        "https://store.example/wp-json/wc/v3/orders",
    ]


def test_woocommerce_analytics_stats_collects_paginated_intervals(monkeypatch):
    client = WooCommerceClient(Settings(
        _env_file=None,
        woocommerce_base_url="https://store.example",
        woocommerce_consumer_key="ck_test",
        woocommerce_consumer_secret="cs_test",
    ))
    pages = []

    def request(_method, _path, params=None, payload=None):
        pages.append(params["page"])
        start = (params["page"] - 1) * 100
        count = 100 if params["page"] == 1 else 1
        return {
            "totals": {"orders_count": 101},
            "intervals": [{"interval": f"day-{index}", "subtotals": {}} for index in range(start, start + count)],
        }

    monkeypatch.setattr(client, "_request", request)

    result = client.analytics_stats("revenue", after="2026-01-01", before="2026-12-31")

    assert pages == [1, 2]
    assert len(result["intervals"]) == 101


def test_woocommerce_configuration_is_verified_and_saved_backend_only(tmp_path, monkeypatch):
    checked = []

    class ConnectionCheck:
        def __init__(self, settings):
            self.settings = settings

        def check_connection(self):
            checked.append(self.settings.woocommerce_base_url)

    env_path = tmp_path / ".env"
    env_path.write_text("APP_ENV=development\nKEEP_ME=yes\n", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        woocommerce_base_url="",
        woocommerce_consumer_key="",
        woocommerce_consumer_secret="",
        woocommerce_allowed_host="store.example",
    )

    saved = save_woocommerce_configuration(
        "https://store.example/",
        "ck_test_key",
        "cs_test_secret",
        env_path=env_path,
        settings=settings,
        client_type=ConnectionCheck,
    )

    assert checked == ["https://store.example"]
    assert saved.woocommerce_allowed_host == "store.example"
    contents = env_path.read_text(encoding="utf-8")
    assert "KEEP_ME=yes" in contents
    assert 'WOOCOMMERCE_BASE_URL="https://store.example"' in contents
    assert 'WOOCOMMERCE_CONSUMER_KEY="ck_test_key"' in contents
    assert 'WOOCOMMERCE_CONSUMER_SECRET="cs_test_secret"' in contents
    assert 'WOOCOMMERCE_ALLOWED_HOST="store.example"' in contents


def test_woocommerce_configuration_rejects_host_change_before_connection_check(tmp_path):
    class ConnectionCheck:
        def __init__(self, settings):
            raise AssertionError("connection check must not run")

    settings = Settings(
        _env_file=None,
        woocommerce_base_url="",
        woocommerce_consumer_key="ck_existing",
        woocommerce_consumer_secret="cs_existing",
        woocommerce_allowed_host="staging32.pongo.ca",
    )

    with pytest.raises(
        ValueError,
        match=(
            r"WooCommerce store host 'staging23\.pongo\.ca' does not match configured allowed host "
            r"'staging32\.pongo\.ca'. Retry with allow_host_change=true to replace the allowed host\."
        ),
    ):
        save_woocommerce_configuration(
            "https://staging23.pongo.ca",
            None,
            None,
            env_path=tmp_path / ".env",
            settings=settings,
            client_type=ConnectionCheck,
        )

    assert not (tmp_path / ".env").exists()


def test_woocommerce_configuration_does_not_persist_failed_verification(tmp_path):
    class ConnectionCheck:
        def __init__(self, settings):
            self.settings = settings

        def check_connection(self):
            raise WooCommerceClientError("credentials rejected")

    env_path = tmp_path / ".env"
    original = (
        'WOOCOMMERCE_BASE_URL="https://old.example"\n'
        'WOOCOMMERCE_CONSUMER_KEY="ck_old"\n'
        'WOOCOMMERCE_CONSUMER_SECRET="cs_old"\n'
        'WOOCOMMERCE_ALLOWED_HOST="old.example"\n'
    )
    env_path.write_text(original, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        woocommerce_consumer_key="ck_old",
        woocommerce_consumer_secret="cs_old",
        woocommerce_allowed_host="old.example",
    )

    with pytest.raises(WooCommerceClientError, match="credentials rejected"):
        save_woocommerce_configuration(
            "https://new.example",
            "ck_new",
            "cs_new",
            allow_host_change=True,
            env_path=env_path,
            settings=settings,
            client_type=ConnectionCheck,
        )

    assert env_path.read_text(encoding="utf-8") == original


def test_woocommerce_configuration_can_explicitly_replace_allowed_host(tmp_path):
    checked = []

    class ConnectionCheck:
        def __init__(self, settings):
            checked.append((settings.woocommerce_base_url, settings.woocommerce_allowed_host))

        def check_connection(self):
            return None

    env_path = tmp_path / ".env"
    settings = Settings(
        _env_file=None,
        woocommerce_base_url="",
        woocommerce_consumer_key="ck_existing",
        woocommerce_consumer_secret="cs_existing",
        woocommerce_allowed_host="staging32.pongo.ca",
    )

    saved = save_woocommerce_configuration(
        "https://staging23.pongo.ca/",
        "ck_replacement",
        "cs_replacement",
        allow_host_change=True,
        env_path=env_path,
        settings=settings,
        client_type=ConnectionCheck,
    )

    assert checked == [("https://staging23.pongo.ca", "staging23.pongo.ca")]
    assert saved.woocommerce_allowed_host == "staging23.pongo.ca"
    assert 'WOOCOMMERCE_ALLOWED_HOST="staging23.pongo.ca"' in env_path.read_text(encoding="utf-8")


def test_woocommerce_configuration_never_reuses_credentials_for_a_new_host(tmp_path):
    class ConnectionCheck:
        def __init__(self, settings):
            raise AssertionError("old credentials must never be sent to a new host")

    settings = Settings(
        _env_file=None,
        woocommerce_consumer_key="ck_existing",
        woocommerce_consumer_secret="cs_existing",
        woocommerce_allowed_host="old.example",
    )

    with pytest.raises(ValueError, match="fresh consumer key and secret"):
        save_woocommerce_configuration(
            "https://new.example",
            None,
            None,
            allow_host_change=True,
            env_path=tmp_path / ".env",
            settings=settings,
            client_type=ConnectionCheck,
        )


def test_woocommerce_configuration_cannot_mutate_runtime_production_secrets(tmp_path):
    settings = Settings(_env_file=None, app_env="production")

    with pytest.raises(ValueError, match="deployment environment"):
        save_woocommerce_configuration(
            "https://store.example",
            "ck_new",
            "cs_new",
            env_path=tmp_path / ".env",
            settings=settings,
        )


def test_production_configuration_is_encrypted_in_database_and_reused(tmp_path):
    class ConnectionCheck:
        def __init__(self, settings):
            self.settings = settings

        def check_connection(self):
            return None

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        app_env="production",
        woocommerce_configuration_encryption_key="test-encryption-key-that-is-longer-than-32-bytes",
    )

    with Session(engine) as db:
        save_woocommerce_configuration(
            "https://store.example",
            "ck_private",
            "cs_private",
            allow_host_change=True,
            env_path=tmp_path / ".env",
            settings=settings,
            client_type=ConnectionCheck,
            db=db,
            changed_by="pytest@example.com",
        )
        row = db.get(WooCommerceConfiguration, 1)
        assert row is not None
        assert row.updated_by == "pytest@example.com"
        assert "ck_private" not in row.consumer_key_ciphertext
        assert "cs_private" not in row.consumer_secret_ciphertext

        persisted = settings_with_persisted_woocommerce_configuration(db, settings)
        assert persisted.woocommerce_base_url == "https://store.example"
        assert persisted.woocommerce_allowed_host == "store.example"
        assert persisted.woocommerce_consumer_key == "ck_private"
        assert persisted.woocommerce_consumer_secret == "cs_private"

        db.add(Order(woo_order_id=1, woo_status="completed", local_status="completed"))
        db.commit()
        with pytest.raises(ValueError, match="isolated database"):
            save_woocommerce_configuration(
                "https://another-store.example",
                "ck_other",
                "cs_other",
                allow_host_change=True,
                env_path=tmp_path / ".env",
                settings=settings,
                client_type=ConnectionCheck,
                db=db,
                changed_by="pytest@example.com",
            )


def test_woocommerce_configuration_binds_blank_allowed_host(tmp_path):
    checked = []

    class ConnectionCheck:
        def __init__(self, settings):
            checked.append(settings.woocommerce_allowed_host)

        def check_connection(self):
            return None

    env_path = tmp_path / ".env"
    settings = Settings(
        _env_file=None,
        woocommerce_base_url="",
        woocommerce_consumer_key="ck_existing",
        woocommerce_consumer_secret="cs_existing",
        woocommerce_allowed_host="",
    )

    saved = save_woocommerce_configuration(
        "https://store.example",
        None,
        None,
        env_path=env_path,
        settings=settings,
        client_type=ConnectionCheck,
    )

    assert checked == ["store.example"]
    assert saved.woocommerce_allowed_host == "store.example"
    assert 'WOOCOMMERCE_ALLOWED_HOST="store.example"' in env_path.read_text(encoding="utf-8")


def test_woocommerce_configuration_never_reuses_credentials_across_hosts_without_allowed_host(tmp_path):
    settings = Settings(
        _env_file=None,
        woocommerce_base_url="https://old.example",
        woocommerce_consumer_key="ck_existing",
        woocommerce_consumer_secret="cs_existing",
        woocommerce_allowed_host="",
    )

    with pytest.raises(ValueError, match="fresh consumer key and secret"):
        save_woocommerce_configuration(
            "https://new.example",
            None,
            None,
            allow_host_change=True,
            env_path=tmp_path / ".env",
            settings=settings,
            client_type=lambda _settings: None,
        )


def test_woocommerce_configuration_response_never_exposes_keys(client, monkeypatch):
    saved_options = {}
    queued_syncs = []
    settings = Settings(
        _env_file=None,
        woocommerce_base_url="https://store.example",
        woocommerce_consumer_key="ck_private",
        woocommerce_consumer_secret="cs_private",
        woocommerce_allowed_host="store.example",
    )
    def save_configuration(*args, **kwargs):
        saved_options.update(kwargs)
        return settings

    monkeypatch.setattr("app.api.routes.woocommerce.save_woocommerce_configuration", save_configuration)
    monkeypatch.setattr("app.api.routes.woocommerce.enqueue_order_sync_job", lambda _db, actor: queued_syncs.append(actor))

    response = client.post(
        "/api/integrations/woocommerce/configuration",
        json={
            "base_url": "https://store.example",
            "consumer_key": "ck_private",
            "consumer_secret": "cs_private",
            "allow_host_change": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert saved_options["allow_host_change"] is True
    assert queued_syncs == ["pytest@example.com:configuration"]
    assert "ck_private" not in response.text
    assert "cs_private" not in response.text


def test_frontend_configuration_endpoint_persists_for_backend_status(client, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        woocommerce_environment="production",
        woocommerce_base_url="",
        woocommerce_allowed_host="",
        woocommerce_consumer_key="",
        woocommerce_consumer_secret="",
        woocommerce_configuration_encryption_key="test-encryption-key-that-is-longer-than-32-bytes",
    )
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.woocommerce_configuration.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.woocommerce_client.WooCommerceClient.check_connection", lambda _self: None)

    response = client.post(
        "/api/integrations/woocommerce/configuration",
        json={
            "base_url": "https://store.example",
            "consumer_key": "ck_private",
            "consumer_secret": "cs_private",
            "allow_host_change": True,
        },
    )
    assert response.status_code == 200
    assert "ck_private" not in response.text
    assert "cs_private" not in response.text

    status = client.get("/api/integrations/woocommerce/status").json()
    assert status["configured"] is True
    assert status["base_url"] == "https://store.example"
    assert status["configuration_source"] == "pongo_database"
    assert status["configuration_updated_by"] == "pytest@example.com"


def test_manual_order_fetch_is_queued_once(client):
    first = client.post("/api/integrations/woocommerce/orders/fetch-now", json={})
    second = client.post("/api/integrations/woocommerce/orders/fetch-now", json={})

    assert first.status_code == 202
    assert first.json()["status"] == "queued"
    assert second.json()["id"] == first.json()["id"]
    jobs = client.get("/api/integrations/woocommerce/orders/fetch-jobs").json()
    assert jobs["total"] == 1
    assert jobs["sync_runs"][0]["created_by"] == "pytest@example.com"


def simple_product(**overrides):
    product = {
        "id": 101,
        "type": "simple",
        "sku": "WOO-SIMPLE",
        "name": "Woo Simple Item",
        "short_description": "<p>Woo Simple Item</p>",
        "categories": [{"name": "Dog Food"}],
        "attributes": [{"name": "Brand", "options": ["North Paw"]}],
        "regular_price": "19.99",
        "sale_price": "17.99",
        "price": "17.99",
        "permalink": "https://example.invalid/product/woo-simple",
        "status": "publish",
        "manage_stock": True,
        "stock_quantity": 42,
        "stock_status": "instock",
        "weight": "2.5",
        "dimensions": {"length": "10", "width": "5", "height": "3"},
        "meta_data": [{"key": "barcode", "value": "WOO-BAR"}],
        "images": [{"src": "https://example.invalid/image.jpg"}],
    }
    product.update(overrides)
    return {"product": product, "variation": None}


def variation_product(**overrides):
    parent = {
        "id": 202,
        "type": "variable",
        "sku": "PARENT",
        "name": "Woo Variable Item",
        "categories": [{"name": "Treats"}],
        "attributes": [{"name": "Brand", "options": ["South Paw"]}],
        "status": "publish",
        "stock_status": "instock",
        "dimensions": {"length": "9", "width": "4", "height": "2"},
    }
    variation = {
        "id": 303,
        "sku": "WOO-VAR-SMALL",
        "attributes": [{"name": "Size", "option": "Small"}],
        "regular_price": "8.99",
        "sale_price": "",
        "price": "8.99",
        "permalink": "https://example.invalid/product/woo-variable?attribute_size=small",
        "status": "publish",
        "manage_stock": False,
        "stock_quantity": None,
        "stock_status": "instock",
        "weight": "1.2",
        "dimensions": {},
        "meta_data": [],
        "image": {"src": "https://example.invalid/variation.jpg"},
    }
    variation.update(overrides)
    return {"product": parent, "variation": variation}


def test_variation_parent_manage_stock_is_normalized(client, monkeypatch):
    record = variation_product(manage_stock="parent")
    record["product"]["manage_stock"] = True
    patch_woo_client(monkeypatch, [record])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    assert response.json()["created_count"] == 1


def patch_woo_client(monkeypatch, records):
    fake = FakeWooClient(records)
    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: fake)
    return fake


def test_woocommerce_status_returns_unconfigured_without_secrets(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.woocommerce.get_settings",
        lambda: type(
            "UnconfiguredWooSettings",
            (),
            {
                "woocommerce_base_url": "",
                "woocommerce_consumer_key": "",
                "woocommerce_consumer_secret": "",
                "woocommerce_timeout_seconds": 30,
                "woocommerce_page_size": 100,
                "woocommerce_order_sync_page_size": 100,
            },
        )(),
    )

    response = client.get("/api/integrations/woocommerce/status")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert "secret" not in body
    assert "WOOCOMMERCE_CONSUMER_SECRET" not in response.text


def test_woocommerce_status_limits_every_history_lookup():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    statements = []
    event.listen(engine, "before_cursor_execute", lambda _connection, _cursor, statement, _parameters, _context, _many: statements.append(statement))

    settings = Settings(_env_file=None)
    with Session(engine) as db:
        woo_status_payload(settings, WooCommerceClient(settings), db)

    history_queries = [
        statement.upper()
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
        and any(table in statement for table in ("woocommerce_sync_errors", "woocommerce_webhook_deliveries", "woocommerce_sync_runs"))
    ]
    assert history_queries
    assert all("LIMIT" in statement for statement in history_queries)


def test_woocommerce_preview_simple_product_with_sku_as_create(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product()])

    response = client.post("/api/integrations/woocommerce/products/preview", json={"include_statuses": ["publish"], "limit": 500})

    assert response.status_code == 200
    body = response.json()
    assert body["total_remote_records"] == 1
    assert body["create_count"] == 1
    assert body["preview_rows"][0]["action"] == "create"
    assert body["preview_rows"][0]["sku"] == "WOO-SIMPLE"


def test_woocommerce_preview_variation_with_sku_as_create(client, monkeypatch):
    patch_woo_client(monkeypatch, [variation_product()])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    row = response.json()["preview_rows"][0]
    assert row["remote_type"] == "variation"
    assert row["woo_product_id"] == 202
    assert row["woo_variation_id"] == 303
    assert row["action"] == "create"


def test_woocommerce_preview_skips_blank_sku(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product(sku="")])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    assert response.json()["skipped_count"] == 1
    assert response.json()["preview_rows"][0]["action"] == "skip"


def test_woocommerce_preview_matches_by_woo_ids_and_sku_but_not_barcode(client, monkeypatch):
    by_ids = seed_item(client, sku="LOCAL-IDS", wooProductId=101, wooVariationId=None)
    by_sku = seed_item(client, sku="WOO-SKU-MATCH")
    by_barcode = seed_item(client, sku="LOCAL-BAR", Barcode="REMOTE-BAR")
    records = [
        simple_product(id=101, sku="REMOTE-ID-SKU"),
        simple_product(id=102, sku="WOO-SKU-MATCH"),
        simple_product(id=103, sku="REMOTE-BAR-SKU", meta_data=[{"key": "barcode", "value": "REMOTE-BAR"}]),
    ]
    patch_woo_client(monkeypatch, records)

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    rows = response.json()["preview_rows"]
    assert rows[0]["local_item_id"] == by_ids["id"]
    assert rows[1]["local_item_id"] == by_sku["id"]
    assert rows[2]["local_item_id"] is None
    assert rows[2]["action"] == "create"
    assert response.json()["matched_count"] == 2


def test_woocommerce_preview_prefers_unique_sku_before_barcode_fallback(client, monkeypatch):
    sku_item = seed_item(client, sku="REMOTE-SKU", Barcode="LOCAL-1")
    seed_item(client, sku="OTHER", Barcode="REMOTE-BAR")
    patch_woo_client(monkeypatch, [simple_product(sku="REMOTE-SKU", meta_data=[{"key": "barcode", "value": "REMOTE-BAR"}])])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    assert response.json()["conflict_count"] == 0
    assert response.json()["preview_rows"][0]["action"] == "update"
    assert response.json()["preview_rows"][0]["local_item_id"] == sku_item["id"]


def test_woocommerce_preview_does_not_write_to_database_or_stock(client, monkeypatch):
    seed_item(client, sku="KEEP-STOCK", **{"In Stock": 7})
    patch_woo_client(monkeypatch, [simple_product(sku="KEEP-STOCK", stock_quantity=99)])

    response = client.post("/api/integrations/woocommerce/products/preview", json={})

    assert response.status_code == 200
    item = client.get("/api/items", params={"sku": "KEEP-STOCK"}).json()["items"][0]
    assert item["In Stock"] == 7
    assert item["wooProductId"] is None
    assert client.get("/api/stock-movements").json()["total"] == 1


def test_woocommerce_commit_creates_new_local_item_from_simple_product(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product()])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    item = client.get("/api/items", params={"sku": "WOO-SIMPLE"}).json()["items"][0]
    assert item["wooProductId"] == 101
    assert item["wooVariationId"] is None
    assert item["In Stock"] == 0
    assert item["wooStockQuantitySnapshot"] == 42


def test_woocommerce_commit_keeps_long_product_description(client, monkeypatch):
    description = "Long Woo description " * 40
    patch_woo_client(monkeypatch, [simple_product(description=f"<p>{description}</p>")])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    item = client.get("/api/items", params={"sku": "WOO-SIMPLE"}).json()["items"][0]
    assert item["Description"] == description.strip()


def test_woocommerce_commit_creates_new_local_item_from_variation(client, monkeypatch):
    patch_woo_client(monkeypatch, [variation_product()])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    item = client.get("/api/items", params={"sku": "WOO-VAR-SMALL"}).json()["items"][0]
    assert item["wooProductId"] == 202
    assert item["wooVariationId"] == 303
    assert item["Description"] == "Woo Variable Item - Small"


def test_woocommerce_commit_updates_existing_item_and_preserves_manual_fields(client, monkeypatch):
    seed_item(client, sku="WOO-SIMPLE", **{"In Stock": 11, "Allocated": 3, "Warehouse": "Manual Warehouse", "Inventory Location": "Manual Loc", "Unit Cost": 7})
    patch_woo_client(monkeypatch, [simple_product(stock_quantity=88)])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    item = client.get("/api/items", params={"sku": "WOO-SIMPLE"}).json()["items"][0]
    assert item["wooProductId"] == 101
    assert item["Description"] == "Woo Simple Item"
    assert item["Brand"] == "Test Brand"
    assert item["Sales Price"] == 17.99
    assert item["In Stock"] == 11
    assert item["Allocated"] == 3
    assert item["Warehouse"] == "Manual Warehouse"
    assert item["Inventory Location"] == "Manual Loc"
    assert item["Unit Cost"] == 7
    assert item["wooStockQuantitySnapshot"] == 88


def test_batched_catalog_mapping_preserves_local_items_and_reports_duplicates(client, monkeypatch):
    mapped = seed_item(client, sku="MAP-ME", Barcode="KEEP-BAR", **{"In Stock": 6, "Unit Cost": 7})
    barcode_fallback = seed_item(client, sku="LOCAL-BARCODE", Barcode="FALLBACK-BAR")
    duplicate_a = seed_item(client, sku="DUPLICATE-LOCAL", Barcode="DUP-A")
    duplicate_b = seed_item(client, sku="DUPLICATE-LOCAL", Barcode="DUP-B")
    records = [
        simple_product(id=501, sku="MAP-ME", name="Remote Name", stock_quantity=99),
        simple_product(id=502, sku="REMOTE-BARCODE", meta_data=[{"key": "barcode", "value": "FALLBACK-BAR"}]),
        simple_product(id=503, sku="DUPLICATE-LOCAL"),
        simple_product(id=504, sku="NEW-FROM-WOO"),
        simple_product(id=505, sku="REMOTE-DUPLICATE"),
        simple_product(id=506, sku="remote-duplicate"),
    ]
    patch_woo_client(monkeypatch, records)

    preview = client.post("/api/integrations/woocommerce/products/preview", json={"page": 1, "per_page": 50}).json()

    assert preview["has_more"] is False
    assert preview["create_count"] == 2
    assert preview["update_count"] == 1
    assert preview["conflict_count"] == 3
    assert any("Duplicate local SKU" in error for error in preview["errors"])
    assert sum("Duplicate WooCommerce SKU" in error for error in preview["errors"]) == 2

    commit = client.post(
        "/api/integrations/woocommerce/products/commit",
        json={"page": 1, "per_page": 50, "blocked_skus": ["remote-duplicate"]},
    ).json()

    assert commit["created_count"] == 2
    assert commit["updated_count"] == 1
    assert commit["conflict_count"] == 3
    assert commit["unmatched_local_count"] == 3
    assert set(commit["unmatched_local_skus"]) == {"DUPLICATE-LOCAL", "LOCAL-BARCODE"}
    mapped_after = client.get("/api/items", params={"sku": "MAP-ME"}).json()["items"][0]
    assert mapped_after["id"] == mapped["id"]
    assert mapped_after["wooProductId"] == 501
    assert mapped_after["Description"] == "Woo Simple Item"
    assert mapped_after["Barcode"] == "KEEP-BAR"
    assert mapped_after["In Stock"] == 6
    assert mapped_after["Unit Cost"] == 7
    barcode_after = client.get("/api/items", params={"sku": "LOCAL-BARCODE"}).json()["items"][0]
    assert barcode_after["id"] == barcode_fallback["id"]
    assert barcode_after["wooProductId"] is None
    assert client.get("/api/items", params={"sku": "REMOTE-BARCODE"}).json()["items"][0]["wooProductId"] == 502
    assert client.get("/api/items", params={"sku": "NEW-FROM-WOO"}).json()["items"][0]["wooProductId"] == 504
    assert all(client.get(f"/api/items/{item['id']}").json()["wooProductId"] is None for item in [duplicate_a, duplicate_b])


def test_woocommerce_commit_stores_sync_run_and_errors_for_skips(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product(sku="")])

    response = client.post("/api/integrations/woocommerce/products/commit", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["sync_run_id"]
    assert body["skipped_count"] == 1
    detail = client.get(f"/api/integrations/woocommerce/sync-runs/{body['sync_run_id']}")
    assert detail.status_code == 200
    assert detail.json()["errors"][0]["error_message"]


def test_woocommerce_commit_never_creates_stock_movement_or_write_calls(client, monkeypatch):
    fake = patch_woo_client(monkeypatch, [simple_product()])

    client.post("/api/integrations/woocommerce/products/commit", json={})

    assert client.get("/api/stock-movements").json()["total"] == 0
    assert fake.write_called is False


def test_woocommerce_sync_runs_list(client, monkeypatch):
    patch_woo_client(monkeypatch, [simple_product()])
    client.post("/api/integrations/woocommerce/products/commit", json={})

    response = client.get("/api/integrations/woocommerce/sync-runs")

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_variable_parent_with_three_variations_creates_three_items_and_is_idempotent(client, monkeypatch):
    first = variation_product(id=3101, sku="SIZE-S", attributes=[{"name": "Size", "option": "Small"}])
    first["variation"]["id"] = 3101
    medium = variation_product(id=3102, sku="SIZE-M", attributes=[{"name": "Size", "option": "Medium"}])
    medium["variation"]["id"] = 3102
    large = variation_product(id=3103, sku="SIZE-L", attributes=[{"name": "Size", "option": "Large"}])
    large["variation"]["id"] = 3103
    parent = {"product": first["product"], "variation": None, "parent_container": True}
    patch_woo_client(monkeypatch, [parent, first, medium, large])

    preview = client.post("/api/integrations/woocommerce/products/preview", json={}).json()
    first_commit = client.post("/api/integrations/woocommerce/products/commit", json={}).json()
    second_preview = client.post("/api/integrations/woocommerce/products/preview", json={}).json()
    second_commit = client.post("/api/integrations/woocommerce/products/commit", json={}).json()

    assert preview["variable_parents_examined"] == 1
    assert preview["purchasable_variations_examined"] == 3
    assert preview["skipped_parent_count"] == 1
    assert preview["new_variation_count"] == 3
    assert first_commit["created_count"] == 3
    assert client.get("/api/items").json()["total"] == 3
    items = client.get("/api/items").json()["items"]
    assert {item["wooProductId"] for item in items} == {202}
    assert {item["wooVariationId"] for item in items} == {3101, 3102, 3103}
    assert {item["SKU"] for item in items} == {"SIZE-S", "SIZE-M", "SIZE-L"}
    assert second_preview["unchanged_count"] == 3
    assert second_commit["created_count"] == 0
    assert second_commit["unchanged_count"] == 3
    assert client.get("/api/items").json()["total"] == 3


def test_later_new_variation_creates_only_one_item_and_mapping_targets_writeback(client, monkeypatch):
    first = variation_product(sku="LATER-S")
    first["variation"]["id"] = 4101
    patch_woo_client(monkeypatch, [first])
    assert client.post("/api/integrations/woocommerce/products/commit", json={}).json()["created_count"] == 1

    second = variation_product(sku="LATER-L", attributes=[{"name": "Size", "option": "Large"}])
    second["variation"]["id"] = 4102
    patch_woo_client(monkeypatch, [first, second])
    preview = client.post("/api/integrations/woocommerce/products/preview", json={}).json()
    commit = client.post("/api/integrations/woocommerce/products/commit", json={}).json()

    assert preview["new_variation_count"] == 1
    assert commit["created_count"] == 1
    assert client.get("/api/items").json()["total"] == 2
    item = client.get("/api/items", params={"sku": "LATER-L"}).json()["items"][0]
    writeback = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"item_id": item["id"]})
    assert writeback.status_code == 200
    assert writeback.json()["payload_json"]["path"] == "/wp-json/wc/v3/products/202/variations/4102"
