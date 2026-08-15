import base64
import hashlib
import hmac
import json
from types import SimpleNamespace

from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryItemLocation
from app.services import woocommerce_webhooks as webhook_service
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order

WEBHOOK_SECRET = "pongo-webhook-test-secret-that-is-long-enough"
WEBHOOK_SOURCE = "https://staging32.pongo.ca/"


def webhook_settings(**overrides):
    values = {
        "woocommerce_base_url": WEBHOOK_SOURCE,
        "woocommerce_consumer_key": "ck_placeholder",
        "woocommerce_consumer_secret": "cs_placeholder",
        "woocommerce_environment": "staging",
        "woocommerce_read_enabled": True,
        "woocommerce_read_only": True,
        "woocommerce_writeback_enabled": False,
        "woocommerce_writeback_dry_run": True,
        "woocommerce_staging_live_test_mode": False,
        "woocommerce_allow_stock_write": False,
        "woocommerce_allow_order_status_write": False,
        "woocommerce_allow_product_metadata_write": False,
        "woocommerce_allow_customer_write": False,
        "woocommerce_allow_coupon_write": False,
        "woocommerce_allow_refund_write": False,
        "woocommerce_allow_delete": False,
        "woocommerce_allowed_host": "staging32.pongo.ca",
        "woocommerce_timeout_seconds": 30,
        "woocommerce_page_size": 100,
        "woocommerce_order_sync_page_size": 100,
        "woocommerce_webhook_enabled": True,
        "woocommerce_webhook_secret": WEBHOOK_SECRET,
        "woocommerce_webhook_max_body_bytes": 1_048_576,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def patch_webhook_settings(monkeypatch, **overrides):
    settings = webhook_settings(**overrides)
    monkeypatch.setattr("app.api.routes.woocommerce.get_settings", lambda: settings)
    return settings


def signed_delivery(payload, *, secret=WEBHOOK_SECRET, topic="order.created", event="created", delivery_id="delivery-1", webhook_id="41", source=WEBHOOK_SOURCE):
    raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("ascii")
    headers = {
        "Content-Type": "application/json",
        "X-WC-Webhook-Source": source,
        "X-WC-Webhook-Topic": topic,
        "X-WC-Webhook-Resource": topic.split(".", 1)[0],
        "X-WC-Webhook-Event": event,
        "X-WC-Webhook-Signature": signature,
        "X-WC-Webhook-ID": webhook_id,
        "X-WC-Webhook-Delivery-ID": delivery_id,
    }
    return raw_body, headers


def post_delivery(client, payload, **header_overrides):
    raw_body, headers = signed_delivery(payload, **header_overrides)
    return client.post("/api/integrations/woocommerce/webhooks/orders", content=raw_body, headers=headers)


def test_unsigned_activation_ping_is_a_no_op(client, monkeypatch):
    patch_webhook_settings(monkeypatch)

    response = client.post(
        "/api/integrations/woocommerce/webhooks/orders",
        content=b"webhook_id=41",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert client.get("/api/orders/open").json()["total"] == 0
    assert client.get("/api/integrations/woocommerce/webhooks/events").json() == {
        "events": [],
        "latest_event_id": 0,
        "next_after_id": 0,
        "has_more": False,
    }


def test_valid_signed_order_created_imports_and_emits_staff_event(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 6, "Allocated": 1})

    response = post_delivery(client, woo_order(id=601, number="1601"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processed"
    assert body["created_order"] is True
    assert body["woo_order_id"] == 601
    assert body["local_order_id"]
    assert body["sync_run_id"]
    open_orders = client.get("/api/orders/open").json()
    assert open_orders["total"] == 1
    assert open_orders["orders"][0]["woo_order_number"] == "1601"
    assert open_orders["orders"][0]["local_status"] == "allocated"
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 3
    movements = client.get("/api/stock-movements").json()
    assert movements["total"] == 1
    assert movements["movements"][0]["movement_type"] == "opening_balance_import"
    events = client.get("/api/integrations/woocommerce/webhooks/events").json()
    assert events["latest_event_id"] == body["event_id"]
    assert events["events"][0]["woo_order_number"] == "1601"
    assert events["events"][0]["customer_name"] == "Avery Stone"
    caught_up = client.get("/api/integrations/woocommerce/webhooks/events", params={"after_id": body["event_id"]}).json()
    assert caught_up == {
        "events": [],
        "latest_event_id": body["event_id"],
        "next_after_id": body["event_id"],
        "has_more": False,
    }


def test_replayed_delivery_is_idempotent_for_order_allocation_and_notification(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 8, "Allocated": 0})
    payload = woo_order(id=602, number="1602")

    first = post_delivery(client, payload, delivery_id="same-delivery")
    second = post_delivery(client, payload, delivery_id="same-delivery")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["duplicate"] is True
    assert client.get("/api/orders/open").json()["total"] == 1
    detail = client.get(f"/api/orders/{first.json()['local_order_id']}").json()
    assert len(detail["lines"]) == 1
    assert detail["lines"][0]["quantity_allocated"] == 2
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["Allocated"] == 2
    assert len(client.get("/api/integrations/woocommerce/webhooks/events").json()["events"]) == 1


def test_delivery_id_collision_with_different_payload_hashes_is_not_deduplicated(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})

    first = post_delivery(client, woo_order(id=603, number="1603"), delivery_id="same-second")
    second = post_delivery(client, woo_order(id=604, number="1604"), delivery_id="same-second")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is False
    assert client.get("/api/orders/open").json()["total"] == 2
    assert len(client.get("/api/integrations/woocommerce/webhooks/events").json()["events"]) == 2


def test_event_feed_initialization_and_pagination_do_not_skip_deliveries(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 20, "Allocated": 0})
    for offset in range(3):
        response = post_delivery(
            client,
            woo_order(id=620 + offset, number=f"162{offset}"),
            delivery_id=f"page-delivery-{offset}",
        )
        assert response.status_code == 200

    initialized = client.get(
        "/api/integrations/woocommerce/webhooks/events",
        params={"initialize": True, "limit": 1},
    ).json()
    assert initialized["events"] == []
    assert initialized["next_after_id"] == initialized["latest_event_id"] == 3

    first_page = client.get("/api/integrations/woocommerce/webhooks/events", params={"after_id": 0, "limit": 1}).json()
    second_page = client.get(
        "/api/integrations/woocommerce/webhooks/events",
        params={"after_id": first_page["next_after_id"], "limit": 1},
    ).json()
    third_page = client.get(
        "/api/integrations/woocommerce/webhooks/events",
        params={"after_id": second_page["next_after_id"], "limit": 1},
    ).json()

    assert [first_page["events"][0]["woo_order_id"], second_page["events"][0]["woo_order_id"], third_page["events"][0]["woo_order_id"]] == [620, 621, 622]
    assert first_page["next_after_id"] == 1
    assert second_page["next_after_id"] == 2
    assert third_page["next_after_id"] == 3
    assert first_page["has_more"] is True
    assert second_page["has_more"] is True
    assert third_page["has_more"] is False


def test_stale_supported_delivery_cannot_regress_newer_poll_data(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    newer = woo_order(id=623, number="1623", total="35.00", date_modified_gmt="2026-07-07T13:00:00")
    patch_woo_order_client(monkeypatch, [newer])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={})
    assert committed.status_code == 200
    order_id = client.get("/api/orders/open").json()["orders"][0]["id"]

    stale = woo_order(id=623, number="1623", total="30.00", date_modified_gmt="2026-07-07T12:30:00")
    response = post_delivery(client, stale, delivery_id="stale-delivery")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    detail = client.get(f"/api/orders/{order_id}").json()
    assert detail["total"] == 35
    assert detail["date_modified"] == "2026-07-07T13:00:00"
    assert client.get("/api/integrations/woocommerce/webhooks/events").json()["events"] == []

    equal_timestamp = woo_order(id=623, number="1623", total="31.00", date_modified_gmt="2026-07-07T13:00:00")
    equal_response = post_delivery(
        client,
        equal_timestamp,
        topic="order.updated",
        event="updated",
        delivery_id="equal-timestamp-delivery",
    )

    assert equal_response.status_code == 200
    assert equal_response.json()["status"] == "ignored"
    assert client.get(f"/api/orders/{order_id}").json()["total"] == 35


def test_missing_or_invalid_signature_fails_closed_without_mutation(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    raw_body, headers = signed_delivery(woo_order(id=605))
    headers.pop("X-WC-Webhook-Signature")

    missing = client.post("/api/integrations/woocommerce/webhooks/orders", content=raw_body, headers=headers)
    headers["X-WC-Webhook-Signature"] = "not-a-valid-signature"
    invalid = client.post("/api/integrations/woocommerce/webhooks/orders", content=raw_body, headers=headers)

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert client.get("/api/orders/open").json()["total"] == 0
    assert client.get("/api/integrations/woocommerce/webhooks/events").json()["latest_event_id"] == 0
    assert WEBHOOK_SECRET not in missing.text + invalid.text


def test_wrong_source_and_mismatched_headers_are_rejected(client, monkeypatch):
    patch_webhook_settings(monkeypatch)

    wrong_source = post_delivery(client, woo_order(id=606), source="https://attacker.invalid/")
    mismatched = post_delivery(client, woo_order(id=607), topic="order.created", event="updated", delivery_id="delivery-2")

    assert wrong_source.status_code == 403
    assert mismatched.status_code == 400
    assert client.get("/api/orders/open").json()["total"] == 0


def test_signed_unsupported_topic_is_audited_and_ignored(client, monkeypatch):
    patch_webhook_settings(monkeypatch)

    response = post_delivery(client, woo_order(id=608), topic="order.deleted", event="deleted")

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["created_order"] is False
    assert client.get("/api/orders/open").json()["total"] == 0
    events = client.get("/api/integrations/woocommerce/webhooks/events").json()
    assert events["events"] == []
    assert events["latest_event_id"] == 0
    assert response.json()["event_id"] is None


def test_signed_order_updated_cancellation_releases_allocation_and_emits_event(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    item = seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 8, "Allocated": 0})
    created = post_delivery(client, woo_order(id=608, number="1608"), delivery_id="created-608")
    assert created.status_code == 200
    assert client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]["Allocated"] == 2

    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    location = db.scalar(
        select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item["id"])
    )
    location.active = False
    db.commit()
    db_override.close()

    cancelled_payload = woo_order(
        id=608,
        number="1608",
        status="cancelled",
        date_modified_gmt="2026-07-07T13:30:00",
    )
    response = post_delivery(
        client,
        cancelled_payload,
        topic="order.updated",
        event="updated",
        delivery_id="updated-608",
    )

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert response.json()["created_order"] is False
    assert client.get("/api/orders/open").json()["total"] == 0
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["Allocated"] == 0
    detail = client.get(f"/api/orders/{created.json()['local_order_id']}").json()
    assert detail["woo_status"] == "cancelled"
    assert detail["local_status"] == "cancelled"
    assert "released 2.000 unpicked units" in detail["workflow_notes"]
    events = client.get("/api/integrations/woocommerce/webhooks/events").json()["events"]
    assert response.json()["event_id"] is not None
    assert [row["event_type"] for row in events] == ["order_created"]


def test_cancellation_after_partial_pick_and_fulfillment_releases_remaining_allocation(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="PARTIAL-CANCEL", Barcode="PARTIAL-CANCEL-BAR", wooProductId=101, **{"In Stock": 8, "Allocated": 0})
    created = post_delivery(client, woo_order(id=618, number="1618"), delivery_id="created-618")
    order_id = created.json()["local_order_id"]
    line_id = client.get(f"/api/orders/{order_id}").json()["lines"][0]["id"]
    picked = client.post(
        "/api/picks/commit",
        json={"idempotency_key": "partial-cancel-pick", "lines": [{"order_line_id": line_id, "quantity_to_pick": 1}], "allow_partial": True},
    )
    fulfilled = client.post(
        "/api/fulfillments/commit",
        json={"lines": [{"order_line_id": line_id, "quantity_to_fulfill": 1}], "allow_partial": True},
    )
    assert picked.json()["status"] == "posted"
    assert fulfilled.json()["status"] == "posted"
    assert client.get("/api/items", params={"sku": "PARTIAL-CANCEL"}).json()["items"][0]["Allocated"] == 1

    response = post_delivery(
        client,
        woo_order(id=618, number="1618", status="cancelled", date_modified_gmt="2026-07-07T13:40:00"),
        topic="order.updated",
        event="updated",
        delivery_id="cancelled-618",
    )

    assert response.status_code == 200, response.text
    assert client.get("/api/items", params={"sku": "PARTIAL-CANCEL"}).json()["items"][0]["Allocated"] == 0
    detail = client.get(f"/api/orders/{order_id}").json()
    assert detail["local_status"] == "cancelled"
    assert detail["lines"][0]["quantity_picked"] == 1
    assert detail["lines"][0]["quantity_fulfilled"] == 1
    assert "released 1.000 unpicked units" in detail["workflow_notes"]


def test_signed_order_updated_safely_retires_removed_line_and_replay_is_idempotent(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 8, "Allocated": 0})
    seed_item(client, sku="SECOND-SKU", Barcode="SECOND-BAR", wooProductId=102, **{"In Stock": 5, "Allocated": 0})
    second_line = {
        **woo_order()["line_items"][0],
        "id": 9002,
        "product_id": 102,
        "sku": "SECOND-SKU",
        "name": "Second Item",
        "quantity": 1,
        "subtotal": "10.00",
        "total": "10.00",
        "meta_data": [{"key": "barcode", "value": "SECOND-BAR"}],
    }
    created_payload = woo_order(id=609, number="1609", line_items=[woo_order()["line_items"][0], second_line])
    created = post_delivery(client, created_payload, delivery_id="created-609")
    assert created.status_code == 200

    updated_payload = woo_order(
        id=609,
        number="1609",
        date_modified_gmt="2026-07-07T13:30:00",
        line_items=[woo_order()["line_items"][0]],
    )
    first = post_delivery(
        client,
        updated_payload,
        topic="order.updated",
        event="updated",
        delivery_id="updated-609",
    )
    replay = post_delivery(
        client,
        updated_payload,
        topic="order.updated",
        event="updated",
        delivery_id="updated-609",
    )

    assert first.status_code == 200
    assert first.json()["status"] == "processed"
    assert replay.status_code == 200
    assert replay.json()["status"] == "duplicate"
    detail = client.get(f"/api/orders/{created.json()['local_order_id']}").json()
    assert len(detail["lines"]) == 2
    retired = next(line for line in detail["lines"] if line["woo_line_item_id"] == 9002)
    assert retired["quantity_ordered"] == 0
    assert retired["quantity_allocated"] == 0
    assert retired["matched_status"] == "removed"
    assert retired["sync_status"] == "synced"
    assert "local history was retained" in retired["sync_error"]
    assert "retained local history" in detail["workflow_notes"]
    allocation_exceptions = client.get("/api/allocations/exceptions", params={"view": "items"}).json()
    assert allocation_exceptions["item_groups"] == []
    workflow = client.get(f"/api/orders/{created.json()['local_order_id']}/workflow").json()
    assert workflow["allocation_evaluation"]["unmatched_lines"] == []
    pick_order_ids = {row["id"] for row in client.get("/api/orders/pick").json()["orders"]}
    assert created.json()["local_order_id"] in pick_order_ids
    second_item = client.get("/api/items", params={"sku": "SECOND-SKU"}).json()["items"][0]
    assert second_item["Allocated"] == 0

    restored_payload = woo_order(
        id=609,
        number="1609",
        date_modified_gmt="2026-07-07T14:00:00",
        line_items=[woo_order()["line_items"][0], second_line],
    )
    restored = post_delivery(
        client,
        restored_payload,
        topic="order.updated",
        event="updated",
        delivery_id="restored-609",
    )

    assert restored.status_code == 200
    restored_detail = client.get(f"/api/orders/{created.json()['local_order_id']}").json()
    reactivated = next(line for line in restored_detail["lines"] if line["woo_line_item_id"] == 9002)
    assert reactivated["quantity_ordered"] == 1
    assert reactivated["quantity_allocated"] == 1
    assert reactivated["matched_status"] == "matched"
    assert reactivated["sync_status"] == "synced"
    events = client.get("/api/integrations/woocommerce/webhooks/events").json()["events"]
    assert first.json()["event_id"] is not None
    assert restored.json()["event_id"] is not None
    assert first.json()["event_id"] != restored.json()["event_id"]
    assert [row["event_type"] for row in events] == ["order_created"]


def test_failed_delivery_retry_gets_a_new_immutable_event_cursor(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 8, "Allocated": 0})
    payload = woo_order(id=624, number="1624")
    raw_body, headers = signed_delivery(payload, delivery_id="retry-delivery")
    real_commit = webhook_service.commit_remote_order_records
    attempts = {"count": 0}

    def flaky_commit(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary import failure")
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(webhook_service, "commit_remote_order_records", flaky_commit)

    first = client.post("/api/integrations/woocommerce/webhooks/orders", content=raw_body, headers=headers)
    checkpoint = client.get("/api/integrations/woocommerce/webhooks/events").json()
    retry = client.post("/api/integrations/woocommerce/webhooks/orders", content=raw_body, headers=headers)
    after_retry = client.get(
        "/api/integrations/woocommerce/webhooks/events",
        params={"after_id": checkpoint["next_after_id"]},
    ).json()

    assert first.status_code == 503
    assert checkpoint == {"events": [], "latest_event_id": 0, "next_after_id": 0, "has_more": False}
    assert retry.status_code == 200
    assert retry.json()["status"] == "processed"
    assert retry.json()["event_id"] == 1
    assert [event["woo_order_id"] for event in after_retry["events"]] == [624]
    assert after_retry["next_after_id"] == 1


def test_malformed_json_invalid_shape_and_oversized_body_are_rejected(client, monkeypatch):
    patch_webhook_settings(monkeypatch)
    malformed_body = b'{"id":'
    signature = base64.b64encode(hmac.new(WEBHOOK_SECRET.encode(), malformed_body, hashlib.sha256).digest()).decode()
    headers = signed_delivery(woo_order())[1]
    headers["X-WC-Webhook-Signature"] = signature
    malformed = client.post("/api/integrations/woocommerce/webhooks/orders", content=malformed_body, headers=headers)
    invalid_shape = post_delivery(client, {"id": 609, "status": "processing", "line_items": "not-a-list"}, delivery_id="delivery-3")
    patch_webhook_settings(monkeypatch, woocommerce_webhook_max_body_bytes=1024)
    oversized = post_delivery(client, woo_order(id=610, customer_note="x" * 2000), delivery_id="delivery-4")

    assert malformed.status_code == 400
    assert invalid_shape.status_code == 422
    assert oversized.status_code == 413
    assert client.get("/api/orders/open").json()["total"] == 0


def test_chunked_body_without_content_length_is_limited_while_streaming(client, monkeypatch):
    patch_webhook_settings(monkeypatch, woocommerce_webhook_max_body_bytes=1024)

    def oversized_chunks():
        yield b"{" + (b"x" * 700)
        yield b"x" * 700

    response = client.post(
        "/api/integrations/woocommerce/webhooks/orders",
        content=oversized_chunks(),
        headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
    )

    assert response.status_code == 413
    assert client.get("/api/integrations/woocommerce/webhooks/events").json()["latest_event_id"] == 0


def test_disabled_or_short_secret_receiver_fails_closed(client, monkeypatch):
    patch_webhook_settings(monkeypatch, woocommerce_webhook_enabled=False)
    disabled = post_delivery(client, woo_order(id=611))
    patch_webhook_settings(monkeypatch, woocommerce_webhook_secret="too-short")
    short_secret = post_delivery(client, woo_order(id=612), secret="too-short", delivery_id="delivery-2")

    assert disabled.status_code == 503
    assert short_secret.status_code == 503
    assert client.get("/api/orders/open").json()["total"] == 0


def test_status_exposes_webhook_booleans_but_never_secret(client, monkeypatch):
    patch_webhook_settings(monkeypatch)

    response = client.get("/api/integrations/woocommerce/status")

    assert response.status_code == 200
    body = response.json()
    assert body["webhook_enabled"] is True
    assert body["webhook_configured"] is True
    assert body["webhook_secret_present"] is True
    assert WEBHOOK_SECRET not in response.text
