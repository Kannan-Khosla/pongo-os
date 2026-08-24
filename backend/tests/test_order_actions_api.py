from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.inventory import InventoryAuditEvent
from app.models.orders import Order, OrderItem
from app.schemas.woocommerce import WooStockSyncResponse
from app.services import order_actions
from app.services.order_actions import stock_sync_error
from app.services.woocommerce_client import WooCommerceClientError
from tests.test_allocations_api import synced_order
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


class ActionWooClient:
    def __init__(self, remote_order):
        self.remote_order = deepcopy(remote_order)
        self.calls = []
        self.fail_next_status = False
        self.accept_then_fail = False

    def get_order(self, order_id):
        assert order_id == self.remote_order["id"]
        return deepcopy(self.remote_order)

    def guarded_write(self, operation_type, method, path, payload):
        self.calls.append((operation_type, method, path, deepcopy(payload)))
        if operation_type == "update_order_status":
            if self.accept_then_fail:
                self.accept_then_fail = False
                self.remote_order["status"] = payload["status"]
                raise WooCommerceClientError("simulated timeout after acceptance")
            if self.fail_next_status:
                self.fail_next_status = False
                raise WooCommerceClientError("simulated timeout")
            self.remote_order["status"] = payload["status"]
            return deepcopy(self.remote_order)
        return {"id": int(path.rstrip("/").split("/")[-1]), **payload}


def action_settings():
    return get_settings().model_copy(
        update={
            "woocommerce_base_url": "https://staging32.pongo.ca/",
            "woocommerce_consumer_key": "ck_test",
            "woocommerce_consumer_secret": "cs_test",
            "woocommerce_environment": "staging",
            "woocommerce_read_only": False,
            "woocommerce_writeback_enabled": True,
            "woocommerce_writeback_dry_run": False,
            "woocommerce_staging_live_test_mode": True,
            "woocommerce_allow_stock_write": True,
            "woocommerce_allow_order_status_write": True,
            "woocommerce_allowed_host": "staging32.pongo.ca",
        }
    )


def patch_action_client(monkeypatch, remote_order):
    fake = ActionWooClient(remote_order)
    settings = action_settings()
    monkeypatch.setattr("app.api.routes.orders.effective_woocommerce_settings", lambda db, *args: settings)
    monkeypatch.setattr("app.api.routes.orders.WooCommerceClient", lambda _settings: fake)
    return fake


def test_remote_live_order_reconcile_returns_full_local_detail_and_replays(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    remote = woo_order()
    fake = patch_action_client(monkeypatch, remote)
    payload = {"idempotency_key": "reconcile-501"}

    first = client.post(
        "/api/orders/woocommerce/501/reconcile",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    second = client.post(
        "/api/orders/woocommerce/501/reconcile",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["order"]["lines"][0]["sku"] == "ORDER-SKU"
    assert first.json()["local_order_id"] == first.json()["order"]["id"]
    assert fake.calls == []


def test_cancel_live_processing_order_writes_woo_releases_allocations_and_audits_reason(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    payload = {
        "target_status": "cancelled",
        "completion_mode": "complete",
        "reason": "Customer requested cancellation",
        "idempotency_key": "cancel-501",
    }

    response = client.post(
        "/api/orders/woocommerce/501/status",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )
    replay = client.post(
        "/api/orders/woocommerce/501/status",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert response.status_code == replay.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["woo_sync_status"] == "sent"
    assert response.json()["released_quantity"] == 2
    assert replay.json()["status"] == "already_applied"
    assert [call[0] for call in fake.calls] == ["update_order_status", "update_product_stock"]
    assert fake.calls[-1][2] == "/wp-json/wc/v3/products/101"
    assert fake.calls[-1][3]["stock_quantity"] == 8
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["woo_status"] == "cancelled"
    assert detail["lines"][0]["quantity_allocated"] == 0
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        assert "Customer requested cancellation" in (stored.workflow_notes or "")
        assert "idempotency='cancel-501'" in (stored.workflow_notes or "")


def test_cancel_retry_same_key_restores_picked_stock_once_and_moves_failed_writeback_to_sent(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    picked = client.post(
        f"/api/picks/orders/{order['id']}/scan/commit",
        json={"sku_or_barcode": "ORDER-BAR", "quantity": 2, "idempotency_key": "pick-before-cancel-retry"},
    )
    assert picked.status_code == 200, picked.text
    fake = patch_action_client(monkeypatch, woo_order())
    fake.fail_next_status = True
    payload = {
        "target_status": "cancelled",
        "completion_mode": "complete",
        "reason": "Duplicate customer order",
        "idempotency_key": "cancel-retry-501",
    }

    failed = client.post("/api/orders/woocommerce/501/status", json=payload)
    sent = client.post("/api/orders/woocommerce/501/status", json=payload)

    assert failed.status_code == sent.status_code == 200
    assert failed.json()["woo_sync_status"] == "failed"
    assert failed.json()["local_status"] == "cancellation_pending"
    assert sent.json()["woo_sync_status"] == "sent"
    assert sent.json()["status"] == "cancelled"
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["lines"][0]["quantity_picked"] == 0
    assert detail["lines"][0]["quantity_stock_reduced"] == 0
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 8
    assert item["Allocated"] == 0
    movements = client.get(
        "/api/stock-movements",
        params={"movement_type": "unpick_stock_restoration"},
    ).json()
    assert movements["total"] == 1
    assert [call[0] for call in fake.calls] == [
        "update_order_status",
        "update_order_status",
        "update_product_stock",
    ]
    with Session(client.test_engine) as db:
        notes = db.get(Order, order["id"]).workflow_notes or ""
        assert "woo_writeback='failed'" in notes
        assert "woo_writeback='sent'" in notes


def test_cancel_rejects_fulfilled_order_without_writing_woocommerce(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    assert client.post(
        f"/api/picks/orders/{order['id']}/scan/commit",
        json={"sku_or_barcode": "ORDER-BAR", "quantity": 2, "idempotency_key": "pick-before-fulfill"},
    ).status_code == 200
    fulfilled = client.post(
        "/api/fulfillments/commit",
        json={"order_ids": [order["id"]], "allow_partial": True, "notes": "Already handed to customer"},
    )
    assert fulfilled.status_code == 200, fulfilled.text
    fake = patch_action_client(monkeypatch, woo_order())

    response = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "cancelled",
            "reason": "Too late to cancel",
            "idempotency_key": "cancel-fulfilled-501",
        },
    )

    assert response.status_code == 409
    assert "fulfilled" in response.json()["detail"]
    assert fake.calls == []


def test_retry_confirms_timeout_after_remote_acceptance_as_sent(client, monkeypatch):
    _, _, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    fake.accept_then_fail = True
    payload = {
        "target_status": "cancelled",
        "completion_mode": "complete",
        "reason": "Customer cancelled",
        "idempotency_key": "cancel-timeout-501",
    }

    timed_out = client.post("/api/orders/woocommerce/501/status", json=payload)
    confirmed = client.post("/api/orders/woocommerce/501/status", json=payload)

    assert timed_out.json()["woo_sync_status"] == "failed"
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "already_applied"
    assert confirmed.json()["woo_sync_status"] == "sent"


def test_local_completion_wins_and_blocks_later_cancellation_while_woo_is_still_processing(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    fake.fail_next_status = True
    completed = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "completed",
            "completion_mode": "complete_without_picking",
            "reason": "Warehouse confirmed completion",
            "idempotency_key": "complete-first-501",
        },
    )

    cancelled = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "cancelled",
            "completion_mode": "complete",
            "reason": "Conflicting cancellation",
            "idempotency_key": "cancel-second-501",
        },
    )

    assert completed.status_code == 200
    assert completed.json()["woo_sync_status"] == "failed"
    assert cancelled.status_code == 409
    assert "completion was already applied" in cancelled.json()["detail"]
    assert [call[3]["status"] for call in fake.calls] == ["completed"]
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        assert stored.completion_status == "completed_without_picking"


def test_cancellation_guard_wins_blocks_completion_and_survives_nonterminal_resync(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    fake.fail_next_status = True
    cancelled = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "cancelled",
            "completion_mode": "complete",
            "reason": "Customer requested cancellation",
            "idempotency_key": "cancel-first-501",
        },
    )

    for woo_status in ("processing", "on-hold", "pending"):
        patch_woo_order_client(monkeypatch, [woo_order(status=woo_status)])
        resync = client.post("/api/integrations/woocommerce/orders/commit", json={})
        assert resync.status_code == 200
        with Session(client.test_engine) as db:
            guarded = db.get(Order, order["id"])
            assert guarded.completion_status == "cancellation_pending"
            assert guarded.local_status == "cancellation_pending"
            assert guarded.items[0].quantity_allocated == 2

    completed = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "completed",
            "completion_mode": "complete_without_picking",
            "reason": "Conflicting completion",
            "idempotency_key": "complete-second-501",
        },
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["woo_sync_status"] == "failed"
    assert completed.status_code == 409
    assert "cancellation is already pending" in completed.json()["detail"]
    assert [call[3]["status"] for call in fake.calls] == ["cancelled"]


def test_terminal_woo_resync_resolves_cancellation_guard(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    fake.fail_next_status = True
    assert client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "cancelled",
            "completion_mode": "complete",
            "reason": "Customer requested cancellation",
            "idempotency_key": "cancel-terminal-sync-501",
        },
    ).status_code == 200

    patch_woo_order_client(monkeypatch, [woo_order(status="cancelled")])
    resync = client.post(
        "/api/integrations/woocommerce/orders/commit",
        json={"include_statuses": ["cancelled"]},
    )

    assert resync.status_code == 200
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        assert stored.completion_status == "cancelled"
        assert stored.local_status == "cancelled"


def test_completion_revalidates_after_a_pick_lands_between_initial_check_and_transition(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    real_complete = order_actions.complete_local_order_once

    def pick_before_locked_completion(db, order_id, completion_mode, reason, actor):
        stored_line = db.get(OrderItem, line["id"])
        stored_line.quantity_picked = 1
        stored_line.picked_qty = 1
        db.commit()
        return real_complete(db, order_id, completion_mode, reason, actor)

    monkeypatch.setattr(order_actions, "complete_local_order_once", pick_before_locked_completion)
    response = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "completed",
            "completion_mode": "complete_without_picking",
            "reason": "Attempted stale completion",
            "idempotency_key": "stale-complete-501",
        },
    )

    assert response.status_code == 400
    assert "picked, fulfilled, or stock-reduced" in response.json()["detail"]
    assert fake.calls == []
    assert client.get(f"/api/orders/{order['id']}").json()["completion_status"] not in {
        "completed",
        "completed_without_picking",
    }


def test_cancellation_revalidates_after_a_pick_lands_before_guard(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    fake = patch_action_client(monkeypatch, woo_order())
    real_guard = order_actions.begin_cancellation_guard

    def pick_before_locked_cancellation(db, order_id, **kwargs):
        stored_line = db.get(OrderItem, line["id"])
        stored_line.quantity_picked = 1
        stored_line.picked_qty = 1
        db.commit()
        return real_guard(db, order_id, **kwargs)

    monkeypatch.setattr(order_actions, "begin_cancellation_guard", pick_before_locked_cancellation)
    response = client.post(
        "/api/orders/woocommerce/501/status",
        json={
            "target_status": "cancelled",
            "completion_mode": "complete",
            "reason": "Attempted stale cancellation",
            "idempotency_key": "stale-cancel-501",
        },
    )

    assert response.status_code == 409
    assert "picked, fulfilled, or stock-reduced" in response.json()["detail"]
    assert fake.calls == []
    assert client.get(f"/api/orders/{order['id']}").json()["completion_status"] != "cancellation_pending"


def test_substitution_preserves_original_identity_uses_effective_scan_and_survives_resync(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    replacement = seed_item(
        client,
        sku="REPLACEMENT-SKU",
        Barcode="REPLACEMENT-BAR",
        wooProductId=202,
        Description="Replacement product",
        **{"Sales Price": 5, "In Stock": 8, "Allocated": 0},
    )
    payload = {
        "replacement_inventory_item_id": replacement["id"],
        "reason": "Original unavailable",
        "idempotency_key": "substitute-line-1",
    }

    response = client.post(
        f"/api/orders/{order['id']}/lines/{line['id']}/substitute",
        json=payload,
        headers={"Idempotency-Key": payload["idempotency_key"]},
    )

    assert response.status_code == 200, response.text
    detail = client.get(f"/api/orders/{order['id']}").json()
    effective = detail["lines"][0]
    assert effective["sku"] == "ORDER-SKU"
    assert effective["effective_sku"] == "REPLACEMENT-SKU"
    assert effective["substituted_from_sku"] == "ORDER-SKU"
    assert effective["invoice_unit_price"] == 5
    assert effective["invoice_line_total"] == 10
    assert effective["line_tax"] == 1
    assert detail["invoice_subtotal"] == 10
    assert detail["invoice_total"] == 16
    assert detail["discount_total"] == 0
    assert detail["shipping_total"] == 5
    assert detail["tax_total"] == 1
    original_scan = client.post(
        f"/api/picks/orders/{order['id']}/scan/preview",
        json={"sku_or_barcode": "ORDER-BAR", "quantity": 1},
    )
    replacement_scan = client.post(
        f"/api/picks/orders/{order['id']}/scan/preview",
        json={"sku_or_barcode": "REPLACEMENT-BAR", "quantity": 1},
    )
    assert original_scan.json()["status"] == "not_found"
    assert replacement_scan.json()["status"] == "valid"

    patch_woo_order_client(monkeypatch, [woo_order()])
    resync = client.post("/api/integrations/woocommerce/orders/commit", json={})
    assert resync.status_code == 200
    after = client.get(f"/api/orders/{order['id']}").json()["lines"][0]
    assert after["effective_sku"] == "REPLACEMENT-SKU"
    assert after["sync_status"] == "substituted"
    assert after["allocation_status"] != "exception"
    assert after["invoice_unit_price"] == 5
    assert client.get(f"/api/orders/{order['id']}").json()["invoice_total"] == 16

    changed = woo_order(line_items=[{**woo_order()["line_items"][0], "quantity": 3}])
    patch_woo_order_client(monkeypatch, [changed])
    changed_sync = client.post("/api/integrations/woocommerce/orders/commit", json={})
    assert changed_sync.status_code == 200
    reviewed = client.get(f"/api/orders/{order['id']}").json()["lines"][0]
    assert reviewed["effective_sku"] == "REPLACEMENT-SKU"
    assert reviewed["allocation_status"] == "exception"
    assert reviewed["sync_status"] == "needs_review"


def test_order_product_edits_allow_blank_reasons_sync_stock_and_survive_woo_resync(client, monkeypatch):
    _, order, original_line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    added_item = seed_item(
        client,
        sku="LOCAL-ADD-SKU",
        Barcode="LOCAL-ADD-BAR",
        wooProductId=202,
        Description="Locally added product",
        **{"Sales Price": 7.5, "In Stock": 8, "Allocated": 0},
    )
    fake = patch_action_client(monkeypatch, woo_order())

    added = client.post(
        f"/api/orders/{order['id']}/lines",
        json={
            "inventory_item_id": added_item["id"],
            "quantity": 2,
            "idempotency_key": "local-add-line",
        },
    )

    assert added.status_code == 200, added.text
    assert added.json()["woo_stock_sync_status"] == "sent"
    detail = client.get(f"/api/orders/{order['id']}").json()
    local_line = next(line for line in detail["lines"] if line["item_id"] == added_item["id"])
    assert local_line["woo_line_item_id"] is None
    assert local_line["quantity_ordered"] == 2
    assert local_line["quantity_allocated"] == 2
    assert local_line["invoice_unit_price"] == 7.5
    assert local_line["invoice_line_total"] == 15
    assert local_line["line_tax"] is None
    assert detail["invoice_subtotal"] == 39
    assert detail["invoice_total"] == 45
    assert detail["tax_total"] == 1
    assert any(path == "/wp-json/wc/v3/products/202" and payload["stock_quantity"] == 6 for _, _, path, payload in fake.calls)

    removed_original = client.post(
        f"/api/orders/{order['id']}/lines/{original_line['id']}/remove",
        json={"idempotency_key": "local-remove-woo-line"},
    )
    assert removed_original.status_code == 200, removed_original.text
    assert removed_original.json()["released_quantity"] == 2
    after_original_removal = client.get(f"/api/orders/{order['id']}").json()
    assert [line["id"] for line in after_original_removal["lines"]] == [local_line["id"]]
    assert after_original_removal["invoice_subtotal"] == 15
    assert after_original_removal["invoice_total"] == 21

    patch_woo_order_client(monkeypatch, [woo_order()])
    assert client.post("/api/integrations/woocommerce/orders/commit", json={}).status_code == 200
    after_resync = client.get(f"/api/orders/{order['id']}").json()["lines"]
    assert [line["id"] for line in after_resync] == [local_line["id"]]

    removed_local = client.post(
        f"/api/orders/{order['id']}/lines/{local_line['id']}/remove",
        json={"reason": "", "idempotency_key": "local-remove-added-line"},
    )
    assert removed_local.status_code == 200, removed_local.text
    assert client.get(f"/api/orders/{order['id']}").json()["lines"] == []
    assert any(path == "/wp-json/wc/v3/products/101" and payload["stock_quantity"] == 8 for _, _, path, payload in fake.calls)
    assert any(path == "/wp-json/wc/v3/products/202" and payload["stock_quantity"] == 8 for _, _, path, payload in fake.calls)
    with Session(client.test_engine) as db:
        assert db.get(OrderItem, original_line["id"]).sync_status == "local_removed"
        assert db.get(OrderItem, local_line["id"]).sync_status == "local_removed"


def test_substitution_reason_is_optional_and_syncs_both_products(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    replacement = seed_item(
        client,
        sku="OPTIONAL-REASON-REPLACEMENT",
        Barcode="OPTIONAL-REASON-BAR",
        wooProductId=202,
        **{"In Stock": 8, "Allocated": 0},
    )
    fake = patch_action_client(monkeypatch, woo_order())

    response = client.post(
        f"/api/orders/{order['id']}/lines/{line['id']}/substitute",
        json={
            "replacement_inventory_item_id": replacement["id"],
            "idempotency_key": "substitute-without-reason",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["woo_stock_sync_status"] == "sent"
    paths = [path for operation, _, path, _ in fake.calls if operation.startswith("update_")]
    assert "/wp-json/wc/v3/products/101" in paths
    assert "/wp-json/wc/v3/products/202" in paths
    assert client.get(f"/api/orders/{order['id']}").json()["lines"][0]["substitution_reason"] is None


def test_woo_product_identity_change_preserves_substitute_but_blocks_picking_for_review(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    replacement = seed_item(
        client,
        sku="IDENTITY-REPLACEMENT",
        Barcode="IDENTITY-REPLACEMENT-BAR",
        wooProductId=202,
        **{"In Stock": 8, "Allocated": 0},
    )
    seed_item(
        client,
        sku="REMOTE-CHANGED-SKU",
        Barcode="REMOTE-CHANGED-BAR",
        wooProductId=303,
        **{"In Stock": 8, "Allocated": 0},
    )
    assert client.post(
        f"/api/orders/{order['id']}/lines/{line['id']}/substitute",
        json={
            "replacement_inventory_item_id": replacement["id"],
            "reason": "Original unavailable",
            "idempotency_key": "substitute-before-woo-identity-change",
        },
    ).status_code == 200
    changed_line = {
        **woo_order()["line_items"][0],
        "product_id": 303,
        "sku": "REMOTE-CHANGED-SKU",
    }
    patch_woo_order_client(monkeypatch, [woo_order(line_items=[changed_line])])

    changed_sync = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert changed_sync.status_code == 200
    reviewed = client.get(f"/api/orders/{order['id']}").json()["lines"][0]
    assert reviewed["effective_sku"] == "IDENTITY-REPLACEMENT"
    assert reviewed["allocation_status"] == "exception"
    assert reviewed["sync_status"] == "needs_review"
    assert "product or variation" in reviewed["sync_error"]


def test_substituted_picked_completion_syncs_original_and_replacement_once(client, monkeypatch):
    original, order, line = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    replacement = seed_item(
        client,
        sku="COMPLETE-REPLACEMENT",
        Barcode="COMPLETE-REPLACEMENT-BAR",
        wooProductId=202,
        **{"In Stock": 8, "Allocated": 0},
    )
    substitution = {
        "replacement_inventory_item_id": replacement["id"],
        "reason": "Use replacement",
        "idempotency_key": "substitute-completion",
    }
    assert client.post(
        f"/api/orders/{order['id']}/lines/{line['id']}/substitute",
        json=substitution,
    ).status_code == 200
    picked = client.post(
        f"/api/picks/orders/{order['id']}/scan/commit",
        json={
            "sku_or_barcode": "COMPLETE-REPLACEMENT-BAR",
            "quantity": 2,
            "idempotency_key": "pick-replacement",
        },
    )
    assert picked.status_code == 200, picked.text
    fake = patch_action_client(monkeypatch, woo_order())
    completion = {
        "target_status": "completed",
        "completion_mode": "complete",
        "reason": "Driver completed the picked order",
        "idempotency_key": "complete-substituted-501",
    }

    response = client.post("/api/orders/woocommerce/501/status", json=completion)

    assert response.status_code == 200, response.text
    assert response.json()["woo_sync_status"] == "sent"
    stock_paths = [path for operation, _, path, _ in fake.calls if operation.startswith("update_") and operation != "update_order_status"]
    assert stock_paths.count("/wp-json/wc/v3/products/101") == 1
    assert stock_paths.count("/wp-json/wc/v3/products/202") == 1
    assert original["id"] != replacement["id"]
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        assert "Driver completed the picked order" in (stored.workflow_notes or "")


def test_prepare_completed_without_picking_for_recovery_is_idempotent_and_does_not_write_woo(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    completed = client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={
            "completion_mode": "complete_without_picking",
            "reason": "Legacy completion",
            "queue_woo_status_update": False,
        },
    )
    assert completed.status_code == 200
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        stored.woo_status = "completed"
        stored.status = "completed"
        db.commit()
    patch_action_client(monkeypatch, woo_order(status="completed"))
    payload = {"reason": "Warehouse still needs to pick it", "idempotency_key": "recover-501"}

    first = client.post(f"/api/orders/{order['id']}/prepare-picking", json=payload)
    second = client.post(f"/api/orders/{order['id']}/prepare-picking", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["status"] == "prepared"
    assert client.get(f"/api/orders/{order['id']}").json()["completion_status"] == "picking_recovery"


def test_prepare_recovery_fails_closed_when_live_woo_order_is_no_longer_completed(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    assert client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={
            "completion_mode": "complete_without_picking",
            "reason": "Legacy completion",
            "queue_woo_status_update": False,
        },
    ).status_code == 200
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        stored.woo_status = "completed"
        stored.status = "completed"
        db.commit()
    patch_action_client(monkeypatch, woo_order(status="cancelled"))

    response = client.post(
        f"/api/orders/{order['id']}/prepare-picking",
        json={"reason": "Try recovery", "idempotency_key": "recover-cancelled-501"},
    )

    assert response.status_code == 409
    assert "still be completed" in response.json()["detail"]
    assert client.get(f"/api/orders/{order['id']}").json()["completion_status"] == "completed_without_picking"


def test_external_cancellation_during_recovery_stops_picking_and_releases_allocations(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    assert client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={
            "completion_mode": "complete_without_picking",
            "reason": "Legacy completion",
            "queue_woo_status_update": False,
        },
    ).status_code == 200
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        stored.woo_status = "completed"
        stored.status = "completed"
        db.commit()
    patch_action_client(monkeypatch, woo_order(status="completed"))
    recovery_payload = {
        "reason": "Recover warehouse pick",
        "idempotency_key": "recover-before-cancel-501",
    }
    assert client.post(
        f"/api/orders/{order['id']}/prepare-picking",
        json=recovery_payload,
    ).status_code == 200

    patch_woo_order_client(monkeypatch, [woo_order(status="cancelled")])
    resync = client.post(
        "/api/integrations/woocommerce/orders/commit",
        json={"include_statuses": ["cancelled"]},
    )

    assert resync.status_code == 200
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["completion_status"] == "cancelled"
    assert detail["local_status"] == "cancelled"
    assert detail["lines"][0]["quantity_allocated"] == 0
    assert client.get(f"/api/orders/{order['id']}/workflow").json()["workflow"]["can_pick"] is False
    patch_action_client(monkeypatch, woo_order(status="cancelled"))
    stale_replay = client.post(
        f"/api/orders/{order['id']}/prepare-picking",
        json=recovery_payload,
    )
    assert stale_replay.status_code == 409
    assert "no longer active" in stale_replay.json()["detail"]


def test_recovery_completion_replay_does_not_duplicate_stock_audit_or_woo_status(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=8, item_allocated=0, quantity=2)
    assert client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={
            "completion_mode": "complete_without_picking",
            "reason": "Legacy completion",
            "queue_woo_status_update": False,
        },
    ).status_code == 200
    with Session(client.test_engine) as db:
        stored = db.get(Order, order["id"])
        stored.woo_status = "completed"
        stored.status = "completed"
        db.commit()
    fake = patch_action_client(monkeypatch, woo_order(status="completed"))
    assert client.post(
        f"/api/orders/{order['id']}/prepare-picking",
        json={"reason": "Recover warehouse pick", "idempotency_key": "recover-complete-501"},
    ).status_code == 200
    assert client.post(
        f"/api/picks/orders/{order['id']}/scan/commit",
        json={"sku_or_barcode": "ORDER-BAR", "quantity": 2, "idempotency_key": "recover-pick-501"},
    ).status_code == 200
    completion_payload = {
        "completion_mode": "complete_picked",
        "reason": "Recovery pick complete",
        "queue_woo_status_update": True,
    }

    first = client.post(f"/api/orders/{order['id']}/complete/commit", json=completion_payload)
    second = client.post(f"/api/orders/{order['id']}/complete/commit", json=completion_payload)

    assert first.status_code == second.status_code == 200
    assert first.json()["queue_woo_status_update"] is False
    assert second.json()["queue_woo_status_update"] is False
    assert [call[0] for call in fake.calls].count("update_order_status") == 0
    stock_calls = [call for call in fake.calls if call[0] != "update_order_status"]
    assert len(stock_calls) == 1
    with Session(client.test_engine) as db:
        completion_events = db.scalars(
            select(InventoryAuditEvent).where(
                InventoryAuditEvent.reference_id == order["id"],
                InventoryAuditEvent.event_type == "complete_picked_order",
            )
        ).all()
        assert len(completion_events) == 1


def test_stock_sync_error_rejects_disabled_partial_and_unmapped_results():
    base = {
        "mode": "live",
        "requested_count": 2,
        "candidate_count": 2,
        "sent_count": 0,
        "dry_run_count": 0,
        "failed_count": 0,
        "skipped_unmapped_count": 0,
        "unchanged_count": 0,
        "queue_ids": [],
        "errors": [],
        "failed_item_ids": [],
    }
    assert "not fully synchronized" in stock_sync_error(WooStockSyncResponse(status="disabled", **base))
    assert "not fully synchronized" in stock_sync_error(WooStockSyncResponse(status="partial", **base))
    unmapped = WooStockSyncResponse(
        status="sent",
        **{**base, "candidate_count": 1, "sent_count": 1, "skipped_unmapped_count": 1},
    )
    assert "not mapped" in stock_sync_error(unmapped)


def test_order_action_mutations_require_idempotency_key(client):
    assert client.post(
        "/api/orders/woocommerce/501/status",
        json={"target_status": "cancelled", "reason": "test", "completion_mode": "complete"},
    ).status_code == 422
    assert client.post(
        "/api/orders/1/lines/1/substitute",
        json={"replacement_inventory_item_id": 1, "reason": "test"},
    ).status_code == 422
    assert client.post("/api/orders/1/prepare-picking", json={"reason": "test"}).status_code == 422
