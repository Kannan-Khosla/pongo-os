import csv
from io import StringIO

from app.services.cycle_counts import CYCLE_COUNT_EXPORT_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import force_location_active_for_legacy_test, seed_location


def cycle_payload(**overrides):
    payload = {
        "warehouse": "Main Warehouse",
        "inventory_location": "CC-01",
        "count_type": "selected_items",
        "notes": "Manual shelf count",
        "created_by": "system",
        "lines": [
            {
                "sku": "CC-001",
                "barcode": "CC-001-BAR",
                "counted_quantity": 12,
                "notes": "Shelf count",
            }
        ],
    }
    payload.update(overrides)
    return payload


def setup_cycle_item_and_location(client, sku="CC-001", barcode="CC-001-BAR", in_stock=10, allocated=2, par_level=8, location_code="CC-01", active=True):
    item = seed_item(
        client,
        sku=sku,
        Barcode=barcode,
        **{"In Stock": in_stock, "Allocated": allocated, "Unit Cost": 4, "Par Level": par_level, "Inventory Location": location_code},
    )
    location = seed_location(client, code=location_code, name=location_code, isActive=True)
    if not active:
        force_location_active_for_legacy_test(location["id"], False)
        location["isActive"] = False
    return item, location


def test_cycle_count_preview_validates_valid_line(client):
    setup_cycle_item_and_location(client)

    response = client.post("/api/cycle-counts/preview", json=cycle_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["valid_lines"] == 1
    assert body["invalid_lines"] == 0
    assert body["adjustment_lines"] == 1
    assert body["preview_lines"][0]["system_quantity"] == 10
    assert body["preview_lines"][0]["counted_quantity"] == 12
    assert body["preview_lines"][0]["variance_quantity"] == 2
    assert body["preview_lines"][0]["variance_value"] == 8


def test_cycle_count_preview_does_not_update_item_stock(client):
    setup_cycle_item_and_location(client)

    client.post("/api/cycle-counts/preview", json=cycle_payload())

    item = client.get("/api/items", params={"sku": "CC-001"}).json()["items"][0]
    assert item["In Stock"] == 10


def test_cycle_count_commit_creates_count_lines_updates_stock_and_movement(client):
    setup_cycle_item_and_location(client, in_stock=10, allocated=2, par_level=11)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["count_number"].startswith("CC-")
    assert body["status"] == "posted"
    assert body["total_lines"] == 1
    assert body["adjustment_lines"] == 1
    assert body["created_movements"] == 1

    item = client.get("/api/items", params={"sku": "CC-001"}).json()["items"][0]
    assert item["In Stock"] == 12
    assert item["Allocated"] == 2
    assert item["Sellable"] == 10
    assert item["Under Par"] is False

    detail = client.get(f"/api/cycle-counts/{body['cycle_count_id']}")
    assert detail.status_code == 200
    assert detail.json()["lines"][0]["sku"] == "CC-001"
    assert detail.json()["lines"][0]["system_quantity"] == 10
    assert detail.json()["lines"][0]["counted_quantity"] == 12

    movements = client.get("/api/stock-movements", params={"movement_type": "cycle_count_adjustment"}).json()["movements"]
    assert len(movements) == 1
    assert movements[0]["sku"] == "CC-001"
    assert movements[0]["quantity_delta"] == 2
    assert movements[0]["previous_in_stock"] == 10
    assert movements[0]["new_in_stock"] == 12
    assert movements[0]["reference_type"] == "cycle_count"
    assert movements[0]["reference_number"] == body["count_number"]


def test_cycle_count_zero_variance_creates_line_without_stock_movement(client):
    setup_cycle_item_and_location(client, in_stock=10)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(lines=[{"sku": "CC-001", "counted_quantity": 10}]))

    assert response.status_code == 200
    assert response.json()["created_movements"] == 0
    detail = client.get(f"/api/cycle-counts/{response.json()['cycle_count_id']}").json()
    assert detail["total_lines"] == 1
    assert detail["lines"][0]["variance_quantity"] == 0
    assert client.get("/api/stock-movements", params={"movement_type": "cycle_count_adjustment"}).json()["total"] == 0


def test_cycle_count_by_sku_works(client):
    setup_cycle_item_and_location(client)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(lines=[{"sku": "CC-001", "counted_quantity": 9}]))

    assert response.status_code == 200


def test_cycle_count_by_barcode_works(client):
    setup_cycle_item_and_location(client)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(lines=[{"barcode": "CC-001-BAR", "counted_quantity": 9}]))

    assert response.status_code == 200


def test_cycle_count_sku_and_barcode_conflict_rejects_full_count(client):
    setup_cycle_item_and_location(client, sku="CC-SKU", barcode="BAR-1", in_stock=10)
    seed_item(client, sku="OTHER-SKU", Barcode="BAR-2")
    payload = cycle_payload(lines=[{"sku": "CC-SKU", "barcode": "BAR-2", "counted_quantity": 3}])

    response = client.post("/api/cycle-counts/commit", json=payload)

    assert response.status_code == 400
    item = client.get("/api/items", params={"sku": "CC-SKU"}).json()["items"][0]
    assert item["In Stock"] == 10


def test_cycle_count_unknown_item_rejects_full_count(client):
    seed_location(client, code="CC-01", name="CC-01")

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(lines=[{"sku": "UNKNOWN", "counted_quantity": 1}]))

    assert response.status_code == 400


def test_cycle_count_missing_warehouse_rejects_count(client):
    setup_cycle_item_and_location(client)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(warehouse=""))

    assert response.status_code == 400


def test_full_location_cycle_count_requires_inventory_location(client):
    setup_cycle_item_and_location(client)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(count_type="full_location", inventory_location=""))

    assert response.status_code == 400


def test_cycle_count_missing_or_inactive_location_rejects_when_provided(client):
    seed_item(client, sku="CC-001", Barcode="CC-001-BAR")
    missing = client.post("/api/cycle-counts/commit", json=cycle_payload(inventory_location="MISSING"))
    assert missing.status_code == 400

    setup_cycle_item_and_location(client, sku="CC-INACTIVE", barcode="CC-INACTIVE-BAR", location_code="CC-INACTIVE", active=False)
    inactive = client.post("/api/cycle-counts/commit", json=cycle_payload(inventory_location="CC-INACTIVE", lines=[{"sku": "CC-INACTIVE", "counted_quantity": 1}]))
    assert inactive.status_code == 400


def test_cycle_count_negative_counted_quantity_rejects_line(client):
    setup_cycle_item_and_location(client)

    response = client.post("/api/cycle-counts/commit", json=cycle_payload(lines=[{"sku": "CC-001", "counted_quantity": -1}]))

    assert response.status_code == 400


def test_multiple_valid_cycle_count_lines_commit_atomically(client):
    setup_cycle_item_and_location(client, sku="CC-A", barcode="BAR-A", in_stock=1, allocated=0)
    seed_item(client, sku="CC-B", Barcode="BAR-B", **{"In Stock": 2, "Allocated": 0, "Unit Cost": 2, "Inventory Location": "CC-01"})
    payload = cycle_payload(lines=[{"sku": "CC-A", "counted_quantity": 4}, {"sku": "CC-B", "counted_quantity": 5}])

    response = client.post("/api/cycle-counts/commit", json=payload)

    assert response.status_code == 200
    assert client.get("/api/items", params={"sku": "CC-A"}).json()["items"][0]["In Stock"] == 4
    assert client.get("/api/items", params={"sku": "CC-B"}).json()["items"][0]["In Stock"] == 5


def test_invalid_cycle_count_line_prevents_all_stock_updates(client):
    setup_cycle_item_and_location(client, sku="CC-A", barcode="BAR-A", in_stock=1, allocated=0)
    seed_item(client, sku="CC-B", Barcode="BAR-B", **{"In Stock": 2, "Allocated": 0, "Inventory Location": "CC-01"})
    payload = cycle_payload(lines=[{"sku": "CC-A", "counted_quantity": 4}, {"sku": "UNKNOWN", "counted_quantity": 5}])

    response = client.post("/api/cycle-counts/commit", json=payload)

    assert response.status_code == 400
    assert client.get("/api/items", params={"sku": "CC-A"}).json()["items"][0]["In Stock"] == 1
    assert client.get("/api/items", params={"sku": "CC-B"}).json()["items"][0]["In Stock"] == 2


def test_get_cycle_counts_lists_counts(client):
    setup_cycle_item_and_location(client)
    client.post("/api/cycle-counts/commit", json=cycle_payload())

    response = client.get("/api/cycle-counts")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["cycle_counts"][0]["status"] == "posted"


def test_cycle_count_export_returns_csv(client):
    setup_cycle_item_and_location(client)
    created = client.post("/api/cycle-counts/commit", json=cycle_payload()).json()

    response = client.get(f"/api/cycle-counts/{created['cycle_count_id']}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0].split(",") == CYCLE_COUNT_EXPORT_COLUMNS
    rows = list(csv.DictReader(StringIO(response.text)))
    assert rows[0]["Count Number"] == created["count_number"]
    assert rows[0]["SKU"] == "CC-001"


def test_inventory_summary_reflects_adjusted_stock_after_cycle_count(client):
    setup_cycle_item_and_location(client, in_stock=10, allocated=2)
    client.post("/api/cycle-counts/commit", json=cycle_payload(lines=[{"sku": "CC-001", "counted_quantity": 6}]))

    response = client.get("/api/inventory/summary/by-location", params={"inventory_location": "CC-01"})

    group = response.json()["groups"][0]
    assert group["total_in_stock"] == 6
    assert group["total_sellable"] == 4
