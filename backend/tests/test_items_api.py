import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.models import Base
from app.models.inventory import InventoryItem
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
    response = client.post("/api/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


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
    assert body["items"][0]["SKU"] == "DOG-001"


def test_get_item(client):
    created = seed_item(client)

    response = client.get(f"/api/items/{created['id']}")

    assert response.status_code == 200
    assert response.json()["SKU"] == "API-001"


def test_update_item_recalculates_fields(client):
    created = seed_item(client)

    response = client.patch(f"/api/items/{created['id']}", json={"In Stock": 5, "Allocated": 2, "Par Level": 5})

    assert response.status_code == 200
    item = response.json()
    assert item["Sellable"] == 3
    assert item["Under Par"] is True


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
