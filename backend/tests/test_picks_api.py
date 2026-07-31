import csv
from io import StringIO
from uuid import uuid4

from app.core.config import get_settings
from tests.test_allocations_api import synced_order
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="PICK-SKU", barcode="PICK-BAR"):
    _, order, _ = synced_order(client, monkeypatch, item_stock=item_stock, item_allocated=item_allocated, quantity=quantity, sku=sku, barcode=barcode)
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["allocation_status"] in {"allocated", "auto_allocated"}
    return detail, detail["lines"][0]


def commit_payload(**values):
    return {"idempotency_key": f"pick-{uuid4()}", **values}


def unpick_payload(**values):
    return {"idempotency_key": f"unpick-{uuid4()}", **values}


def test_pick_preview_valid_allocated_order_does_not_write(client, monkeypatch):
    order, line = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)
    before_item = client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]

    pick_list_order = client.get("/api/orders/pick").json()["orders"][0]
    assert pick_list_order["order_source"] == "WooCommerce"
    assert pick_list_order["skus"] == ["PICK-SKU"]
    assert pick_list_order["total_quantity_ordered"] == 2
    assert pick_list_order["total_quantity_allocated"] == 2
    assert pick_list_order["total_quantity_picked"] == 0

    response = client.post("/api/picks/preview", json={"order_ids": [order["id"]], "allow_partial": True})

    assert response.status_code == 200
    body = response.json()
    assert body["total_orders"] == 1
    assert body["total_lines"] == 1
    assert body["pickable_lines"] == 1
    assert body["total_quantity_to_pick"] == 2
    preview_line = body["preview_orders"][0]["lines"][0]
    assert preview_line["quantity_allocated"] == 2
    assert preview_line["quantity_previously_picked"] == 0
    assert preview_line["remaining_to_pick"] == 2
    assert preview_line["recommended_pick_quantity"] == 2
    assert preview_line["pick_status"] == "picked"
    after_item = client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]
    after_order = client.get(f"/api/orders/{order['id']}").json()
    assert after_item["In Stock"] == before_item["In Stock"] == 6
    assert after_item["Allocated"] == before_item["Allocated"] == 3
    assert after_item["Sellable"] == before_item["Sellable"] == 3
    assert after_order["lines"][0]["quantity_picked"] == line["quantity_picked"] == 0
    assert client.get("/api/picks").json()["total"] == 0


def test_pick_preview_skips_unallocated_unmatched_conflict_and_fully_picked(client, monkeypatch):
    _, unallocated_order, _ = synced_order(client, monkeypatch, item_stock=1, item_allocated=0, quantity=2, sku="UNALLOC-SKU", barcode="UNALLOC-BAR")
    unallocated = client.post("/api/picks/preview", json={"order_ids": [unallocated_order["id"]], "allow_partial": True}).json()
    assert unallocated["skipped_lines"] == 1
    assert unallocated["errors"]

    patch_woo_order_client(monkeypatch, [woo_order(id=601, number="2001", line_items=[{**woo_order()["line_items"][0], "sku": "MISSING", "meta_data": []}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    unmatched_order = [order for order in client.get("/api/orders/open").json()["orders"] if order["woo_order_number"] == "2001"][0]
    unmatched = client.post("/api/picks/preview", json={"order_ids": [unmatched_order["id"]], "allow_partial": True}).json()
    assert unmatched["skipped_lines"] == 1

    seed_item(client, sku="CONFLICT-SKU", Barcode="SKU-BAR")
    seed_item(client, sku="OTHER-CONFLICT-SKU", Barcode="ORDER-BAR")
    patch_woo_order_client(monkeypatch, [woo_order(id=602, number="2002", line_items=[{**woo_order()["line_items"][0], "sku": "CONFLICT-SKU"}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    conflict_order = [order for order in client.get("/api/orders/open").json()["orders"] if order["woo_order_number"] == "2002"][0]
    conflict = client.post("/api/picks/preview", json={"order_ids": [conflict_order["id"]], "allow_partial": True}).json()
    assert conflict["conflict_lines"] == 1

def test_pick_commit_creates_records_updates_picked_and_reduces_stock(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)
    before_item = client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]

    response = client.post("/api/picks/commit", json=commit_payload(order_ids=[order["id"]], allow_partial=True, created_by="pytest", notes="Pick order"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "posted"
    assert body["pick_id"]
    assert body["picked_lines"] == 1
    assert body["total_quantity_picked"] == 2
    assert body["created_stock_movements"] == 1
    assert body["created_audit_events"] == 1
    item = client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]
    assert item["In Stock"] == before_item["In Stock"] - 2 == 4
    assert item["Allocated"] == before_item["Allocated"] - 2 == 1
    assert item["Sellable"] == before_item["Sellable"] == 3
    order_after = client.get(f"/api/orders/{order['id']}").json()
    assert order_after["local_status"] == "picked"
    assert order_after["lines"][0]["quantity_allocated"] == 2
    assert order_after["lines"][0]["quantity_picked"] == 2
    assert order_after["lines"][0]["quantity_stock_reduced"] == 2
    assert order_after["lines"][0]["remaining_to_pick"] == 0
    assert order_after["lines"][0]["picking_status"] == "picked"
    assert order_after["shows_in_pick_orders"] is False
    assert order["id"] not in {row["id"] for row in client.get("/api/orders/pick").json()["orders"]}
    movements = client.get("/api/stock-movements", params={"movement_type": "pick_stock_reduction"}).json()
    assert movements["total"] == 1
    assert movements["movements"][0]["quantity_delta"] == -2


def test_pick_commit_idempotency_replays_and_rejects_changed_payload(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)
    payload = {
        "idempotency_key": "pick-commit-1",
        "order_ids": [order["id"]],
        "allow_partial": True,
        "created_by": "pytest",
    }

    first = client.post("/api/picks/commit", json=payload)
    replay = client.post("/api/picks/commit", json=payload)
    changed = client.post("/api/picks/commit", json={**payload, "notes": "different request"})

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert changed.status_code == 409
    assert client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]["In Stock"] == 4
    assert client.get("/api/stock-movements", params={"movement_type": "pick_stock_reduction"}).json()["total"] == 1


def test_pick_commit_requires_a_nonblank_idempotency_key(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch)

    missing = client.post("/api/picks/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    blank = client.post("/api/picks/commit", json={"idempotency_key": "   ", "order_ids": [order["id"]], "allow_partial": True})

    assert missing.status_code == 422
    assert blank.status_code == 409
    assert client.get("/api/stock-movements", params={"movement_type": "pick_stock_reduction"}).json()["total"] == 0


def test_pick_waits_until_completion_to_write_reduced_stock_to_woo(client, monkeypatch):
    settings = get_settings().model_copy(
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
            "woocommerce_allowed_host": "staging32.pongo.ca",
        }
    )
    monkeypatch.setattr("app.api.routes.orders.get_settings", lambda: settings)
    calls = []

    def fake_write(self, operation_type, method, path, payload):
        calls.append((operation_type, path, payload["stock_quantity"]))
        return {"stock_quantity": payload["stock_quantity"]}

    monkeypatch.setattr("app.api.routes.orders.WooCommerceClient.guarded_write", fake_write)
    order, _ = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="PICK-WRITEBACK", barcode="PICK-WRITEBACK-BAR")

    response = client.post("/api/picks/commit", json=commit_payload(order_ids=[order["id"]], allow_partial=True, created_by="pytest"))

    assert response.status_code == 200
    assert response.json()["status"] == "posted"
    assert calls == []

    completed = client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={"completion_mode": "complete", "queue_woo_status_update": False},
    )

    assert completed.status_code == 200
    assert calls == [("update_product_stock", "/wp-json/wc/v3/products/101", 4.0)]


def test_pick_preview_skips_fully_picked_line(client, monkeypatch):
    picked_order, _ = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=1, sku="FULL-PICK-SKU", barcode="FULL-PICK-BAR")
    client.post("/api/picks/commit", json=commit_payload(order_ids=[picked_order["id"]], allow_partial=True))

    fully_picked = client.post("/api/picks/preview", json={"order_ids": [picked_order["id"]], "allow_partial": True}).json()

    assert fully_picked["skipped_lines"] == 1
    assert fully_picked["preview_orders"][0]["lines"][0]["remaining_to_pick"] == 0


def test_pick_commit_partial_updates_order_status(client, monkeypatch):
    order, line = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)

    response = client.post("/api/picks/commit", json=commit_payload(lines=[{"order_line_id": line["id"], "quantity_to_pick": 1}], allow_partial=True))

    assert response.json()["status"] == "posted"
    assert response.json()["partial_lines"] == 1
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["local_status"] == "partially_picked"
    assert detail["lines"][0]["quantity_allocated"] == 2
    assert detail["lines"][0]["quantity_picked"] == 1
    assert detail["lines"][0]["quantity_stock_reduced"] == 1
    assert detail["lines"][0]["remaining_to_pick"] == 1


def test_bulk_unpick_restores_original_location_stock_and_allocation_with_audit_movement(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="UNPICK-SKU", barcode="UNPICK-BAR")
    before = client.get("/api/items", params={"sku": "UNPICK-SKU"}).json()["items"][0]
    pick = client.post("/api/picks/commit", json=commit_payload(order_ids=[order["id"]], allow_partial=True)).json()
    assert pick["status"] == "posted"

    response = client.post("/api/orders/bulk/unpick", json=unpick_payload(order_ids=[order["id"]], created_by="pytest", reason="Packing correction"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["succeeded_count"] == 1
    assert body["total_quantity_restored"] == 2
    assert body["created_stock_movements"] == 1
    assert body["created_audit_events"] == 1
    item = client.get("/api/items", params={"sku": "UNPICK-SKU"}).json()["items"][0]
    assert item["In Stock"] == before["In Stock"]
    assert item["Allocated"] == before["Allocated"]
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["lines"][0]["quantity_picked"] == 0
    assert detail["lines"][0]["quantity_stock_reduced"] == 0
    assert detail["pick_status"] == "ready_to_pick"
    pick_detail = client.get(f"/api/picks/{pick['pick_id']}").json()
    assert pick_detail["status"] == "reversed"
    assert pick_detail["lines"][0]["status"] == "reversed"
    movements = client.get("/api/stock-movements", params={"movement_type": "unpick_stock_restoration"}).json()
    assert movements["total"] == 1
    assert movements["movements"][0]["quantity_delta"] == 2

    duplicate = client.post("/api/orders/bulk/unpick", json=unpick_payload(order_ids=[order["id"]]))
    assert duplicate.json()["status"] == "rejected"
    assert client.get("/api/items", params={"sku": "UNPICK-SKU"}).json()["items"][0]["In Stock"] == before["In Stock"]

    repick = client.post("/api/picks/commit", json=commit_payload(order_ids=[order["id"]], allow_partial=False))
    assert repick.status_code == 200
    assert repick.json()["status"] == "posted"
    repicked_detail = client.get(f"/api/orders/{order['id']}").json()
    assert repicked_detail["lines"][0]["quantity_picked"] == 2
    assert repicked_detail["lines"][0]["quantity_stock_reduced"] == 2


def test_bulk_unpick_idempotency_replays_and_rejects_changed_payload(client, monkeypatch):
    order, _ = allocated_order(
        client,
        monkeypatch,
        item_stock=6,
        item_allocated=0,
        quantity=2,
        sku="UNPICK-IDEMP",
        barcode="UNPICK-IDEMP-BAR",
    )
    client.post("/api/picks/commit", json=commit_payload(order_ids=[order["id"]], allow_partial=False))
    payload = {
        "idempotency_key": "unpick-1",
        "order_ids": [order["id"]],
        "created_by": "pytest",
        "reason": "Retry-safe correction",
    }

    first = client.post("/api/orders/bulk/unpick", json=payload)
    replay = client.post("/api/orders/bulk/unpick", json=payload)
    changed = client.post("/api/orders/bulk/unpick", json={**payload, "reason": "Changed correction"})

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert changed.status_code == 409
    assert client.get(
        "/api/stock-movements",
        params={"movement_type": "unpick_stock_restoration"},
    ).json()["total"] == 1


def test_pick_commit_rejects_overpick_and_is_atomic(client, monkeypatch):
    order, line = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)
    before_item = client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]

    response = client.post("/api/picks/commit", json=commit_payload(lines=[{"order_line_id": line["id"], "quantity_to_pick": 99}], allow_partial=True))

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    item = client.get("/api/items", params={"sku": "PICK-SKU"}).json()["items"][0]
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert item["In Stock"] == before_item["In Stock"]
    assert item["Allocated"] == before_item["Allocated"]
    assert item["Sellable"] == before_item["Sellable"]
    assert detail["lines"][0]["quantity_picked"] == 0
    assert client.get("/api/picks").json()["total"] == 0


def test_pick_commit_requires_full_pick_when_partial_not_allowed(client, monkeypatch):
    _, line = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)

    response = client.post("/api/picks/commit", json=commit_payload(lines=[{"order_line_id": line["id"], "quantity_to_pick": 1}], allow_partial=False))

    assert response.json()["status"] == "rejected"
    assert client.get("/api/picks").json()["total"] == 0


def test_pick_list_detail_export_and_open_orders_reflect_picked(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)
    commit = client.post("/api/picks/commit", json=commit_payload(order_ids=[order["id"]], allow_partial=True, created_by="pytest"))
    pick_id = commit.json()["pick_id"]

    listing = client.get("/api/picks")
    detail = client.get(f"/api/picks/{pick_id}")
    exported = client.get(f"/api/picks/{pick_id}/export")
    open_orders = client.get("/api/orders/open")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert len(detail.json()["lines"]) == 1
    assert detail.json()["audit_event_ids"]
    assert detail.json()["lines"][0]["stock_movement_id"]
    assert exported.status_code == 200
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert exported.text.splitlines()[0] == "Pick Number,Status,Created At,Posted At,Woo Order Number,Order ID,SKU,Barcode,Description,Warehouse,Inventory Location,Quantity Ordered,Quantity Allocated,Previously Picked,Quantity Picked,Picked After,Remaining To Pick,Line Status,Notes"
    assert rows[0]["Pick Number"] == commit.json()["pick_number"]
    assert rows[0]["Quantity Picked"] == "2.0"
    assert open_orders.status_code == 200
    picked_orders = [row for row in open_orders.json()["orders"] if row["id"] == order["id"]]
    assert picked_orders
    assert picked_orders[0]["local_status"] == "picked"


def test_pick_scan_commit_is_idempotent_with_key(client, monkeypatch):
    order, line = allocated_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="IDEMP-PICK-SKU", barcode="IDEMP-PICK-BAR")

    first = client.post(f"/api/picks/orders/{order['id']}/scan/commit", json={"sku_or_barcode": line["sku"], "quantity": 2, "idempotency_key": "scan-1"})
    second = client.post(f"/api/picks/orders/{order['id']}/scan/commit", json={"sku_or_barcode": line["sku"], "quantity": 2, "idempotency_key": "scan-1"})

    assert first.json()["status"] == "posted"
    assert second.json() == first.json()
    item = client.get("/api/items", params={"sku": "IDEMP-PICK-SKU"}).json()["items"][0]
    assert item["In Stock"] == 4
    assert client.get("/api/stock-movements", params={"movement_type": "pick_stock_reduction"}).json()["total"] == 1

    collision = client.post(
        f"/api/picks/orders/{order['id']}/scan/commit",
        json={"sku_or_barcode": line["sku"], "quantity": 1, "idempotency_key": "scan-1"},
    )
    assert collision.status_code == 409
