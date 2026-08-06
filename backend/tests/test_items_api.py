import csv
from io import StringIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.models import Base
from app.models.inventory import InventoryAuditEvent, InventoryItem, InventoryItemLocation
from app.services.items import CANONICAL_ITEM_COLUMNS


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        registration = test_client.post(
            "/api/auth/register",
            json={"email": "pytest@example.com", "display_name": "Pytest", "password": "correct-horse-battery-staple"},
        )
        assert registration.status_code == 201, registration.text
        yield test_client
    app.dependency_overrides.clear()


def seed_item(client, sku="API-001", **overrides):
    payload = {
        "Client": "Pongo",
        "SKU": sku,
        "Description": "API Test Item",
        "Category": "Dog Food",
        "Unit of Measurement": "Each",
        "Warehouse": "Main Warehouse",
        "Inventory Location": "Rack 1",
        "Default Location": "Rack 1",
        "In Stock": 10,
        "Allocated": 3,
        "On Order": 2,
        "Barcode": f"{sku}-BAR",
        "Manufacturer": "Test Maker",
        "Manufacturer Website": "https://example.invalid/maker",
        "Recommended Retail Price": 12.99,
        "Sales Price": 10.99,
        "Unit Cost": 4.25,
        "Weight": 2,
        "Default Econ Order": 6,
        "Default Lead Time Days": 5,
        "Par Level": 8,
        "Assembly": False,
        "Serializable": False,
        "Track Lot": True,
        "Perishable": False,
        "Re-Order": True,
        "Storage Length": 2,
        "Storage Width": 3,
        "Storage Height": 4,
        "Brand": "Test Brand",
        "active": True,
        "nonInventory": False,
    }
    payload.update(overrides)
    opening_stock = payload.pop("In Stock", 0)
    opening_allocated = payload.pop("Allocated", 0)
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    item = response.json()
    if opening_stock or opening_allocated:
        opening = client.post(
            f"/api/items/{item['id']}/opening-balance",
            json={
                "In Stock": opening_stock,
                "Allocated": opening_allocated,
                "Warehouse": payload.get("Warehouse") or "UNASSIGNED",
                "Inventory Location": payload.get("Inventory Location") or payload.get("Default Location") or "UNASSIGNED",
                "idempotencyKey": f"test-{uuid4()}",
                "createdBy": "pytest",
            },
        )
        assert opening.status_code == 200, opening.text
        item = client.get(f"/api/items/{item['id']}").json()
    return item


def test_create_item_calculates_fields(client):
    item = seed_item(client)

    assert item["SKU"] == "API-001"
    assert item["Sellable"] == 7
    assert item["Under Par"] is False
    assert item["Storage Volume"] == 24


def test_list_items_filters(client):
    seed_item(client, sku="DOG-001", Category="Dog Food", Brand="North Paw")
    seed_item(client, sku="CAT-001", Category="Cats", Brand="South Paw")

    response = client.get("/api/items", params={"search": "dog", "category": "Dog Food", "brand": "North Paw"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 1
    assert body["total_pages"] == 1
    assert body["returned_count"] == 1
    assert body["items"][0]["SKU"] == "DOG-001"


def test_item_search_and_product_title_sort_use_concise_woo_name(client):
    first = seed_item(client, sku="TITLE-1", Description="Long marketing copy one")
    second = seed_item(client, sku="TITLE-2", Description="Long marketing copy two")
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        db.get(InventoryItem, first["id"]).woo_name = "Alpha concise title"
        db.get(InventoryItem, second["id"]).woo_name = "Zulu concise title"
        db.commit()
    finally:
        db_override.close()

    searched = client.get("/api/items", params={"search": "zulu concise", "page": 1, "page_size": 20}).json()
    assert [item["SKU"] for item in searched["items"]] == ["TITLE-2"]

    sorted_rows = client.get(
        "/api/items",
        params={"sort_by": "description", "sort_direction": "desc", "page": 1, "page_size": 20},
    ).json()
    assert [item["SKU"] for item in sorted_rows["items"][:2]] == ["TITLE-2", "TITLE-1"]


def test_keyword_search_matches_partial_skus_and_words_across_item_fields(client):
    seed_item(client, sku="70001", Description="Duck Food Adult", Brand="North Paw")
    seed_item(client, sku="70002", Description="Duck Food Puppy", Brand="South Paw")
    seed_item(client, sku="90001", Description="Chicken Food Adult", Brand="North Paw")
    seed_item(client, sku="10000", Barcode="ABC700XYZ", Description="Unrelated barcode match")

    sku_suggestions = client.get("/api/items/search", params={"q": "700"}).json()["items"]
    assert [(item["sku"], item["product_name"]) for item in sku_suggestions[:2]] == [
        ("70001", "Duck Food Adult"),
        ("70002", "Duck Food Puppy"),
    ]

    keyword_suggestions = client.get("/api/items/search", params={"q": "duck north"}).json()["items"]
    assert [item["sku"] for item in keyword_suggestions] == ["70001"]

    catalog_results = client.get("/api/items", params={"search": "duck south"}).json()["items"]
    assert [item["SKU"] for item in catalog_results] == ["70002"]


def test_list_items_supports_server_pagination_and_sorting(client):
    for index in range(21):
        seed_item(client, sku=f"PAGE-{index:02d}")

    legacy = client.get("/api/items").json()
    assert legacy["total"] == 21
    assert legacy["page_size"] == 21
    assert legacy["returned_count"] == 21
    assert legacy["total_pages"] == 1

    first = client.get(
        "/api/items",
        params={"page": 1, "page_size": 20, "sort_by": "sku", "sort_direction": "desc"},
    )

    assert first.status_code == 200
    body = first.json()
    assert body["total"] == 21
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_pages"] == 2
    assert body["returned_count"] == 20
    assert body["has_previous"] is False
    assert body["has_next"] is True
    assert [item["SKU"] for item in body["items"][:2]] == ["PAGE-20", "PAGE-19"]

    second = client.get(
        "/api/items",
        params={"page": 2, "page_size": 20, "sort_by": "sku", "sort_direction": "desc"},
    ).json()
    assert second["returned_count"] == 1
    assert second["has_previous"] is True
    assert second["has_next"] is False
    assert [item["SKU"] for item in second["items"]] == ["PAGE-00"]


def test_list_items_pagination_metadata_tracks_filtered_total(client):
    seed_item(client, sku="FILTER-A", Brand="Included")
    seed_item(client, sku="FILTER-B", Brand="Included")
    seed_item(client, sku="FILTER-C", Brand="Excluded")

    body = client.get("/api/items", params={"brand": "Included", "page": 1, "page_size": 1}).json()

    assert body["total"] == 2
    assert body["total_pages"] == 2
    assert body["returned_count"] == 1


def test_list_items_stock_status_filters_remain_server_paginated(client):
    seed_item(client, sku="STOCK-IN", **{"In Stock": 10, "Allocated": 0, "Par Level": 5})
    seed_item(client, sku="STOCK-OUT", **{"In Stock": 0, "Allocated": 0, "Par Level": 0})
    seed_item(client, sku="STOCK-LOW", **{"In Stock": 2, "Allocated": 0, "Par Level": 5})

    in_stock = client.get("/api/items", params={"stock_status": "in_stock", "page": 1, "page_size": 1}).json()
    assert in_stock["total"] == 2
    assert in_stock["returned_count"] == 1

    out_of_stock = client.get("/api/items", params={"stock_status": "out_of_stock", "page": 1, "page_size": 20}).json()
    assert [item["SKU"] for item in out_of_stock["items"]] == ["STOCK-OUT"]

    under_par = client.get("/api/items", params={"stock_status": "under_par", "page": 1, "page_size": 20}).json()
    assert [item["SKU"] for item in under_par["items"]] == ["STOCK-LOW", "STOCK-OUT"]


def test_list_items_facets_cover_the_full_catalog_and_preserve_raw_values(client):
    seed_item(client, sku="FACET-1", Category="Dogs", Brand="Alpha")
    seed_item(client, sku="FACET-2", Category="Dog &amp; Cat", Brand="Zeta &amp; Co")

    body = client.get("/api/items", params={"page": 1, "page_size": 1}).json()

    assert body["returned_count"] == 1
    assert body["facets"]["categories"] == ["Dog &amp; Cat", "Dogs"]
    assert body["facets"]["brands"] == ["Alpha", "Zeta &amp; Co"]

    filtered = client.get("/api/items", params={"category": "Dog &amp; Cat", "page": 1, "page_size": 20}).json()
    assert [item["SKU"] for item in filtered["items"]] == ["FACET-2"]


def test_list_items_pagination_handles_empty_and_out_of_range_pages(client):
    seed_item(client, sku="ONLY-ITEM")

    empty = client.get("/api/items", params={"search": "does-not-exist", "page": 1, "page_size": 20}).json()
    assert empty["total"] == 0
    assert empty["total_pages"] == 0
    assert empty["returned_count"] == 0
    assert empty["items"] == []

    out_of_range = client.get("/api/items", params={"page": 2, "page_size": 20}).json()
    assert out_of_range["total"] == 1
    assert out_of_range["total_pages"] == 1
    assert out_of_range["page"] == 1
    assert out_of_range["returned_count"] == 1
    assert out_of_range["has_previous"] is False
    assert out_of_range["has_next"] is False

    assert client.get("/api/items", params={"page": 0}).status_code == 422
    assert client.get("/api/items", params={"page_size": 101}).status_code == 422
    assert client.get("/api/items", params={"sort_by": "unknown"}).status_code == 422
    assert client.get("/api/items", params={"sort_direction": "sideways"}).status_code == 422


def test_list_items_supports_data_quality_filters(client):
    common = {"wooProductId": 100}
    seed_item(client, sku="COMPLETE", **common)
    seed_item(client, sku="MISSING-BARCODE", Barcode=None, **common)
    seed_item(client, sku="MISSING-BRAND", Brand=None, **common)
    seed_item(client, sku="MISSING-COST", **{"Unit Cost": None, **common})
    seed_item(client, sku="UNMAPPED")
    seed_item(client, sku="RECEIVING", **{"Inventory Location": "RECEIVING", "Default Location": "RECEIVING", **common})
    unlocated = seed_item(client, sku="MISSING-LOCATION", **common)

    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        location = db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == unlocated["id"]))
        db.delete(location)
        db.commit()
    finally:
        db_override.close()

    def filtered_skus(data_quality):
        response = client.get("/api/items", params={"data_quality": data_quality, "page": 1, "page_size": 20})
        assert response.status_code == 200
        return response.json(), {item["SKU"] for item in response.json()["items"]}

    missing_barcode, barcode_skus = filtered_skus("missing_barcode")
    assert barcode_skus == {"MISSING-BARCODE"}
    assert missing_barcode["total"] == 1
    assert filtered_skus("missing_brand")[1] == {"MISSING-BRAND"}
    assert filtered_skus("missing_cost")[1] == {"MISSING-COST"}
    assert filtered_skus("unmapped")[1] == {"UNMAPPED"}
    assert filtered_skus("receiving")[1] == {"RECEIVING"}
    assert filtered_skus("missing_location")[1] == {"MISSING-LOCATION"}
    assert filtered_skus("missing_barcode,missing_brand")[1] == {"MISSING-BARCODE", "MISSING-BRAND"}
    assert client.get("/api/items", params={"data_quality": "unknown"}).status_code == 422


def test_receiving_quality_filter_ignores_inactive_historical_locations(client):
    item = seed_item(client, sku="OLD-RECEIVING")
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        location = db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == item["id"]))
        location.inventory_location = "RECEIVING"
        location.active = False
        db.commit()
    finally:
        db_override.close()

    body = client.get("/api/items", params={"data_quality": "receiving"}).json()
    assert body["items"] == []


def test_get_item(client):
    created = seed_item(client)

    response = client.get(f"/api/items/{created['id']}")

    assert response.status_code == 200
    assert response.json()["SKU"] == "API-001"


def test_update_item_blocks_direct_stock_mutation(client):
    created = seed_item(client)

    response = client.patch(f"/api/items/{created['id']}", json={"In Stock": 5, "Allocated": 2, "Par Level": 5})

    assert response.status_code == 422
    item = client.get(f"/api/items/{created['id']}").json()
    assert item["In Stock"] == 10
    assert item["Allocated"] == 3


def test_opening_balance_is_explicit_audited_and_idempotent(client):
    created = client.post("/api/items", json={"SKU": "OPENING-API", "Warehouse": "Main Warehouse", "Inventory Location": "Rack 1"}).json()
    payload = {
        "In Stock": 5,
        "Allocated": 2,
        "Warehouse": "Main Warehouse",
        "Inventory Location": "Rack 1",
        "idempotencyKey": "opening-api-1",
        "createdBy": "pytest",
    }

    first = client.post(f"/api/items/{created['id']}/opening-balance", json=payload)
    replay = client.post(f"/api/items/{created['id']}/opening-balance", json=payload)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert client.get("/api/stock-movements", params={"item_id": created["id"], "movement_type": "opening_balance_import"}).json()["total"] == 1
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        audit = db.scalar(select(InventoryAuditEvent).where(InventoryAuditEvent.item_id == created["id"]))
        assert audit.previous_allocated == 0
        assert audit.new_allocated == 2
        assert audit.previous_sellable == 0
        assert audit.new_sellable == 3
        assert audit.created_by == "pytest@example.com"
    finally:
        db_override.close()


def test_metadata_update_preserves_multi_location_stock_and_movement_history(client):
    created = seed_item(client, sku="MULTI-METADATA", **{"In Stock": 10, "Allocated": 3})
    second = client.post(
        "/api/locations",
        json={"warehouse": "Main Warehouse", "code": "RACK-2", "name": "Rack 2", "isActive": True},
    ).json()
    source = client.get("/api/inventory/locations", params={"item_id": created["id"]}).json()["rows"][0]
    transfer = client.post(
        "/api/inventory/transfers",
        json={
            "idempotency_key": "multi-metadata-transfer",
            "lines": [{
                "item_id": created["id"],
                "from_inventory_item_location_id": source["id"],
                "to_warehouse": second["warehouse"],
                "to_inventory_location": second["name"],
                "quantity": 2,
            }],
        },
    )
    assert transfer.status_code == 201, transfer.text
    before_rows = client.get("/api/inventory/locations", params={"item_id": created["id"]}).json()["rows"]
    before = {(row["id"], row["in_stock"], row["allocated"]) for row in before_rows}
    movement_count = client.get("/api/stock-movements", params={"item_id": created["id"]}).json()["total"]

    updated = client.patch(f"/api/items/{created['id']}", json={"Description": "Metadata only"})

    assert updated.status_code == 200, updated.text
    after_rows = client.get("/api/inventory/locations", params={"item_id": created["id"]}).json()["rows"]
    assert {(row["id"], row["in_stock"], row["allocated"]) for row in after_rows} == before
    assert updated.json()["In Stock"] == 10
    assert updated.json()["Allocated"] == 3
    assert client.get("/api/stock-movements", params={"item_id": created["id"]}).json()["total"] == movement_count


def test_create_item_rejects_embedded_stock_quantities(client):
    response = client.post("/api/items", json={"SKU": "NO-HIDDEN-STOCK", "In Stock": 3})

    assert response.status_code == 422


def test_include_non_inventory_filter(client):
    seed_item(client, sku="STOCK-001", nonInventory=False)
    seed_item(client, sku="SERVICE-001", nonInventory=True)

    response = client.get("/api/items", params={"include_non_inventory": False})

    assert response.status_code == 200
    skus = [item["SKU"] for item in response.json()["items"]]
    assert skus == ["STOCK-001"]


def test_csv_export_header_order(client):
    seed_item(client, sku="EXPORT-001")

    response = client.get("/api/items/export")

    assert response.status_code == 200
    header = response.text.splitlines()[0].split(",")
    assert header == CANONICAL_ITEM_COLUMNS


def test_csv_export_filtered_rows(client):
    seed_item(client, sku="EXPORT-DOG", Brand="Export Dog")
    seed_item(client, sku="EXPORT-CAT", Brand="Export Cat")

    response = client.get("/api/items/export", params={"brand": "Export Dog"})

    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["SKU"] == "EXPORT-DOG"
