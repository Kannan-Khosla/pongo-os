import csv
from datetime import date, timedelta
from io import StringIO

import pytest

from app.services.received_inventory_report import RECEIVED_INVENTORY_CSV_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import seed_location
from tests.test_receiving_api import direct_payload


def setup_received_inventory(client):
    seed_item(client, sku="RPT-001", Barcode="RPT-BAR-001", Category="Dog Treats", Brand="North Paw", **{"In Stock": 10, "Unit Cost": 2.5, "Inventory Location": "REC-A"})
    seed_item(client, sku="RPT-002", Barcode="RPT-BAR-002", Category="Cats", Brand="South Paw", **{"In Stock": 4, "Unit Cost": 4, "Inventory Location": "REC-B"})
    seed_location(client, code="REC-A", name="Receiving A")
    seed_location(client, code="REC-B", name="Receiving B")
    payload = direct_payload(
        reference_number="BOL-777",
        notes="Report receipt notes",
        created_by="report-user",
        lines=[
            {"sku": "RPT-001", "barcode": "RPT-BAR-001", "inventory_location": "REC-A", "default_location": "REC-A", "quantity_received": 3, "unit_cost": 2.5, "notes": "First line"},
            {"sku": "RPT-002", "barcode": "RPT-BAR-002", "inventory_location": "REC-B", "default_location": "REC-B", "quantity_received": 2, "unit_cost": 4, "notes": "Second line"},
        ],
    )
    response = client.post("/api/receipts/direct/commit", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def report_rows(client, params=None):
    response = client.get("/api/reports/received-inventory", params=params or {})
    assert response.status_code == 200, response.text
    return response.json()


def report_summary(client, params=None):
    response = client.get("/api/reports/received-inventory/summary", params=params or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_received_inventory_report_returns_rows_after_direct_receiving_commit(client):
    receipt = setup_received_inventory(client)

    rows = report_rows(client)

    assert len(rows) == 2
    first = next(row for row in rows if row["sku"] == "RPT-001")
    assert first["receipt_number"] == receipt["receipt_number"]
    assert first["quantity_received"] == 3
    assert first["inventory_location"] == "REC-A"
    assert first["total_received_value"] == 7.5


def test_received_inventory_summary_calculates_totals_and_groups(client):
    setup_received_inventory(client)

    summary = report_summary(client)

    assert summary["total_receipts"] == 1
    assert summary["total_lines"] == 2
    assert summary["total_quantity_received"] == 5
    assert summary["total_received_value"] == 15.5
    assert summary["unique_skus"] == 2
    assert summary["unique_locations"] == 2
    assert summary["by_warehouse"][0]["warehouse"] == "Main Warehouse"
    assert summary["by_warehouse"][0]["total_lines"] == 2
    assert {row["inventory_location"] for row in summary["by_location"]} == {"REC-A", "REC-B"}
    sku_group = next(row for row in summary["by_sku"] if row["sku"] == "RPT-001")
    assert sku_group["brand"] == "North Paw"
    assert sku_group["category"] == "Dog Treats"
    assert sku_group["receipt_count"] == 1


def test_received_inventory_csv_export_returns_expected_headers_and_rows(client):
    setup_received_inventory(client)

    response = client.get("/api/reports/received-inventory/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(StringIO(response.text)))
    assert response.text.splitlines()[0].split(",") == RECEIVED_INVENTORY_CSV_COLUMNS
    assert {row["SKU"] for row in rows} == {"RPT-001", "RPT-002"}
    assert next(row for row in rows if row["SKU"] == "RPT-001")["Total Received Value"] == "7.5"


@pytest.mark.parametrize(
    ("params", "expected_skus"),
    [
        ({"warehouse": "Main Warehouse"}, {"RPT-001", "RPT-002"}),
        ({"inventory_location": "REC-A"}, {"RPT-001"}),
        ({"sku": "RPT-001"}, {"RPT-001"}),
        ({"barcode": "RPT-BAR-002"}, {"RPT-002"}),
        ({"brand": "North Paw"}, {"RPT-001"}),
        ({"category": "Cats"}, {"RPT-002"}),
        ({"reference_number": "BOL-777"}, {"RPT-001", "RPT-002"}),
        ({"created_by": "pytest@example.com"}, {"RPT-001", "RPT-002"}),
    ],
)
def test_received_inventory_report_filters(client, params, expected_skus):
    setup_received_inventory(client)

    rows = report_rows(client, params=params)

    assert {row["sku"] for row in rows} == expected_skus


def test_received_inventory_report_filters_by_receipt_number(client):
    receipt = setup_received_inventory(client)

    rows = report_rows(client, params={"receipt_number": receipt["receipt_number"]})

    assert {row["sku"] for row in rows} == {"RPT-001", "RPT-002"}


def test_received_inventory_report_date_filters(client):
    setup_received_inventory(client)
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    assert len(report_rows(client, params={"date_from": today})) == 2
    assert len(report_rows(client, params={"date_to": today})) == 2
    assert report_rows(client, params={"date_from": tomorrow}) == []
    assert report_rows(client, params={"date_to": yesterday}) == []


def test_received_inventory_report_endpoints_do_not_modify_item_stock(client):
    setup_received_inventory(client)
    before = client.get("/api/items", params={"sku": "RPT-001"}).json()["items"][0]["In Stock"]

    client.get("/api/reports/received-inventory")
    client.get("/api/reports/received-inventory/summary")
    client.get("/api/reports/received-inventory/export")

    after = client.get("/api/items", params={"sku": "RPT-001"}).json()["items"][0]["In Stock"]
    assert after == before
