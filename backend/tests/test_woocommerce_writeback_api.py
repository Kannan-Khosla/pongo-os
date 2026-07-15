from types import SimpleNamespace

import httpx

from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError, safe_woocommerce_error_message
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def staging_settings(**overrides):
    values = {
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
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
        assert "limited to allowlisted order completion" in error.message
    else:
        raise AssertionError("Production stock writeback should be blocked")


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


def test_woocommerce_client_blocks_non_completion_status_in_production():
    client = WooCommerceClient(
        staging_settings(
            woocommerce_base_url="https://shop.pongo.ca/",
            woocommerce_allowed_host="shop.pongo.ca",
            woocommerce_environment="production",
            woocommerce_staging_live_test_mode=False,
        )
    )

    try:
        client.guarded_write("update_order_status", "PUT", "/wp-json/wc/v3/orders/851", {"status": "cancelled"})
    except WooCommerceClientError as error:
        assert "only set status to completed" in error.message
    else:
        raise AssertionError("Production order writeback must be completion-only")


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
    assert body["payload_json"]["body"]["stock_quantity"] == 8


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
    assert calls == [("update_product_stock", "PATCH", "/wp-json/wc/v3/products/404", {"manage_stock": True, "stock_quantity": 9.0, "stock_status": "instock"})]


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
    seed_item(client, sku="NEEDS-APPROVAL", wooProductId=505, **{"In Stock": 2})
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
    seed_item(client, sku="UNCHANGED-STOCK", wooProductId=702, wooStockQuantitySnapshot=5, **{"In Stock": 5})
    calls = []

    class FakeWoo:
        def guarded_write(self, operation_type, method, path, payload):
            calls.append((path, payload["stock_quantity"]))
            return {"stock_quantity": payload["stock_quantity"]}

    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: FakeWoo())

    changed = client.post("/api/integrations/woocommerce/writeback/stock/sync", json={"force": False})

    assert changed.status_code == 200
    assert changed.json()["status"] == "sent"
    assert changed.json()["candidate_count"] == 1
    assert changed.json()["sent_count"] == 1
    assert changed.json()["unchanged_count"] == 1
    assert calls == [("/wp-json/wc/v3/products/701", 8.0)]

    calls.clear()
    all_items = client.post("/api/integrations/woocommerce/writeback/stock/sync", json={"force": True})

    assert all_items.status_code == 200
    assert all_items.json()["candidate_count"] == 2
    assert all_items.json()["sent_count"] == 2
    assert calls == [("/wp-json/wc/v3/products/701", 8.0), ("/wp-json/wc/v3/products/702", 5.0)]


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

    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: FakeWoo())

    response = client.post("/api/integrations/woocommerce/writeback/stock/sync", json={"force": False})

    assert response.status_code == 200
    assert response.json()["sent_count"] == 1
    assert calls == [
        (
            "update_variation_stock",
            "/wp-json/wc/v3/products/704/variations/705",
            {"manage_stock": True, "stock_quantity": 6.0, "stock_status": "instock"},
        )
    ]
    item = client.get("/api/items", params={"sku": "ORDER-MAPPED-STOCK"}).json()["items"][0]
    assert item["wooProductId"] == 704
    assert item["wooVariationId"] == 705
    assert item["wooStockQuantitySnapshot"] == 6
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
            "adjustment_type": "manual_increase",
            "reason": "Physical count correction",
            "created_by": "pytest",
            "lines": [{"item_id": item["id"], "inventory_item_location_id": location["id"], "quantity_change": 2}],
        },
    )

    assert response.status_code == 201, response.text
    assert calls == [("update_product_stock", "/wp-json/wc/v3/products/703", 8.0)]
