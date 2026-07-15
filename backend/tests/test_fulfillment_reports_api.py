import csv
from io import StringIO

from tests.test_fulfillments_api import picked_order
from tests.test_items_api import client  # noqa: F401


FULFILLMENT_CSV_HEADER = [
    "Fulfillment Number",
    "Status",
    "Posted At",
    "Created At",
    "Woo Order Number",
    "Woo Order ID",
    "Local Status",
    "Customer Name",
    "Customer Email",
    "Warehouse",
    "Inventory Location",
    "SKU",
    "Barcode",
    "Description",
    "Category",
    "Brand",
    "Quantity Ordered",
    "Quantity Allocated",
    "Quantity Picked",
    "Quantity Fulfilled",
    "Previously Fulfilled",
    "Remaining To Fulfill",
    "Unit Cost",
    "Fulfilled Value",
    "In Stock Before",
    "Allocated Before",
    "Sellable Before",
    "In Stock After",
    "Allocated After",
    "Sellable After",
    "Created By",
    "Line Notes",
    "Fulfillment Notes",
]


def fulfilled_order(client, monkeypatch):
    order, _ = picked_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="REPORT-FULFILL-SKU", barcode="REPORT-FULFILL-BAR", woo_id=801, product_id=401)
    commit = client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True, "created_by": "reporter", "notes": "Report fulfillment"})
    assert commit.status_code == 200, commit.text
    assert commit.json()["status"] == "posted"
    return order, commit.json()


def test_fulfillment_report_rows_summary_csv_and_read_only(client, monkeypatch):
    order, commit = fulfilled_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "REPORT-FULFILL-SKU"}).json()["items"][0]

    rows_response = client.get("/api/reports/fulfillments")
    summary_response = client.get("/api/reports/fulfillments/summary")
    export_response = client.get("/api/reports/fulfillments/export")

    assert rows_response.status_code == 200
    rows = rows_response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["fulfillment_number"] == commit["fulfillment_number"]
    assert row["woo_order_number"] == "801"
    assert row["sku"] == "REPORT-FULFILL-SKU"
    assert row["barcode"] == "REPORT-FULFILL-BAR"
    assert row["category"] == "Dog Food"
    assert row["brand"] == "Test Brand"
    assert row["quantity_fulfilled"] == 2
    assert row["quantity_previously_fulfilled"] == 0
    assert row["remaining_to_fulfill"] == 0
    assert row["unit_cost"] == 4.25
    assert row["fulfilled_value"] == 8.5
    assert row["in_stock_before"] == 4
    assert row["in_stock_after"] == 4
    assert row["allocated_before"] == 1
    assert row["allocated_after"] == 1
    assert row["created_by"] == "reporter"
    assert row["fulfillment_notes"] == "Report fulfillment"

    summary = summary_response.json()
    assert summary["total_fulfillments"] == 1
    assert summary["total_orders"] == 1
    assert summary["total_lines"] == 1
    assert summary["total_quantity_fulfilled"] == 2
    assert summary["total_fulfilled_value"] == 8.5
    assert summary["unique_skus"] == 1
    assert summary["unique_locations"] == 1
    assert summary["by_warehouse"][0]["warehouse"] == "Main Warehouse"
    assert summary["by_location"][0]["inventory_location"] == "Rack 1"
    assert summary["by_sku"][0]["sku"] == "REPORT-FULFILL-SKU"
    assert summary["by_sku"][0]["fulfillment_count"] == 1
    assert summary["by_sku"][0]["order_count"] == 1
    assert summary["by_order"][0]["woo_order_number"] == "801"

    assert export_response.status_code == 200
    assert export_response.text.splitlines()[0].split(",") == FULFILLMENT_CSV_HEADER
    exported_rows = list(csv.DictReader(StringIO(export_response.text)))
    assert exported_rows[0]["Fulfillment Number"] == commit["fulfillment_number"]
    assert exported_rows[0]["Quantity Fulfilled"] == "2.0"

    after_item = client.get("/api/items", params={"sku": "REPORT-FULFILL-SKU"}).json()["items"][0]
    assert after_item["In Stock"] == before_item["In Stock"]
    assert after_item["Allocated"] == before_item["Allocated"]
    assert client.get(f"/api/orders/{order['id']}").json()["woo_status"] == "processing"


def test_fulfillment_report_filters(client, monkeypatch):
    _, commit = fulfilled_order(client, monkeypatch)
    row = client.get("/api/reports/fulfillments").json()[0]
    report_date = row["posted_at"][:10]

    matching_filters = {
        "date_from": report_date,
        "date_to": report_date,
        "warehouse": "Main Warehouse",
        "inventory_location": "Rack 1",
        "sku": "REPORT-FULFILL-SKU",
        "barcode": "REPORT-FULFILL-BAR",
        "category": "Dog Food",
        "brand": "Test Brand",
        "fulfillment_number": commit["fulfillment_number"],
        "woo_order_number": "801",
        "woo_order_id": 801,
        "customer_email": "avery@example.invalid",
        "local_status": "fulfilled",
        "created_by": "reporter",
    }
    for key, value in matching_filters.items():
        filtered = client.get("/api/reports/fulfillments", params={key: value})
        assert filtered.status_code == 200
        assert len(filtered.json()) == 1, key

    assert client.get("/api/reports/fulfillments", params={"sku": "NOPE"}).json() == []
    assert client.get("/api/reports/fulfillments/summary", params={"sku": "NOPE"}).json()["total_lines"] == 0


def test_completed_orders_list_filters_export_and_read_only(client, monkeypatch):
    order, _ = fulfilled_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "REPORT-FULFILL-SKU"}).json()["items"][0]

    listing = client.get("/api/orders/completed")

    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    completed = body["orders"][0]
    assert completed["id"] == order["id"]
    assert completed["local_status"] == "fulfilled"
    assert completed["line_count"] == 1
    assert completed["fulfilled_line_count"] == 1
    assert completed["total_quantity_ordered"] == 2
    assert completed["total_quantity_allocated"] == 2
    assert completed["total_quantity_picked"] == 2
    assert completed["total_quantity_fulfilled"] == 2
    assert completed["total_remaining_to_fulfill"] == 0
    assert completed["total_fulfilled_value"] == 8.5

    for params in [
        {"local_status": "fulfilled"},
        {"customer_email": "avery@example.invalid"},
        {"woo_order_number": "801"},
        {"sku": "REPORT-FULFILL-SKU"},
        {"barcode": "REPORT-FULFILL-BAR"},
        {"search": "Avery"},
    ]:
        assert client.get("/api/orders/completed", params=params).json()["total"] == 1
    assert client.get("/api/orders/completed", params={"local_status": "partially_fulfilled"}).json()["total"] == 0

    exported = client.get("/api/orders/completed/export")
    assert exported.status_code == 200
    header = exported.text.splitlines()[0].split(",")
    assert header == [
        "Woo Order Number",
        "Woo Order ID",
        "Woo Status",
        "Local Status",
        "Customer Name",
        "Customer Email",
        "Order Total",
        "Line SKU",
        "Line Barcode",
        "Line Name",
        "Quantity Ordered",
        "Quantity Allocated",
        "Quantity Picked",
        "Quantity Fulfilled",
        "Remaining To Fulfill",
        "Fulfillment Status",
        "Fulfilled Value",
        "Date Created",
        "Date Modified",
    ]
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert rows[0]["Woo Order Number"] == "801"
    assert rows[0]["Quantity Fulfilled"] == "2.0"

    after_item = client.get("/api/items", params={"sku": "REPORT-FULFILL-SKU"}).json()["items"][0]
    assert after_item["In Stock"] == before_item["In Stock"]
    assert after_item["Allocated"] == before_item["Allocated"]


def test_completed_orders_includes_partially_fulfilled(client, monkeypatch):
    order, line = picked_order(client, monkeypatch, item_stock=6, item_allocated=1, quantity=2, sku="PARTIAL-REPORT-SKU", barcode="PARTIAL-REPORT-BAR", woo_id=802, product_id=402)
    client.post("/api/fulfillments/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_fulfill": 1}], "allow_partial": True})

    listing = client.get("/api/orders/completed", params={"local_status": "partially_fulfilled"})

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["orders"][0]["id"] == order["id"]
