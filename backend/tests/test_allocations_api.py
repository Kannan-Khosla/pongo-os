import csv
from io import StringIO

from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def synced_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="ORDER-SKU", barcode="ORDER-BAR"):
    item = seed_item(client, sku=sku, Barcode=barcode, wooProductId=101, **{"In Stock": item_stock, "Allocated": item_allocated})
    order_payload = woo_order(
        line_items=[
            {
                **woo_order()["line_items"][0],
                "sku": sku,
                "quantity": quantity,
                "meta_data": [{"key": "barcode", "value": barcode}],
            }
        ]
    )
    patch_woo_order_client(monkeypatch, [order_payload])
    commit = client.post("/api/integrations/woocommerce/orders/commit", json={})
    assert commit.status_code == 200, commit.text
    order = client.get("/api/orders/open").json()["orders"][0]
    detail = client.get(f"/api/orders/{order['id']}").json()
    return item, detail, detail["lines"][0]


def test_allocation_preview_valid_order_does_not_write(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)

    response = client.post("/api/allocations/preview", json={"order_ids": [order["id"]], "allow_partial": True})

    assert response.status_code == 200
    body = response.json()
    assert body["total_orders"] == 1
    assert body["total_lines"] == 1
    assert body["allocatable_lines"] == 1
    assert body["total_quantity_to_allocate"] == 2
    preview_line = body["preview_orders"][0]["lines"][0]
    assert preview_line["remaining_to_allocate"] == 2
    assert preview_line["recommended_allocate_quantity"] == 2
    assert preview_line["allocation_status"] == "allocated"
    after_item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    after_order = client.get(f"/api/orders/{order['id']}").json()
    assert after_item["In Stock"] == 6
    assert after_item["Allocated"] == 1
    assert after_order["lines"][0]["quantity_allocated"] == line["quantity_allocated"] == 0
    assert client.get("/api/allocations").json()["total"] == 0


def test_allocation_preview_partial_zero_sellable_and_already_allocated(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=2, item_allocated=1, quantity=3)

    partial = client.post("/api/allocations/preview", json={"order_ids": [order["id"]], "allow_partial": True}).json()
    assert partial["partial_lines"] == 1
    assert partial["preview_orders"][0]["lines"][0]["recommended_allocate_quantity"] == 1
    assert partial["preview_orders"][0]["lines"][0]["shortage_quantity"] == 2

    client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    zero_sellable = client.post("/api/allocations/preview", json={"order_ids": [order["id"]], "allow_partial": True}).json()
    assert zero_sellable["skipped_lines"] == 1
    assert zero_sellable["preview_orders"][0]["lines"][0]["allocation_status"] in {"unavailable", "skipped"}


def test_allocation_preview_skips_unmatched_and_conflict_lines(client, monkeypatch):
    patch_woo_order_client(monkeypatch, [woo_order(line_items=[{**woo_order()["line_items"][0], "sku": "MISSING", "meta_data": []}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    unmatched_order = client.get("/api/orders/open").json()["orders"][0]
    unmatched = client.post("/api/allocations/preview", json={"order_ids": [unmatched_order["id"]], "allow_partial": True}).json()
    assert unmatched["skipped_lines"] == 1

    seed_item(client, sku="ORDER-SKU", Barcode="SKU-BAR")
    seed_item(client, sku="OTHER-SKU", Barcode="ORDER-BAR")
    patch_woo_order_client(monkeypatch, [woo_order(id=502, number="1002")])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    conflict_order = [order for order in client.get("/api/orders/open").json()["orders"] if order["woo_order_number"] == "1002"][0]
    conflict = client.post("/api/allocations/preview", json={"order_ids": [conflict_order["id"]], "allow_partial": True}).json()
    assert conflict["conflict_lines"] == 1


def test_allocation_commit_creates_records_updates_allocated_and_audit_only(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)

    response = client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True, "created_by": "pytest", "notes": "Allocate order"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "posted"
    assert body["allocation_id"]
    assert body["allocated_lines"] == 1
    assert body["total_quantity_allocated"] == 2
    assert body["created_audit_events"] == 1
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 3
    assert item["Sellable"] == 3
    order_after = client.get(f"/api/orders/{order['id']}").json()
    assert order_after["local_status"] == "allocated"
    assert order_after["lines"][0]["quantity_allocated"] == 2
    assert order_after["lines"][0]["quantity_picked"] == 0
    assert order_after["lines"][0]["remaining_to_allocate"] == 0
    assert order_after["lines"][0]["shortage_quantity"] == 0
    assert order_after["lines"][0]["local_sellable"] == 3
    assert client.get("/api/stock-movements").json()["total"] == 0
    assert line["woo_product_id"] == order_after["lines"][0]["woo_product_id"]


def test_allocation_commit_partial_updates_order_status(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=2, item_allocated=1, quantity=3)

    response = client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True})

    assert response.json()["partial_lines"] == 1
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 2
    assert item["Allocated"] == 2
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["local_status"] == "partially_allocated"
    assert detail["lines"][0]["quantity_allocated"] == 1
    assert detail["lines"][0]["remaining_to_allocate"] == 2


def test_allocation_commit_rejects_overallocate_and_is_atomic(client, monkeypatch):
    _, order, line = synced_order(client, monkeypatch, item_stock=5, item_allocated=0, quantity=2)

    response = client.post("/api/allocations/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_allocate": 99}], "allow_partial": True})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert item["Allocated"] == 0
    assert item["In Stock"] == 5
    assert detail["lines"][0]["quantity_allocated"] == 0
    assert client.get("/api/allocations").json()["total"] == 0


def test_allocation_commit_requires_full_allocation_when_partial_not_allowed(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=1, item_allocated=0, quantity=2)

    response = client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": False})

    assert response.json()["status"] == "rejected"
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["Allocated"] == 0


def test_allocation_list_detail_and_export(client, monkeypatch):
    _, order, _ = synced_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2)
    commit = client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True, "created_by": "pytest"})
    allocation_id = commit.json()["allocation_id"]

    listing = client.get("/api/allocations")
    detail = client.get(f"/api/allocations/{allocation_id}")
    exported = client.get(f"/api/allocations/{allocation_id}/export")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert len(detail.json()["lines"]) == 1
    assert detail.json()["audit_event_ids"]
    assert exported.status_code == 200
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert rows[0]["Allocation Number"] == commit.json()["allocation_number"]
    assert rows[0]["Quantity Allocated"] == "2.0"
