import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.session import get_db
from app.main import app
from app.models.orders import Order
from app.models.woocommerce import WooCommerceAccessModeChange, WooStockSyncJob
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError, safe_woocommerce_error_message
from app.services.woocommerce_stock_sync_jobs import cancel_stock_sync_job, ensure_daily_full_stock_sync_job, process_next_stock_sync_job, run_stock_sync_job_scheduler, unresolved_stock_sync_job_count
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order
from tests.test_woocommerce_sync_api import patch_woo_client, simple_product


def staging_settings(**overrides):
    values = {
        "app_env": "development",
        "woocommerce_base_url": "https://staging32.pongo.ca/",
        "woocommerce_consumer_key": "ck_test_secret_value",
        "woocommerce_consumer_secret": "cs_test_secret_value",
        "woocommerce_environment": "staging",
        "woocommerce_read_enabled": True,
        "woocommerce_read_only": False,
        "woocommerce_writeback_enabled": True,
        "woocommerce_writeback_dry_run": False,
        "woocommerce_staging_live_test_mode": True,
        "woocommerce_allow_stock_write": True,
        "woocommerce_production_stock_authority": "disabled",
        "woocommerce_allow_order_status_write": True,
        "woocommerce_allow_product_metadata_write": False,
        "woocommerce_allow_customer_write": False,
        "woocommerce_allow_coupon_write": False,
        "woocommerce_allow_refund_write": False,
        "woocommerce_allow_delete": False,
        "woocommerce_allowed_host": "staging32.pongo.ca",
        "woocommerce_timeout_seconds": 30,
        "woocommerce_page_size": 100,
        "woocommerce_order_sync_page_size": 100,
        "woocommerce_stock_sync_job_stale_seconds": 900,
        "woocommerce_stock_sync_max_retries": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def stock_sync_db_factory():
    db = next(app.dependency_overrides[get_db]())
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, autocommit=False)
    db.close()
    return factory


def test_woocommerce_status_masks_credentials_and_shows_staging(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())

    response = client.get("/api/integrations/woocommerce/status")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["base_url_host"] == "staging32.pongo.ca"
    assert body["environment"] == "staging"
    assert body["dry_run"] is False
    assert body["staging_live_test_mode"] is True
    assert body["stock_write_allowed"] is True
    assert body["order_status_write_allowed"] is True
    assert "ck_test_secret_value" not in response.text
    assert "cs_test_secret_value" not in response.text


def test_woocommerce_access_mode_is_audited_and_enforced(client, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        woocommerce_base_url="https://store.example",
        woocommerce_allowed_host="store.example",
        woocommerce_consumer_key="ck_test_secret_value",
        woocommerce_consumer_secret="cs_test_secret_value",
        woocommerce_environment="production",
    )
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: settings)

    read_only = client.post("/api/integrations/woocommerce/access-mode", json={"access_mode": "read_only"})
    assert read_only.status_code == 200
    assert read_only.json()["access_mode"] == "read_only"
    assert client.get("/api/integrations/woocommerce/status").json()["writeback_enabled"] is False

    read_write = client.post("/api/integrations/woocommerce/access-mode", json={"access_mode": "read_write"})
    assert read_write.status_code == 200
    status = client.get("/api/integrations/woocommerce/status").json()
    assert status["access_mode"] == "read_write"
    assert status["read_only"] is False
    assert status["writeback_enabled"] is True
    assert status["dry_run"] is False
    assert status["stock_write_allowed"] is True
    assert status["order_status_write_allowed"] is True
    assert status["product_metadata_write_allowed"] is False
    assert status["customer_write_allowed"] is False
    assert status["coupon_write_allowed"] is False
    assert status["refund_write_allowed"] is False
    assert status["delete_allowed"] is False

    db = next(app.dependency_overrides[get_db]())
    try:
        changes = list(db.scalars(select(WooCommerceAccessModeChange).order_by(WooCommerceAccessModeChange.id)).all())
        assert [change.access_mode for change in changes] == ["read_only", "read_write"]
        assert all(change.changed_by for change in changes)
    finally:
        db.close()


def test_woocommerce_client_blocks_delete():
    client = WooCommerceClient(staging_settings())

    try:
        client.guarded_write("update_product_stock", "DELETE", "/wp-json/wc/v3/products/101", {})
    except WooCommerceClientError as error:
        assert "DELETE is blocked" in error.message
    else:
        raise AssertionError("DELETE should be blocked")


def test_woocommerce_write_permission_error_is_actionable():
    response = httpx.Response(
        401,
        json={
            "code": "woocommerce_rest_authentication_error",
            "message": "The API key provided does not have write permissions.",
        },
    )

    message = safe_woocommerce_error_message(response)

    assert "Read/Write" in message


def test_woocommerce_client_blocks_write_outside_staging():
    client = WooCommerceClient(staging_settings(woocommerce_environment="production"))

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "PRODUCTION_STOCK_AUTHORITY=pongo" in error.message
    else:
        raise AssertionError("Production stock writeback should be blocked")


def test_production_app_cannot_bypass_guard_by_claiming_staging():
    client = WooCommerceClient(
        staging_settings(
            app_env="production",
            woocommerce_environment="staging",
            woocommerce_production_stock_authority="pongo",
        )
    )

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "WOOCOMMERCE_ENVIRONMENT=production" in error.message
    else:
        raise AssertionError("A production app must never use staging write guards")


def test_woocommerce_client_allows_production_stock_only_with_explicit_pongo_authority(monkeypatch):
    client = WooCommerceClient(staging_settings(
        woocommerce_base_url="https://shop.pongo.ca/",
        woocommerce_allowed_host="shop.pongo.ca",
        woocommerce_environment="production",
        woocommerce_staging_live_test_mode=False,
        woocommerce_production_stock_authority="pongo",
    ))
    monkeypatch.setattr(client, "_request", lambda method, path, params=None, payload=None: {"id": 101, **payload})

    result = client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})

    assert result["stock_quantity"] == 3


def test_woocommerce_client_allows_explicit_production_order_completion(monkeypatch):
    client = WooCommerceClient(
        staging_settings(
            woocommerce_base_url="https://shop.pongo.ca/",
            woocommerce_allowed_host="shop.pongo.ca",
            woocommerce_environment="production",
            woocommerce_staging_live_test_mode=False,
            woocommerce_allow_stock_write=False,
        )
    )
    calls = []

    def fake_request(method, path, params=None, payload=None):
        calls.append((method, path, payload))
        return {"id": 851, "status": payload["status"]}

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.guarded_write(
        "update_order_status",
        "PUT",
        "/wp-json/wc/v3/orders/851",
        {"status": "completed"},
    )

    assert result == {"id": 851, "status": "completed"}
    assert calls == [("PUT", "/wp-json/wc/v3/orders/851", {"status": "completed"})]


def test_woocommerce_client_allows_only_completion_or_cancellation_status_in_production():
    client = WooCommerceClient(
        staging_settings(
            woocommerce_base_url="https://shop.pongo.ca/",
            woocommerce_allowed_host="shop.pongo.ca",
            woocommerce_environment="production",
            woocommerce_staging_live_test_mode=False,
        )
    )

    client.assert_woo_write_allowed(
        "update_order_status",
        "PUT",
        "/wp-json/wc/v3/orders/851",
        {"status": "cancelled"},
    )
    try:
        client.assert_woo_write_allowed(
            "update_order_status",
            "PUT",
            "/wp-json/wc/v3/orders/851",
            {"status": "pending"},
        )
    except WooCommerceClientError as error:
        assert "completed or cancelled" in error.message
    else:
        raise AssertionError("Production pending status writeback should be blocked.")


def test_woocommerce_client_blocks_write_in_read_only_mode():
    client = WooCommerceClient(staging_settings(woocommerce_read_only=True))

    try:
        client.guarded_write("update_order_status", "PUT", "/wp-json/wc/v3/orders/851", {"status": "completed"})
    except WooCommerceClientError as error:
        assert "read-only mode" in error.message
    else:
        raise AssertionError("Read-only mode must block writeback")


def test_woocommerce_client_blocks_host_mismatch():
    client = WooCommerceClient(staging_settings(woocommerce_allowed_host="different.example"))

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "allowed host" in error.message
    else:
        raise AssertionError("Host mismatch should be blocked")


def test_woocommerce_client_rejects_plaintext_or_noncanonical_base_url():
    for base_url in [
        "http://shop.pongo.ca",
        "https://user:pass@shop.pongo.ca",
        "https://shop.pongo.ca/store",
        "https://shop.pongo.ca?debug=1",
    ]:
        client = WooCommerceClient(staging_settings(
            app_env="production",
            woocommerce_base_url=base_url,
            woocommerce_allowed_host="shop.pongo.ca",
            woocommerce_environment="production",
            woocommerce_production_stock_authority="pongo",
        ))
        try:
            client._request("GET", "/wp-json/wc/v3/products", params={"per_page": 1})
        except WooCommerceClientError as error:
            assert "HTTPS" in error.message or "canonical" in error.message
        else:
            raise AssertionError(f"Unsafe WooCommerce base URL should be blocked: {base_url}")


def test_woocommerce_client_blocks_writeback_disabled():
    client = WooCommerceClient(staging_settings(woocommerce_writeback_enabled=False))

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "disabled" in error.message
    else:
        raise AssertionError("Disabled writeback should be blocked")


def test_woocommerce_client_blocks_dry_run_write():
    client = WooCommerceClient(staging_settings(woocommerce_writeback_dry_run=True))

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "dry-run" in error.message
    else:
        raise AssertionError("Dry-run writeback should be blocked")


def test_woocommerce_client_blocks_when_live_test_mode_false():
    client = WooCommerceClient(staging_settings(woocommerce_staging_live_test_mode=False))

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "live staging test mode" in error.message
    else:
        raise AssertionError("Live staging mode should be required")


def test_woocommerce_client_blocks_product_metadata_payload():
    client = WooCommerceClient(staging_settings())

    try:
        client.guarded_write("update_product_stock", "PATCH", "/wp-json/wc/v3/products/101", {"name": "Nope", "stock_quantity": 3})
    except WooCommerceClientError as error:
        assert "non-allowlisted fields" in error.message
    else:
        raise AssertionError("Product metadata payload should be blocked")


def test_stock_preview_creates_no_woo_request(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="STAGE-STOCK", wooProductId=101, **{"In Stock": 8, "Allocated": 2})

    response = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "STAGE-STOCK"})

    assert response.status_code == 200
    body = response.json()
    assert body["operation_type"] == "update_product_stock"
    assert body["payload_json"]["body"]["stock_quantity"] == 6


def test_stock_preview_fails_closed_for_duplicate_sku(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="DUPLICATE-STOCK-SKU", wooProductId=111)
    seed_item(client, sku="DUPLICATE-STOCK-SKU", wooProductId=112)

    response = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "DUPLICATE-STOCK-SKU"})

    assert response.status_code == 409
    assert "duplicate_sku_conflict" in response.text


def test_order_status_preview_creates_no_woo_request(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101)
    patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})

    response = client.post("/api/integrations/woocommerce/writeback/order-status/preview", json={"woo_order_id": 501, "proposed_status": "completed"})

    assert response.status_code == 200
    body = response.json()
    assert body["operation_type"] == "update_order_status"
    assert body["payload_json"]["body"]["status"] == "completed"


def test_historical_snapshot_cannot_be_previewed_or_queued_for_writeback(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    db = next(app.dependency_overrides[get_db]())
    try:
        order = Order(
            woo_order_id=9501,
            order_number="HISTORY-9501",
            woo_status="completed",
            local_status="completed",
            is_historical_snapshot=True,
        )
        db.add(order)
        db.commit()
        order_id = order.id
    finally:
        db.close()

    preview = client.post(
        "/api/integrations/woocommerce/writeback/order-status/preview",
        json={"order_id": order_id, "proposed_status": "completed"},
    )
    forged_queue = client.post(
        "/api/integrations/woocommerce/writeback/queue",
        json={
            "operation_type": "update_order_status",
            "entity_type": "order",
            "entity_id": order_id,
            "woo_entity_id": 9501,
            "woo_order_id": 9501,
            "payload_json": {"method": "PUT", "path": "/wp-json/wc/v3/orders/9501", "body": {"status": "completed"}},
            "preview_json": {},
        },
    )

    assert preview.status_code == 404
    assert forged_queue.status_code == 400
    assert "historical snapshots" in forged_queue.text


def test_queue_creates_local_row_only(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="QUEUE-STOCK", wooProductId=202, **{"In Stock": 4})
    preview = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "QUEUE-STOCK"}).json()

    response = client.post("/api/integrations/woocommerce/writeback/queue", json=preview)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert client.get("/api/integrations/woocommerce/writeback/queue").json()["total"] == 1


def test_dry_run_send_does_not_call_woo(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings(woocommerce_writeback_dry_run=True))
    seed_item(client, sku="DRY-STOCK", wooProductId=303, **{"In Stock": 7})
    preview = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "DRY-STOCK"}).json()
    queued = client.post("/api/integrations/woocommerce/writeback/queue", json=preview).json()
    client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/approve")

    class NoCallWoo:
        def guarded_write(self, *args, **kwargs):
            raise AssertionError("Dry-run send must not call WooCommerce")

    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: NoCallWoo())
    sent = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/send")

    assert sent.status_code == 200
    assert sent.json()["status"] == "dry_run"
    assert sent.json()["response_json"]["dry_run"] is True


def test_non_dry_run_send_calls_allowlisted_operation(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="SEND-STOCK", wooProductId=404, **{"In Stock": 9})
    preview = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "SEND-STOCK"}).json()
    queued = client.post("/api/integrations/woocommerce/writeback/queue", json=preview).json()
    client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/approve")
    calls = []

    class FakeWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append((operation_type, method, path, payload))
            return {"id": 404, "stock_quantity": payload["stock_quantity"]}

    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: FakeWoo())
    sent = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/send")

    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert calls == [("update_product_stock", "PATCH", "/wp-json/wc/v3/products/404", {"manage_stock": True, "stock_quantity": 6.0, "stock_status": "instock"})]


def test_failed_legacy_order_status_queue_can_retry_with_woo_put(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="RETRY-ORDER", Barcode="RETRY-BAR", wooProductId=101)
    patch_woo_order_client(monkeypatch, [woo_order(id=777, number="777")])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    preview = client.post(
        "/api/integrations/woocommerce/writeback/order-status/preview",
        json={"woo_order_id": 777, "proposed_status": "completed"},
    ).json()
    preview["payload_json"]["method"] = "PATCH"
    queued = client.post("/api/integrations/woocommerce/writeback/queue", json=preview).json()
    client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/approve")

    class FailedWoo:
        def guarded_write(self, *args, **kwargs):
            raise WooCommerceClientError("WooCommerce API returned an error.", status_code=405)

    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: FailedWoo())
    failed = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/send").json()
    assert failed["status"] == "failed"
    assert "HTTP 405" in failed["error_message"]

    retried = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/approve").json()
    assert retried["status"] == "approved"
    calls = []

    class SuccessfulWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append((operation_type, method, path, payload))
            return {"id": 777, "status": "completed"}

    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: SuccessfulWoo())
    sent = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/send").json()

    assert sent["status"] == "sent"
    assert sent["payload_json"]["method"] == "PUT"
    assert calls == [("update_order_status", "PUT", "/wp-json/wc/v3/orders/777", {"status": "completed"})]


def test_send_requires_approval(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="NEEDS-APPROVAL", wooProductId=505, **{"In Stock": 2, "Allocated": 0})
    preview = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "NEEDS-APPROVAL"}).json()
    queued = client.post("/api/integrations/woocommerce/writeback/queue", json=preview).json()

    sent = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/send")

    assert sent.status_code == 200
    assert sent.json()["status"] == "failed"
    assert "approved" in sent.json()["error_message"]


def test_logs_include_failed_cancelled_and_sent(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="LOG-STOCK", wooProductId=606, **{"In Stock": 3})
    preview = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"sku": "LOG-STOCK"}).json()
    queued = client.post("/api/integrations/woocommerce/writeback/queue", json=preview).json()
    client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/cancel")

    logs = client.get("/api/integrations/woocommerce/writeback/logs")

    assert logs.status_code == 200
    assert logs.json()["total"] == 1
    assert logs.json()["queue"][0]["status"] == "cancelled"


def test_stock_sync_updates_only_changed_items_then_can_force_all(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="CHANGED-STOCK", wooProductId=701, wooStockQuantitySnapshot=3, **{"In Stock": 8})
    seed_item(client, sku="UNCHANGED-STOCK", wooProductId=702, wooStockQuantitySnapshot=2, **{"In Stock": 5})
    calls = []

    class FakeWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append((path, payload["stock_quantity"]))
            return {"stock_quantity": payload["stock_quantity"]}

    changed = client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": False, "idempotency_key": "changed-stock-job", "chunk_size": 10},
    )

    assert changed.status_code == 202
    assert changed.json()["status"] == "queued"
    assert client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": False, "idempotency_key": "changed-stock-job", "chunk_size": 10},
    ).json()["id"] == changed.json()["id"]
    process_next_stock_sync_job(staging_settings(), db_factory=stock_sync_db_factory(), client_factory=lambda _settings: FakeWoo())
    process_next_stock_sync_job(staging_settings(), db_factory=stock_sync_db_factory(), client_factory=lambda _settings: FakeWoo())
    completed = client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{changed.json()['id']}").json()
    assert completed["status"] == "completed"
    assert completed["sent_count"] == 1
    assert completed["unchanged_count"] == 1
    assert calls == [("/wp-json/wc/v3/products/701", 5.0)]

    calls.clear()
    all_items = client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": True, "idempotency_key": "force-stock-job", "chunk_size": 10},
    )

    assert all_items.status_code == 202
    process_next_stock_sync_job(staging_settings(), db_factory=stock_sync_db_factory(), client_factory=lambda _settings: FakeWoo())
    process_next_stock_sync_job(staging_settings(), db_factory=stock_sync_db_factory(), client_factory=lambda _settings: FakeWoo())
    completed_all = client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{all_items.json()['id']}").json()
    assert completed_all["sent_count"] == 2
    assert calls == [("/wp-json/wc/v3/products/701", 5.0), ("/wp-json/wc/v3/products/702", 2.0)]


def test_daily_full_stock_sync_is_forced_and_idempotent_per_admin_day(client):
    seed_item(client, sku="DAILY-STOCK", wooProductId=703, **{"In Stock": 5})
    factory = stock_sync_db_factory()
    settings = staging_settings(woocommerce_daily_full_stock_sync_enabled=True, admin_timezone="America/Edmonton")
    with factory() as db:
        before_first_midnight = ensure_daily_full_stock_sync_job(db, settings, now=datetime(2026, 8, 3, 23, 0, tzinfo=timezone.utc))
        first = ensure_daily_full_stock_sync_job(db, settings, now=datetime(2026, 8, 4, 6, 5, tzinfo=timezone.utc))
        duplicate = ensure_daily_full_stock_sync_job(db, settings, now=datetime(2026, 8, 4, 23, 0, tzinfo=timezone.utc))
        next_day = ensure_daily_full_stock_sync_job(db, settings, now=datetime(2026, 8, 5, 6, 5, tzinfo=timezone.utc))
        first_id, duplicate_id, next_day_id = first.id, duplicate.id, next_day.id
        first_force, first_requester = first.force, first.requested_by

    assert before_first_midnight is None
    assert first_force is True
    assert duplicate_id == first_id
    assert next_day_id != first_id
    assert first_requester == "daily-midnight-stock-sync"


def test_stock_sync_recovers_a_stale_running_chunk(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    item = seed_item(client, sku="CRASH-RECOVERY", wooProductId=799, **{"In Stock": 4})
    created = client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": True, "idempotency_key": "crash-recovery-job", "chunk_size": 10},
    ).json()
    factory = stock_sync_db_factory()
    with factory() as db:
        job = db.get(WooStockSyncJob, created["id"])
        job.status = "running"
        job.retry_item_ids = [item["id"]]
        job.last_item_id = item["id"]
        job.processed_items = 1
        db.commit()

    calls = []

    class FakeWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append((path, payload["stock_quantity"]))
            return {"stock_quantity": payload["stock_quantity"]}

    settings = staging_settings(woocommerce_stock_sync_job_stale_seconds=0)
    process_next_stock_sync_job(settings, db_factory=factory, client_factory=lambda _settings: FakeWoo())
    process_next_stock_sync_job(settings, db_factory=factory, client_factory=lambda _settings: FakeWoo())

    completed = client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{created['id']}").json()
    assert completed["status"] == "completed"
    assert calls == [("/wp-json/wc/v3/products/799", 1.0)]


def test_completed_stock_sync_failures_can_be_resumed(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="RESUME-FAILED-STOCK", wooProductId=798, **{"In Stock": 4})
    created = client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": True, "idempotency_key": "resume-failed-stock-job", "chunk_size": 10},
    ).json()
    factory = stock_sync_db_factory()

    class FailedWoo:
        def guarded_write(self, *args, **kwargs):
            raise WooCommerceClientError("temporary failure")

    settings = staging_settings(woocommerce_stock_sync_max_retries=0)
    process_next_stock_sync_job(settings, db_factory=factory, client_factory=lambda _settings: FailedWoo())
    process_next_stock_sync_job(settings, db_factory=factory, client_factory=lambda _settings: FailedWoo())
    failed = client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{created['id']}").json()
    assert failed["status"] == "completed_with_errors"
    assert failed["failed_count"] == 1
    with factory() as db:
        assert unresolved_stock_sync_job_count(db) == 1

    assert client.post(f"/api/integrations/woocommerce/writeback/stock/jobs/{created['id']}/resume").status_code == 200

    class SuccessfulWoo:
        def guarded_write(self, operation_type, method, path, payload):
            return {"stock_quantity": payload["stock_quantity"]}

    process_next_stock_sync_job(settings, db_factory=factory, client_factory=lambda _settings: SuccessfulWoo())
    process_next_stock_sync_job(settings, db_factory=factory, client_factory=lambda _settings: SuccessfulWoo())
    completed = client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{created['id']}").json()
    assert completed["status"] == "completed"
    assert completed["failed_count"] == 0
    assert completed["sent_count"] == 1
    with factory() as db:
        assert unresolved_stock_sync_job_count(db) == 0


def test_stock_sync_scheduler_alerts_on_terminal_item_failures(monkeypatch):
    job = SimpleNamespace(id=91, status="completed_with_errors", failed_count=2, last_error="two mappings failed")
    captured = {}

    class StopAfterOne:
        calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls > 1

        async def wait(self):
            return None

    monkeypatch.setattr("app.services.woocommerce_stock_sync_jobs.process_next_stock_sync_job", lambda _settings: job)
    monkeypatch.setattr("app.services.woocommerce_stock_sync_jobs.send_operations_alert", lambda _settings, event, message, **details: captured.update(event=event, message=message, details=details) or True)
    settings = staging_settings(
        woocommerce_stock_sync_job_interval_seconds=1,
        operations_alert_failure_threshold=3,
        operations_alert_webhook_url="https://alerts.example.invalid/hook",
    )

    asyncio.run(run_stock_sync_job_scheduler(settings, StopAfterOne()))

    assert captured["event"] == "woo_stock_sync_job_requires_review"
    assert captured["details"]["failed_count"] == 2
    monkeypatch.setattr("app.services.woocommerce_stock_sync_jobs.process_next_stock_sync_job", lambda _settings: None)
    asyncio.run(run_stock_sync_job_scheduler(settings, StopAfterOne()))


def test_running_stock_sync_cancel_stops_between_items_and_keeps_completed_counts(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="CANCEL-STOCK-A", wooProductId=796, **{"In Stock": 4})
    seed_item(client, sku="CANCEL-STOCK-B", wooProductId=797, **{"In Stock": 5})
    created = client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": True, "idempotency_key": "cancel-running-stock-job", "chunk_size": 10},
    ).json()
    factory = stock_sync_db_factory()
    calls = []

    class CancellingWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append(path)
            with factory() as other:
                cancel_stock_sync_job(other, created["id"])
            return {"stock_quantity": payload["stock_quantity"]}

    process_next_stock_sync_job(staging_settings(), db_factory=factory, client_factory=lambda _settings: CancellingWoo())
    cancelled = client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{created['id']}").json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["sent_count"] == 1
    assert len(calls) == 1


def test_stock_sync_recovers_unambiguous_mapping_from_imported_order(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    seed_item(client, sku="ORDER-MAPPED-STOCK", Barcode="ORDER-MAPPED-BAR", **{"In Stock": 6})
    line = {
        **woo_order()["line_items"][0],
        "product_id": 704,
        "variation_id": 705,
        "sku": "ORDER-MAPPED-STOCK",
        "meta_data": [{"key": "barcode", "value": "ORDER-MAPPED-BAR"}],
    }
    patch_woo_order_client(monkeypatch, [woo_order(id=704, number="704", line_items=[line])])
    assert client.post("/api/integrations/woocommerce/orders/commit", json={}).status_code == 200
    calls = []

    class FakeWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append((operation_type, path, payload))
            return {"stock_quantity": payload["stock_quantity"], "stock_status": payload["stock_status"]}

    response = client.post(
        "/api/integrations/woocommerce/writeback/stock/sync",
        json={"force": False, "idempotency_key": "recovered-stock-job", "chunk_size": 10},
    )

    assert response.status_code == 202
    process_next_stock_sync_job(staging_settings(), db_factory=stock_sync_db_factory(), client_factory=lambda _settings: FakeWoo())
    process_next_stock_sync_job(staging_settings(), db_factory=stock_sync_db_factory(), client_factory=lambda _settings: FakeWoo())
    assert client.get(f"/api/integrations/woocommerce/writeback/stock/jobs/{response.json()['id']}").json()["sent_count"] == 1
    assert calls == [
        (
            "update_variation_stock",
            "/wp-json/wc/v3/products/704/variations/705",
            {"manage_stock": True, "stock_quantity": 1.0, "stock_status": "instock"},
        )
    ]
    item = client.get("/api/items", params={"sku": "ORDER-MAPPED-STOCK"}).json()["items"][0]
    assert item["wooProductId"] == 704
    assert item["wooVariationId"] == 705
    assert item["wooStockQuantitySnapshot"] == 1
    assert item["wooStockStatus"] == "instock"


def test_manual_stock_adjustment_writes_changed_item_to_woo(client, monkeypatch):
    settings = staging_settings()
    monkeypatch.setattr("app.api.routes.inventory.get_settings", lambda: settings)
    item = seed_item(client, sku="ADJUST-WRITEBACK", wooProductId=703, wooStockQuantitySnapshot=6, **{"In Stock": 6})
    location = client.get("/api/inventory/locations", params={"item_id": item["id"]}).json()["rows"][0]
    calls = []

    def fake_write(self, operation_type, method, path, payload):
        calls.append((operation_type, path, payload["stock_quantity"]))
        return {"stock_quantity": payload["stock_quantity"]}

    monkeypatch.setattr("app.api.routes.inventory.WooCommerceClient.guarded_write", fake_write)

    response = client.post(
        "/api/inventory/adjustments",
        json={
            "idempotency_key": "writeback-adjustment",
            "adjustment_type": "manual_increase",
            "reason": "Physical count correction",
            "created_by": "pytest",
            "lines": [{"item_id": item["id"], "inventory_item_location_id": location["id"], "new_quantity": 8}],
        },
    )

    assert response.status_code == 201, response.text
    assert calls == [("update_product_stock", "/wp-json/wc/v3/products/703", 5.0)]


def test_writeback_missing_duplicate_and_incomplete_mappings_fail_closed(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings())
    missing = seed_item(client, sku="NO-WOO-MAPPING")
    assert client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"item_id": missing["id"]}).status_code == 409

    seed_item(client, sku="DUP-MAP-1", wooProductId=8801)
    duplicate = seed_item(client, sku="DUP-MAP-2", wooProductId=8801)
    conflict = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"item_id": duplicate["id"]})
    assert conflict.status_code == 409
    assert "woo_mapping_conflict" in conflict.text

    incomplete = seed_item(client, sku="INCOMPLETE-VAR", wooProductId=8802, wooProductType="variation")
    invalid = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"item_id": incomplete["id"]})
    assert invalid.status_code == 409
    assert "woo_variation_mapping_incomplete" in invalid.text


def test_stale_pending_stock_writeback_can_be_revalidated_and_must_be_reapproved(client, monkeypatch):
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: staging_settings(woocommerce_writeback_dry_run=True))
    patch_woo_client(monkeypatch, [simple_product(id=9901, sku="REVALIDATE")])
    assert client.post("/api/integrations/woocommerce/products/commit", json={}).status_code == 200
    item = client.get("/api/items", params={"sku": "REVALIDATE"}).json()["items"][0]
    preview = client.post("/api/integrations/woocommerce/writeback/stock/preview", json={"item_id": item["id"]}).json()
    preview["payload_json"]["path"] = "/wp-json/wc/v3/products/123"
    queued = client.post("/api/integrations/woocommerce/writeback/queue", json=preview).json()

    blocked = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/approve")
    revalidated = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/revalidate")
    approved = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/approve")
    sent = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/send")
    immutable = client.post(f"/api/integrations/woocommerce/writeback/queue/{queued['id']}/revalidate")

    assert blocked.status_code == 409
    assert "woo_writeback_target_stale" in blocked.text
    assert revalidated.status_code == 200
    assert revalidated.json()["status"] == "pending"
    assert revalidated.json()["payload_json"]["path"] == "/wp-json/wc/v3/products/9901"
    assert revalidated.json()["approved_by"] is None
    assert approved.json()["status"] == "approved"
    assert sent.json()["status"] == "dry_run"
    assert immutable.status_code == 409
