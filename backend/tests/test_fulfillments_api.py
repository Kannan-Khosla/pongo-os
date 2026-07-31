import csv
from io import StringIO

from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def picked_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="FULFILL-SKU", barcode="FULFILL-BAR", woo_id=701, product_id=301):
    seed_item(client, sku=sku, Barcode=barcode, wooProductId=product_id, **{"In Stock": item_stock, "Allocated": item_allocated})
    order_payload = woo_order(
        id=woo_id,
        number=str(woo_id),
        line_items=[
            {
                **woo_order()["line_items"][0],
                "id": woo_id + 1000,
                "product_id": product_id,
                "sku": sku,
                "quantity": quantity,
                "meta_data": [{"key": "barcode", "value": barcode}],
            }
        ],
    )
    patch_woo_order_client(monkeypatch, [order_payload])
    sync = client.post("/api/integrations/woocommerce/orders/commit", json={})
    assert sync.status_code == 200, sync.text
    order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == woo_id][0]
    pick = client.post("/api/picks/commit", json={"idempotency_key": f"fulfillment-pick-{order['id']}", "order_ids": [order["id"]], "allow_partial": True, "created_by": "pytest"})
    assert pick.status_code == 200, pick.text
    assert pick.json()["status"] == "posted"
    detail = client.get(f"/api/orders/{order['id']}").json()
    return detail, detail["lines"][0]


def test_fulfillment_preview_valid_picked_order_does_not_write(client, monkeypatch):
    order, line = picked_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]

    response = client.post("/api/fulfillments/preview", json={"order_ids": [order["id"]], "allow_partial": True})

    assert response.status_code == 200
    body = response.json()
    assert body["total_orders"] == 1
    assert body["total_lines"] == 1
    assert body["fulfillable_lines"] == 1
    assert body["total_quantity_to_fulfill"] == 2
    preview_line = body["preview_orders"][0]["lines"][0]
    assert preview_line["quantity_picked"] == 2
    assert preview_line["quantity_previously_fulfilled"] == 0
    assert preview_line["remaining_to_fulfill"] == 2
    assert preview_line["recommended_fulfill_quantity"] == 2
    assert preview_line["fulfillment_status"] == "fulfilled"
    after_item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]
    after_order = client.get(f"/api/orders/{order['id']}").json()
    assert after_item["In Stock"] == before_item["In Stock"] == 4
    assert after_item["Allocated"] == before_item["Allocated"] == 1
    assert after_order["lines"][0]["quantity_fulfilled"] == line["quantity_fulfilled"] == 0
    assert client.get("/api/stock-movements", params={"movement_type": "fulfill_order"}).json()["total"] == 0
    assert client.get("/api/fulfillments").json()["total"] == 0


def test_fulfillment_preview_skips_unpicked_unmatched_conflict_and_fully_fulfilled(client, monkeypatch):
    seed_item(client, sku="UNPICKED-SKU", Barcode="UNPICKED-BAR", wooProductId=302, **{"In Stock": 6, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order(id=702, number="702", line_items=[{**woo_order()["line_items"][0], "id": 1702, "product_id": 302, "sku": "UNPICKED-SKU", "meta_data": [{"key": "barcode", "value": "UNPICKED-BAR"}]}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    unpicked_order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == 702][0]
    unpicked = client.post("/api/fulfillments/preview", json={"order_ids": [unpicked_order["id"]], "allow_partial": True}).json()
    assert unpicked["skipped_lines"] == 1
    assert unpicked["errors"]

    patch_woo_order_client(monkeypatch, [woo_order(id=703, number="703", line_items=[{**woo_order()["line_items"][0], "sku": "MISSING", "meta_data": []}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    unmatched_order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == 703][0]
    unmatched = client.post("/api/fulfillments/preview", json={"order_ids": [unmatched_order["id"]], "allow_partial": True}).json()
    assert unmatched["skipped_lines"] == 1

    seed_item(client, sku="CONFLICT-FULFILL-SKU", Barcode="SKU-BAR")
    seed_item(client, sku="OTHER-FULFILL-SKU", Barcode="ORDER-BAR")
    patch_woo_order_client(monkeypatch, [woo_order(id=704, number="704", line_items=[{**woo_order()["line_items"][0], "sku": "CONFLICT-FULFILL-SKU"}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    conflict_order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == 704][0]
    conflict = client.post("/api/fulfillments/preview", json={"order_ids": [conflict_order["id"]], "allow_partial": True}).json()
    assert conflict["conflict_lines"] == 1


def test_fulfillment_preview_skips_fully_fulfilled_line(client, monkeypatch):
    order, _ = picked_order(client, monkeypatch, quantity=1, sku="FULL-FULFILL-SKU", barcode="FULL-FULFILL-BAR", woo_id=705, product_id=305)
    client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True})

    fully_fulfilled = client.post("/api/fulfillments/preview", json={"order_ids": [order["id"]], "allow_partial": True}).json()

    assert fully_fulfilled["skipped_lines"] == 1
    assert fully_fulfilled["preview_orders"][0]["lines"][0]["remaining_to_fulfill"] == 0


def test_fulfillment_commit_creates_records_without_reducing_stock_again(client, monkeypatch):
    order, _ = picked_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]

    response = client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True, "created_by": "pytest", "notes": "Complete order"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "posted"
    assert body["fulfillment_id"]
    assert body["fulfilled_lines"] == 1
    assert body["total_quantity_fulfilled"] == 2
    assert body["created_stock_movements"] == 0
    assert body["created_audit_events"] == 1
    assert "Stock already reduced during picking." in body["warnings"]
    item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]
    assert item["In Stock"] == before_item["In Stock"] == 4
    assert item["Allocated"] == before_item["Allocated"] == 1
    assert item["Sellable"] == 3
    assert item["Under Par"] is True
    order_after = client.get(f"/api/orders/{order['id']}").json()
    assert order_after["local_status"] == "fulfilled"
    assert order_after["lines"][0]["quantity_allocated"] == 2
    assert order_after["lines"][0]["quantity_picked"] == 2
    assert order_after["lines"][0]["quantity_fulfilled"] == 2
    assert order_after["lines"][0]["remaining_to_fulfill"] == 0
    assert client.get("/api/stock-movements", params={"movement_type": "fulfill_order"}).json()["total"] == 0


def test_fulfillment_commit_partial_updates_order_status(client, monkeypatch):
    order, line = picked_order(client, monkeypatch)

    response = client.post("/api/fulfillments/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_fulfill": 1}], "allow_partial": True})

    assert response.json()["status"] == "posted"
    assert response.json()["partial_lines"] == 1
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["local_status"] == "partially_fulfilled"
    assert detail["lines"][0]["quantity_fulfilled"] == 1
    assert detail["lines"][0]["remaining_to_fulfill"] == 1
    item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]
    assert item["In Stock"] == 4
    assert item["Allocated"] == 1


def test_fulfillment_commit_rejects_overfulfill_and_is_atomic(client, monkeypatch):
    order, line = picked_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]

    response = client.post("/api/fulfillments/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_fulfill": 99}], "allow_partial": True})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    item = client.get("/api/items", params={"sku": "FULFILL-SKU"}).json()["items"][0]
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert item["In Stock"] == before_item["In Stock"]
    assert item["Allocated"] == before_item["Allocated"]
    assert detail["lines"][0]["quantity_fulfilled"] == 0
    assert client.get("/api/fulfillments").json()["total"] == 0
    assert client.get("/api/stock-movements", params={"movement_type": "fulfill_order"}).json()["total"] == 0


def test_fulfillment_commit_rejects_unpicked_order_without_reducing_stock(client, monkeypatch):
    seed_item(client, sku="UNPICKED-COMMIT-SKU", Barcode="UNPICKED-COMMIT-BAR", wooProductId=306, **{"In Stock": 2, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order(id=706, number="706", line_items=[{**woo_order()["line_items"][0], "id": 1706, "product_id": 306, "sku": "UNPICKED-COMMIT-SKU", "meta_data": [{"key": "barcode", "value": "UNPICKED-COMMIT-BAR"}]}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == 706][0]
    line = client.get(f"/api/orders/{order['id']}").json()["lines"][0]
    before = client.get("/api/items", params={"sku": "UNPICKED-COMMIT-SKU"}).json()["items"][0]

    response = client.post("/api/fulfillments/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_fulfill": 2}], "allow_partial": True})

    assert response.json()["status"] == "rejected"
    after = client.get("/api/items", params={"sku": "UNPICKED-COMMIT-SKU"}).json()["items"][0]
    assert after["In Stock"] == before["In Stock"]
    assert client.get("/api/fulfillments").json()["total"] == 0


def test_fulfillment_list_detail_export_and_open_orders_reflect_fulfilled(client, monkeypatch):
    order, _ = picked_order(client, monkeypatch)
    commit = client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True, "created_by": "pytest"})
    fulfillment_id = commit.json()["fulfillment_id"]

    listing = client.get("/api/fulfillments")
    detail = client.get(f"/api/fulfillments/{fulfillment_id}")
    exported = client.get(f"/api/fulfillments/{fulfillment_id}/export")
    open_orders = client.get("/api/orders/open")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert len(detail.json()["lines"]) == 1
    assert detail.json()["stock_movement_ids"] == []
    assert detail.json()["audit_event_ids"]
    assert exported.status_code == 200
    assert exported.text.splitlines()[0] == "Fulfillment Number,Status,Created At,Posted At,Woo Order Number,Order ID,SKU,Barcode,Description,Warehouse,Inventory Location,Quantity Ordered,Quantity Allocated,Quantity Picked,Previously Fulfilled,Quantity Fulfilled,Fulfilled After,Remaining To Fulfill,In Stock Before,Allocated Before,Sellable Before,In Stock After,Allocated After,Sellable After,Line Status,Notes"
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert rows[0]["Fulfillment Number"] == commit.json()["fulfillment_number"]
    assert rows[0]["Quantity Fulfilled"] == "2.0"
    fulfilled_orders = [row for row in open_orders.json()["orders"] if row["id"] == order["id"]]
    assert not fulfilled_orders
    completed = client.get("/api/orders/completed").json()["orders"]
    assert order["id"] in {row["id"] for row in completed}
