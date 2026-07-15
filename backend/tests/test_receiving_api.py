from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import seed_location
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def direct_payload(**overrides):
    payload = {
        "warehouse": "Main Warehouse",
        "reference_number": "INV-12345",
        "notes": "Manual receiving without PO",
        "created_by": "system",
        "lines": [
            {
                "sku": "RCV-001",
                "barcode": "RCV-001-BAR",
                "inventory_location": "REC-01",
                "default_location": "REC-01",
                "quantity_received": 5,
                "unit_cost": 3.5,
                "notes": "Received from delivery",
            }
        ],
    }
    payload.update(overrides)
    return payload


def setup_receiving_item_and_location(client, sku="RCV-001", barcode="RCV-001-BAR", in_stock=10, allocated=2, location_code="REC-01", active=True):
    item = seed_item(client, sku=sku, Barcode=barcode, **{"In Stock": in_stock, "Allocated": allocated, "Unit Cost": 4, "Inventory Location": location_code})
    location = seed_location(client, code=location_code, name=location_code, isActive=active)
    return item, location


def test_direct_receiving_preview_validates_valid_line(client):
    setup_receiving_item_and_location(client)

    response = client.post("/api/receipts/direct/preview", json=direct_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["valid_lines"] == 1
    assert body["invalid_lines"] == 0
    assert body["preview_lines"][0]["previous_in_stock"] == 10
    assert body["preview_lines"][0]["new_in_stock"] == 15


def test_direct_receiving_preview_does_not_update_stock(client):
    setup_receiving_item_and_location(client)

    client.post("/api/receipts/direct/preview", json=direct_payload())

    item = client.get("/api/items", params={"sku": "RCV-001"}).json()["items"][0]
    assert item["In Stock"] == 10


def test_direct_receiving_commit_creates_receipt_line_stock_and_movement(client):
    setup_receiving_item_and_location(client)

    response = client.post("/api/receipts/direct/commit", json=direct_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["receipt_number"].startswith("DR-")
    assert body["status"] == "posted"
    assert body["total_lines"] == 1
    assert body["total_quantity_received"] == 5
    assert body["created_movements"] == 1

    item = client.get("/api/items", params={"sku": "RCV-001"}).json()["items"][0]
    assert item["In Stock"] == 15
    assert item["Allocated"] == 2
    assert item["Sellable"] == 13

    detail = client.get(f"/api/receipts/{body['receipt_id']}")
    assert detail.status_code == 200
    assert detail.json()["lines"][0]["sku"] == "RCV-001"
    assert detail.json()["lines"][0]["quantity_received"] == 5

    movements = client.get("/api/stock-movements", params={"sku": "RCV-001"}).json()["movements"]
    assert len(movements) == 1
    assert movements[0]["movement_type"] == "receive_direct"
    assert movements[0]["quantity_delta"] == 5
    assert movements[0]["previous_in_stock"] == 10
    assert movements[0]["new_in_stock"] == 15
    assert movements[0]["reference_type"] == "direct_receipt"


def test_direct_receiving_auto_allocates_oldest_waiting_processing_order(client, monkeypatch):
    seed_item(
        client,
        sku="RCV-FIFO",
        Barcode="RCV-FIFO-BAR",
        wooProductId=951,
        **{"In Stock": 0, "Allocated": 0, "Inventory Location": "REC-FIFO"},
    )
    seed_location(client, code="REC-FIFO", name="REC-FIFO")
    order_line = {
        **woo_order()["line_items"][0],
        "id": 9951,
        "product_id": 951,
        "sku": "RCV-FIFO",
        "quantity": 2,
        "meta_data": [{"key": "barcode", "value": "RCV-FIFO-BAR"}],
    }
    patch_woo_order_client(monkeypatch, [woo_order(id=951, number="RCV-WAITING", line_items=[order_line])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    waiting = next(row for row in client.get("/api/orders/allocate").json()["orders"] if row["woo_order_number"] == "RCV-WAITING")

    response = client.post(
        "/api/receipts/direct/commit",
        json=direct_payload(
            reference_number="FIFO-RESTOCK",
            lines=[{"sku": "RCV-FIFO", "inventory_location": "REC-FIFO", "quantity_received": 2}],
        ),
    )

    assert response.status_code == 200, response.text
    detail = client.get(f"/api/orders/{waiting['id']}").json()
    assert detail["lines"][0]["quantity_allocated"] == 2
    assert detail["shows_in_allocate"] is False
    assert detail["shows_in_pick_orders"] is True


def test_receiving_by_sku_works(client):
    setup_receiving_item_and_location(client)
    payload = direct_payload(lines=[{"sku": "RCV-001", "inventory_location": "REC-01", "quantity_received": 1}])

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 200


def test_receiving_by_barcode_works(client):
    setup_receiving_item_and_location(client)
    payload = direct_payload(lines=[{"barcode": "RCV-001-BAR", "inventory_location": "REC-01", "quantity_received": 1}])

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 200


def test_sku_and_barcode_conflict_rejects_full_receipt(client):
    setup_receiving_item_and_location(client, sku="RCV-SKU", barcode="BAR-1")
    seed_item(client, sku="OTHER-SKU", Barcode="BAR-2")
    payload = direct_payload(lines=[{"sku": "RCV-SKU", "barcode": "BAR-2", "inventory_location": "REC-01", "quantity_received": 1}])

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 400
    item = client.get("/api/items", params={"sku": "RCV-SKU"}).json()["items"][0]
    assert item["In Stock"] == 10


def test_unknown_item_rejects_full_receipt(client):
    seed_location(client, code="REC-01", name="REC-01")

    response = client.post("/api/receipts/direct/commit", json=direct_payload(lines=[{"sku": "UNKNOWN", "inventory_location": "REC-01", "quantity_received": 1}]))

    assert response.status_code == 400


def test_missing_warehouse_rejects_receipt(client):
    setup_receiving_item_and_location(client)

    response = client.post("/api/receipts/direct/commit", json=direct_payload(warehouse=""))

    assert response.status_code == 400


def test_missing_inventory_location_rejects_line(client):
    setup_receiving_item_and_location(client)
    payload = direct_payload(lines=[{"sku": "RCV-001", "quantity_received": 1}])

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 400


def test_inactive_location_rejects_line(client):
    setup_receiving_item_and_location(client, active=False)

    response = client.post("/api/receipts/direct/commit", json=direct_payload())

    assert response.status_code == 400


def test_non_existing_location_rejects_line(client):
    seed_item(client, sku="RCV-001", Barcode="RCV-001-BAR")

    response = client.post("/api/receipts/direct/commit", json=direct_payload())

    assert response.status_code == 400


def test_quantity_less_than_or_equal_to_zero_rejects_line(client):
    setup_receiving_item_and_location(client)
    payload = direct_payload(lines=[{"sku": "RCV-001", "inventory_location": "REC-01", "quantity_received": 0}])

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 400


def test_multiple_valid_lines_commit_atomically(client):
    setup_receiving_item_and_location(client, sku="RCV-A", barcode="BAR-A", in_stock=1)
    seed_item(client, sku="RCV-B", Barcode="BAR-B", **{"In Stock": 2, "Allocated": 0, "Unit Cost": 2})
    payload = direct_payload(
        lines=[
            {"sku": "RCV-A", "inventory_location": "REC-01", "quantity_received": 2},
            {"sku": "RCV-B", "inventory_location": "REC-01", "quantity_received": 3},
        ]
    )

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 200
    assert client.get("/api/items", params={"sku": "RCV-A"}).json()["items"][0]["In Stock"] == 3
    assert client.get("/api/items", params={"sku": "RCV-B"}).json()["items"][0]["In Stock"] == 5


def test_invalid_line_prevents_all_stock_updates(client):
    setup_receiving_item_and_location(client, sku="RCV-A", barcode="BAR-A", in_stock=1)
    seed_item(client, sku="RCV-B", Barcode="BAR-B", **{"In Stock": 2})
    payload = direct_payload(
        lines=[
            {"sku": "RCV-A", "inventory_location": "REC-01", "quantity_received": 2},
            {"sku": "RCV-B", "inventory_location": "MISSING", "quantity_received": 3},
        ]
    )

    response = client.post("/api/receipts/direct/commit", json=payload)

    assert response.status_code == 400
    assert client.get("/api/items", params={"sku": "RCV-A"}).json()["items"][0]["In Stock"] == 1
    assert client.get("/api/items", params={"sku": "RCV-B"}).json()["items"][0]["In Stock"] == 2


def test_get_receipts_lists_receipts(client):
    setup_receiving_item_and_location(client)
    client.post("/api/receipts/direct/commit", json=direct_payload())

    response = client.get("/api/receipts")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["receipts"][0]["receipt_type"] == "direct"


def test_get_stock_movements_returns_history(client):
    setup_receiving_item_and_location(client)
    client.post("/api/receipts/direct/commit", json=direct_payload())

    response = client.get("/api/stock-movements", params={"movement_type": "receive_direct"})

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_inventory_summary_reflects_received_stock_after_commit(client):
    setup_receiving_item_and_location(client, in_stock=10, allocated=2)
    client.post("/api/receipts/direct/commit", json=direct_payload())

    response = client.get("/api/inventory/summary/by-location", params={"inventory_location": "REC-01"})

    group = response.json()["groups"][0]
    assert group["total_in_stock"] == 15
    assert group["total_sellable"] == 13
