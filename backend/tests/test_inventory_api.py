import csv
from decimal import Decimal
from io import StringIO

from app.services.inventory_reports import INVENTORY_BY_LOCATION_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401


def test_inventory_export_by_location_returns_csv(client):
    seed_item(client, sku="INV-EXPORT-001", Warehouse="Main Warehouse", **{"Inventory Location": "Rack A"})

    response = client.get("/api/inventory/export/by-location")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "INV-EXPORT-001" in response.text


def test_inventory_export_includes_required_columns(client):
    seed_item(client, sku="INV-COLS-001")

    response = client.get("/api/inventory/export/by-location")

    assert response.status_code == 200
    assert response.text.splitlines()[0].split(",") == INVENTORY_BY_LOCATION_COLUMNS


def test_inventory_export_supports_warehouse_filter(client):
    seed_item(client, sku="INV-WH-1", Warehouse="Main Warehouse")
    seed_item(client, sku="INV-WH-2", Warehouse="Secondary Warehouse")

    response = client.get("/api/inventory/export/by-location", params={"warehouse": "Secondary Warehouse"})

    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["SKU"] for row in rows] == ["INV-WH-2"]


def test_inventory_export_supports_inventory_location_filter(client):
    seed_item(client, sku="INV-LOC-1", **{"Inventory Location": "Rack A"})
    seed_item(client, sku="INV-LOC-2", **{"Inventory Location": "Rack B"})

    response = client.get("/api/inventory/export/by-location", params={"inventory_location": "Rack B"})

    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["SKU"] for row in rows] == ["INV-LOC-2"]


def test_inventory_export_supports_category_filter(client):
    seed_item(client, sku="INV-CAT-1", Category="Dog Food")
    seed_item(client, sku="INV-CAT-2", Category="Cats")

    response = client.get("/api/inventory/export/by-location", params={"category": "Cats"})

    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["SKU"] for row in rows] == ["INV-CAT-2"]


def test_inventory_export_supports_brand_filter(client):
    seed_item(client, sku="INV-BRAND-1", Brand="North Paw")
    seed_item(client, sku="INV-BRAND-2", Brand="South Paw")

    response = client.get("/api/inventory/export/by-location", params={"brand": "South Paw"})

    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["SKU"] for row in rows] == ["INV-BRAND-2"]


def test_inventory_export_supports_under_par_filter(client):
    seed_item(client, sku="INV-PAR-1", **{"In Stock": 2, "Par Level": 5})
    seed_item(client, sku="INV-PAR-2", **{"In Stock": 9, "Par Level": 5})

    response = client.get("/api/inventory/export/by-location", params={"under_par": True})

    rows = list(csv.DictReader(StringIO(response.text)))
    assert [row["SKU"] for row in rows] == ["INV-PAR-1"]


def test_inventory_summary_groups_items_by_warehouse_and_inventory_location(client):
    seed_item(client, sku="INV-GRP-1", Warehouse="Main Warehouse", **{"Inventory Location": "Rack A"})
    seed_item(client, sku="INV-GRP-2", Warehouse="Main Warehouse", **{"Inventory Location": "Rack A"})
    seed_item(client, sku="INV-GRP-3", Warehouse="Main Warehouse", **{"Inventory Location": "Rack B"})

    response = client.get("/api/inventory/summary/by-location")

    assert response.status_code == 200
    groups = response.json()["groups"]
    rack_a = next(group for group in groups if group["inventory_location"] == "Rack A")
    assert rack_a["warehouse"] == "Main Warehouse"
    assert rack_a["item_count"] == 2


def test_inventory_summary_calculates_totals(client):
    seed_item(client, sku="INV-TOT-1", Warehouse="Main Warehouse", **{"Inventory Location": "Rack A", "In Stock": 10, "Allocated": 3, "On Order": 2, "Unit Cost": 4, "Par Level": 8})
    seed_item(client, sku="INV-TOT-2", Warehouse="Main Warehouse", **{"Inventory Location": "Rack A", "In Stock": 2, "Allocated": 1, "On Order": 5, "Unit Cost": 6, "Par Level": 3})

    response = client.get("/api/inventory/summary/by-location")

    assert response.status_code == 200
    group = response.json()["groups"][0]
    assert group["total_in_stock"] == 12
    assert group["total_allocated"] == 4
    assert group["total_sellable"] == 8
    assert group["total_on_order"] == 7
    assert group["total_inventory_value"] == 52
    assert group["under_par_count"] == 1


def test_inventory_export_recalculates_derived_fields(client):
    seed_item(
        client,
        sku="INV-CALC-1",
        **{
            "In Stock": 3,
            "Allocated": 2,
            "Par Level": 3,
            "Unit Cost": 7,
            "Storage Length": 2,
            "Storage Width": 5,
            "Storage Height": 4,
        },
    )

    response = client.get("/api/inventory/export/by-location", params={"warehouse": "Main Warehouse"})

    row = next(row for row in csv.DictReader(StringIO(response.text)) if row["SKU"] == "INV-CALC-1")
    assert Decimal(row["Sellable"]) == Decimal("1")
    assert row["Under Par"] == "True"
    assert Decimal(row["Storage Volume"]) == Decimal("40")
    assert Decimal(row["Inventory Value"]) == Decimal("21")
