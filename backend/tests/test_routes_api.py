import csv
from io import StringIO

from tests.test_fulfillments_api import picked_order
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def fulfilled_route_order(client, monkeypatch, sku="ROUTE-SKU", barcode="ROUTE-BAR", woo_id=901, product_id=501, partial=False):
    order, line = picked_order(client, monkeypatch, item_stock=8, item_allocated=1, quantity=2, sku=sku, barcode=barcode, woo_id=woo_id, product_id=product_id)
    if partial:
        commit = client.post("/api/fulfillments/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_fulfill": 1}], "allow_partial": True})
    else:
        commit = client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    assert commit.status_code == 200, commit.text
    assert commit.json()["status"] == "posted"
    detail = client.get(f"/api/orders/{order['id']}").json()
    return detail


def synced_unfulfilled_order(client, monkeypatch, status_step="open"):
    woo_id, product_id = {
        "open": (977, 777),
        "allocated": (978, 778),
        "picked": (979, 779),
    }[status_step]
    sku = f"{status_step.upper()}-ROUTE-SKU"
    barcode = f"{status_step.upper()}-ROUTE-BAR"
    seed_item(client, sku=sku, Barcode=barcode, wooProductId=product_id, **{"In Stock": 8, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order(id=woo_id, number=str(woo_id), line_items=[{**woo_order()["line_items"][0], "id": 1000 + woo_id, "product_id": product_id, "sku": sku, "meta_data": [{"key": "barcode", "value": barcode}]}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == woo_id][0]
    if status_step == "allocated":
        client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    if status_step == "picked":
        client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True})
        client.post("/api/picks/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    return client.get(f"/api/orders/{order['id']}").json()


def route_payload(order_ids):
    return {
        "route_date": "2026-07-07",
        "route_name": "Morning Route",
        "driver_name": "Driver 1",
        "vehicle_name": "Van 1",
        "order_ids": order_ids,
        "created_by": "pytest",
        "notes": "Manual route",
    }


def test_route_candidates_include_fulfilled_and_partial_with_warning(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    partial = fulfilled_route_order(client, monkeypatch, sku="PARTIAL-ROUTE-SKU", barcode="PARTIAL-ROUTE-BAR", woo_id=902, product_id=502, partial=True)

    response = client.get("/api/routes/candidates")

    assert response.status_code == 200
    candidates = response.json()["candidates"]
    ids = {row["order_id"] for row in candidates}
    assert fulfilled["id"] in ids
    assert partial["id"] in ids
    partial_row = [row for row in candidates if row["order_id"] == partial["id"]][0]
    assert partial_row["route_warning"] == "Order is partially fulfilled."


def test_route_candidates_exclude_ineligible_and_active_routed_orders(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    open_order = synced_unfulfilled_order(client, monkeypatch, "open")
    allocated_order = synced_unfulfilled_order(client, monkeypatch, "allocated")
    picked_order_detail = synced_unfulfilled_order(client, monkeypatch, "picked")
    commit = client.post("/api/routes/commit", json=route_payload([fulfilled["id"]]))
    assert commit.json()["status"] == "draft"

    candidates = client.get("/api/routes/candidates").json()["candidates"]
    ids = {row["order_id"] for row in candidates}

    assert fulfilled["id"] not in ids
    assert open_order["id"] not in ids
    assert allocated_order["id"] not in ids
    assert picked_order_detail["id"] not in ids

    client.post(f"/api/routes/{commit.json()['route_id']}/cancel")
    candidates_after_cancel = client.get("/api/routes/candidates").json()["candidates"]
    assert fulfilled["id"] in {row["order_id"] for row in candidates_after_cancel}


def test_route_preview_validates_without_writing_or_inventory_changes(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "ROUTE-SKU"}).json()["items"][0]

    response = client.post("/api/routes/preview", json=route_payload([fulfilled["id"], 999999]))

    assert response.status_code == 200
    body = response.json()
    assert body["total_orders"] == 2
    assert body["valid_orders"] == 1
    assert body["invalid_orders"] == 1
    assert body["preview_route"]["stops"][0]["stop_sequence"] == 1
    assert body["preview_route"]["stops"][0]["status"] == "valid"
    assert body["preview_route"]["stops"][1]["status"] == "invalid"
    assert client.get("/api/routes").json()["total"] == 0
    after_item = client.get("/api/items", params={"sku": "ROUTE-SKU"}).json()["items"][0]
    assert after_item["In Stock"] == before_item["In Stock"]
    assert after_item["Allocated"] == before_item["Allocated"]


def test_route_commit_creates_route_stops_and_rejects_invalid_atomically(client, monkeypatch):
    first = fulfilled_route_order(client, monkeypatch)
    second = fulfilled_route_order(client, monkeypatch, sku="ROUTE-SKU-2", barcode="ROUTE-BAR-2", woo_id=903, product_id=503)
    invalid = client.post("/api/routes/commit", json=route_payload([first["id"], 123456]))
    assert invalid.json()["status"] == "rejected"
    assert client.get("/api/routes").json()["total"] == 0

    response = client.post("/api/routes/commit", json=route_payload([first["id"], second["id"]]))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["route_number"].startswith("RT-")
    assert body["total_stops"] == 2
    detail = client.get(f"/api/routes/{body['route_id']}").json()
    assert [stop["stop_sequence"] for stop in detail["stops"]] == [1, 2]
    assert [stop["order_id"] for stop in detail["stops"]] == [first["id"], second["id"]]

    duplicate = client.post("/api/routes/commit", json=route_payload([first["id"]]))
    assert duplicate.json()["status"] in {"rejected", "error"}
    assert client.get("/api/routes").json()["total"] == 1


def test_route_list_detail_export_finalize_cancel(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    commit = client.post("/api/routes/commit", json=route_payload([fulfilled["id"]]))
    route_id = commit.json()["route_id"]

    listing = client.get("/api/routes")
    detail = client.get(f"/api/routes/{route_id}")
    exported = client.get(f"/api/routes/{route_id}/export")
    finalized = client.post(f"/api/routes/{route_id}/finalize")
    cancelled = client.post(f"/api/routes/{route_id}/cancel")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert len(detail.json()["stops"]) == 1
    assert exported.status_code == 200
    header = exported.text.splitlines()[0].split(",")
    assert header == [
        "Route Number",
        "Route Date",
        "Route Status",
        "Route Name",
        "Driver Name",
        "Vehicle Name",
        "Stop Sequence",
        "Woo Order Number",
        "Woo Order ID",
        "Local Status",
        "Customer Name",
        "Customer Email",
        "Customer Phone",
        "Shipping Summary",
        "Delivery Notes",
        "Stop Status",
        "Order Total",
        "Created At",
    ]
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert rows[0]["Route Number"] == commit.json()["route_number"]
    assert finalized.json()["status"] == "finalized"
    assert cancelled.json()["status"] == "cancelled"
    cancelled_detail = client.get(f"/api/routes/{route_id}").json()
    assert len(cancelled_detail["stops"]) == 1
    candidates = client.get("/api/routes/candidates").json()["candidates"]
    assert fulfilled["id"] in {row["order_id"] for row in candidates}
