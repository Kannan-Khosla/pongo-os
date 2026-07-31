import csv
from decimal import Decimal
from io import StringIO

from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryItem, InventoryItemLocation
from app.services.inventory_reports import INVENTORY_BY_LOCATION_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401


def test_inventory_export_by_location_returns_csv(client):
    seed_item(client, sku="INV-EXPORT-001", Warehouse="Main Warehouse", **{"Inventory Location": "Rack A"})

    response = client.get("/api/inventory/export/by-location")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "INV-EXPORT-001" in response.text


def test_inventory_locations_filters_by_comma_separated_item_ids(client):
    first = seed_item(client, sku="LOC-ID-1")
    seed_item(client, sku="LOC-ID-2")
    third = seed_item(client, sku="LOC-ID-3")

    response = client.get(
        "/api/inventory/locations",
        params={"item_ids": f"{first['id']},{third['id']}", "limit": 100},
    )

    assert response.status_code == 200
    assert {row["item_id"] for row in response.json()["rows"]} == {first["id"], third["id"]}


def test_inventory_locations_rejects_invalid_item_ids(client):
    response = client.get("/api/inventory/locations", params={"item_ids": "1,not-an-id"})

    assert response.status_code == 422


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
    seed_item(client, sku="INV-PAR-1", **{"In Stock": 2, "Allocated": 0, "Par Level": 5})
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


def test_inventory_summary_uses_the_same_search_and_quality_filters_as_catalog_rows(client):
    seed_item(client, sku="SUMMARY-MATCH", Description="Needle product", **{"In Stock": 7, "Unit Cost": None})
    seed_item(client, sku="SUMMARY-OTHER", Description="Other product", **{"In Stock": 11, "Unit Cost": 5})

    summary = client.get(
        "/api/inventory/summary/by-location",
        params={"search": "needle", "data_quality": "missing_cost"},
    )

    assert summary.status_code == 200
    assert summary.json()["total_items"] == 1
    assert summary.json()["total_in_stock"] == 7
    assert client.get("/api/inventory/summary/by-location", params={"data_quality": "unknown"}).status_code == 422


def test_inventory_exports_keep_missing_cost_blank_and_real_zero_numeric(client):
    seed_item(client, sku="EXPORT-NULL-COST", **{"Unit Cost": None, "In Stock": 3})
    seed_item(client, sku="EXPORT-ZERO-COST", **{"Unit Cost": 0, "In Stock": 3})

    by_item_rows = list(csv.DictReader(StringIO(client.get("/api/inventory/export/by-location").text)))
    by_location_rows = list(csv.DictReader(StringIO(client.get("/api/inventory/locations/export").text)))

    for rows in (by_item_rows, by_location_rows):
        null_cost = next(row for row in rows if row["SKU"] == "EXPORT-NULL-COST")
        zero_cost = next(row for row in rows if row["SKU"] == "EXPORT-ZERO-COST")
        assert null_cost["Unit Cost"] == ""
        assert null_cost["Inventory Value"] == ""
        assert Decimal(zero_cost["Unit Cost"]) == Decimal("0")
        assert Decimal(zero_cost["Inventory Value"]) == Decimal("0")


def test_inventory_valuation_summary_explains_record_exclusions(client):
    valued = seed_item(client, sku="VALUE-1", Description="A very long marketing description that should not be the report title", **{"Unit Cost": 4})
    seed_item(client, sku="NO-COST", **{"Unit Cost": None})
    unlocated = seed_item(
        client,
        sku="NO-LOCATION",
        Warehouse=None,
        **{"Inventory Location": None, "Default Location": None, "Unit Cost": None},
    )
    missing_sku = seed_item(client, sku="REMOVE-SKU")
    duplicate_one = seed_item(client, sku="DUPLICATE-ONE")
    duplicate_two = seed_item(client, sku="DUPLICATE-TWO")
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        location = db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == unlocated["id"]))
        db.delete(location)
        db.get(InventoryItem, missing_sku["id"]).sku = None
        db.get(InventoryItem, duplicate_one["id"]).sku = "Duplicate"
        db.get(InventoryItem, duplicate_two["id"]).sku = " duplicate "
        db.get(InventoryItem, valued["id"]).woo_name = "Concise Woo title"
        db.commit()
    finally:
        db_override.close()

    response = client.get("/api/reports/inventory-valuation/summary")

    assert response.status_code == 200
    summary = response.json()
    assert summary["inventory_record_count"] == 6
    assert summary["unique_sku_count"] == 4
    assert summary["total_skus"] == summary["reported_sku_count"] == 3
    assert summary["valued_sku_count"] == 2
    assert summary["missing_sku_count"] == 1
    assert summary["duplicate_sku_record_count"] == 1
    assert summary["missing_location_count"] == 1
    assert summary["missing_cost_count"] == 2
    assert summary["reported_missing_cost_count"] == 1
    assert summary["excluded_record_count"] == 1
    assert summary["location_filter_exclusion_count"] == 0
    assert {entry["reason"] for entry in summary["exclusion_summary"]} == {"missing_location", "missing_cost", "missing_sku", "duplicate_sku"}
    rows = client.get("/api/reports/inventory-valuation").json()
    assert next(row for row in rows if row["sku"] == "VALUE-1")["description"] == "Concise Woo title"


def test_inventory_valuation_summary_counts_location_filter_exclusions(client):
    seed_item(client, sku="MAIN-ITEM", Warehouse="Main Warehouse")
    seed_item(client, sku="SECONDARY-ITEM", Warehouse="Secondary Warehouse")

    summary = client.get("/api/reports/inventory-valuation/summary", params={"warehouse": "Main Warehouse"}).json()

    assert summary["inventory_record_count"] == 2
    assert summary["reported_sku_count"] == 1
    assert summary["excluded_record_count"] == 1
    assert summary["missing_location_count"] == 0
    assert summary["location_filter_exclusion_count"] == 1
    assert any(entry["reason"] == "location_filter" for entry in summary["exclusion_summary"])


def test_inventory_valuation_preserves_missing_cost_instead_of_false_zero(client):
    seed_item(client, sku="NULL-COST", **{"Unit Cost": None, "In Stock": 3, "Sales Price": 8})
    seed_item(client, sku="ZERO-COST", **{"Unit Cost": 0, "In Stock": 3, "Sales Price": 8})

    rows = client.get("/api/reports/inventory-valuation").json()
    null_cost = next(row for row in rows if row["sku"] == "NULL-COST")
    zero_cost = next(row for row in rows if row["sku"] == "ZERO-COST")

    assert null_cost["unit_cost"] is None
    assert null_cost["inventory_value"] is None
    assert null_cost["margin_estimate"] is None
    assert zero_cost["unit_cost"] == 0
    assert zero_cost["inventory_value"] == 0
    assert zero_cost["margin_estimate"] == 8

    summary = client.get("/api/reports/inventory-valuation/summary").json()
    assert summary["missing_cost_count"] == 1
    assert summary["valued_sku_count"] == 1
    assert summary["total_inventory_value"] == 0


def test_inventory_valuation_preserves_missing_sales_price_instead_of_false_zero(client):
    seed_item(client, sku="NULL-PRICE", **{"Unit Cost": 2, "In Stock": 3, "Sales Price": None})

    rows = client.get("/api/reports/inventory-valuation").json()
    null_price = next(row for row in rows if row["sku"] == "NULL-PRICE")

    assert null_price["sales_price"] is None
    assert null_price["retail_value"] is None
    assert null_price["margin_estimate"] is None
    assert client.get("/api/reports/inventory-valuation/summary").json()["total_retail_value"] is None

    seed_item(client, sku="ZERO-PRICE", **{"Unit Cost": 2, "In Stock": 3, "Sales Price": 0})
    zero_price = next(row for row in client.get("/api/reports/inventory-valuation").json() if row["sku"] == "ZERO-PRICE")

    assert zero_price["sales_price"] == 0
    assert zero_price["retail_value"] == 0
    assert zero_price["margin_estimate"] == -2
    assert client.get("/api/reports/inventory-valuation/summary").json()["total_retail_value"] == 0


def test_inventory_valuation_requires_an_active_populated_location(client):
    usable = seed_item(client, sku="USABLE-LOCATION")
    inactive = seed_item(client, sku="INACTIVE-LOCATION")
    blank = seed_item(client, sku="BLANK-LOCATION")
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == inactive["id"])).active = False
        blank_location = db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == blank["id"]))
        blank_location.warehouse = " "
        blank_location.inventory_location = " "
        db.commit()
    finally:
        db_override.close()

    rows = client.get("/api/reports/inventory-valuation").json()
    summary = client.get("/api/reports/inventory-valuation/summary").json()

    assert [row["sku"] for row in rows] == [usable["SKU"]]
    assert summary["inventory_record_count"] == 3
    assert summary["reported_sku_count"] == 1
    assert summary["missing_location_count"] == 2
    assert summary["excluded_record_count"] == 2


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
