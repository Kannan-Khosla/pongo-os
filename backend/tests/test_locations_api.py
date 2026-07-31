import csv
from io import StringIO
from pathlib import Path

from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryItemLocation, InventoryLocation
from app.services.locations import CANONICAL_LOCATION_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401


def location_payload(code="LOC-001", **overrides):
    payload = {
        "warehouse": "Main Warehouse",
        "code": code,
        "name": "Test Location",
        "description": "API test location",
        "zone": "Dry Storage",
        "aisle": "A",
        "rack": "01",
        "shelf": "02",
        "bin": "03",
        "isDefault": False,
        "isActive": True,
    }
    payload.update(overrides)
    return payload


def seed_location(client, code="LOC-001", **overrides):
    payload = location_payload(code=code, **overrides)
    response = client.post("/api/locations", json=payload)
    if response.status_code == 409:
        rows = client.get("/api/locations", params={"search": code}).json()["locations"]
        existing = next(row for row in rows if row["code"] == code and row["warehouse"] == payload["warehouse"])
        response = client.patch(f"/api/locations/{existing['id']}", json=payload)
    assert response.status_code in {200, 201}, response.text
    return response.json()


def force_location_active_for_legacy_test(location_id, active):
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        db.get(InventoryLocation, location_id).active = active
        db.commit()
    finally:
        db_override.close()


def csv_text(rows, header=None):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header or CANONICAL_LOCATION_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def upload_csv(client, endpoint, text, filename="locations.csv"):
    return client.post(endpoint, files={"file": (filename, text, "text/csv")})


def csv_row(code="IMP-001", **overrides):
    row = {
        "Warehouse": "Main Warehouse",
        "Location Code": code,
        "Location Name": "Import Location",
        "Description": "Imported location",
        "Zone": "Dry Storage",
        "Aisle": "A",
        "Rack": "01",
        "Shelf": "02",
        "Bin": "03",
        "Default": "No",
        "Active": "Yes",
    }
    row.update(overrides)
    return row


def test_create_location(client):
    location = seed_location(client)

    assert location["warehouse"] == "Main Warehouse"
    assert location["code"] == "LOC-001"
    assert location["isActive"] is True


def test_update_location(client):
    created = seed_location(client)

    response = client.patch(f"/api/locations/{created['id']}", json={"name": "Updated Location", "isDefault": True})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated Location"
    assert body["isDefault"] is True


def test_list_locations_filters(client):
    seed_location(client, code="A-001", zone="Dry Storage")
    seed_location(client, code="B-001", zone="Cold Storage")

    response = client.get("/api/locations", params={"search": "A-001", "zone": "Dry Storage"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["locations"][0]["code"] == "A-001"


def test_export_locations_csv(client):
    seed_location(client, code="EXPORT-001")

    response = client.get("/api/locations/export")

    assert response.status_code == 200
    header = response.text.splitlines()[0].split(",")
    assert header == CANONICAL_LOCATION_COLUMNS
    assert "EXPORT-001" in response.text


def test_preview_accepts_valid_location_csv(client):
    response = upload_csv(client, "/api/locations/import/preview", csv_text([csv_row()]))

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 1
    assert body["valid_rows"] == 1
    assert body["create_count"] == 1
    assert body["preview_rows"][0]["code"] == "IMP-001"


def test_preview_rejects_missing_required_header(client):
    header = [column for column in CANONICAL_LOCATION_COLUMNS if column != "Location Code"]

    response = upload_csv(client, "/api/locations/import/preview", csv_text([csv_row()], header=header))

    assert response.status_code == 400
    assert "Location Code" in response.text


def test_preview_reports_extra_columns_as_warnings(client):
    header = [*CANONICAL_LOCATION_COLUMNS, "Extra Column"]
    row = {**csv_row(), "Extra Column": "ignored"}

    response = upload_csv(client, "/api/locations/import/preview", csv_text([row], header=header))

    assert response.status_code == 200
    assert "Extra column ignored: Extra Column" in response.json()["warnings"]


def test_commit_creates_new_locations(client):
    response = upload_csv(client, "/api/locations/import/commit", csv_text([csv_row()]))

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 1
    assert client.get(f"/api/import-jobs/{body['import_job_id']}").json()["created_by"] == "pytest@example.com"
    list_response = client.get("/api/locations", params={"code": "IMP-001"})
    assert list_response.json()["locations"][0]["code"] == "IMP-001"


def test_commit_updates_existing_location_by_warehouse_and_code(client):
    seed_location(client, code="IMP-UPDATE", name="Old")

    response = upload_csv(client, "/api/locations/import/commit", csv_text([csv_row(code="IMP-UPDATE", **{"Location Name": "Updated"})]))

    assert response.status_code == 200
    assert response.json()["updated_count"] == 1
    location = client.get("/api/locations", params={"code": "IMP-UPDATE"}).json()["locations"][0]
    assert location["name"] == "Updated"


def test_invalid_rows_are_recorded_in_import_errors(client):
    response = upload_csv(client, "/api/locations/import/commit", csv_text([csv_row(**{"Warehouse": ""})]))

    assert response.status_code == 200
    body = response.json()
    assert body["failed_count"] == 1
    detail = client.get(f"/api/import-jobs/{body['import_job_id']}")
    assert detail.status_code == 200
    assert "Warehouse is required" in detail.json()["errors"][0]["error_message"]
    failed_rows = client.get(f"/api/import-jobs/{body['import_job_id']}/failed-rows")
    assert failed_rows.status_code == 200
    assert failed_rows.text.splitlines()[0].startswith("Warehouse,Location Code")


def test_inactive_location_is_handled(client):
    created = seed_location(client, code="INACTIVE-API")

    delete_response = client.delete(f"/api/locations/{created['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json()["isActive"] is False
    active_response = client.get("/api/locations", params={"active": True})
    assert "INACTIVE-API" not in [location["code"] for location in active_response.json()["locations"]]


def test_stocked_location_cannot_be_deactivated(client):
    item = seed_item(client, sku="LOCATION-GUARD", **{"Inventory Location": "GUARDED", "Default Location": "GUARDED", "In Stock": 4})
    location = next(row for row in client.get("/api/locations").json()["locations"] if row["name"] == "GUARDED")

    response = client.delete(f"/api/locations/{location['id']}")

    assert response.status_code == 409
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 4


def test_inactive_legacy_item_location_with_stock_still_blocks_deactivation(client):
    item = seed_item(client, sku="LOCATION-LEGACY-GUARD", **{"Inventory Location": "LEGACY-GUARDED", "Default Location": "LEGACY-GUARDED", "In Stock": 2, "Allocated": 0})
    location = next(row for row in client.get("/api/locations").json()["locations"] if row["name"] == "LEGACY-GUARDED")
    db = next(app.dependency_overrides[get_db]())
    try:
        row = db.query(InventoryItemLocation).filter(InventoryItemLocation.inventory_item_id == item["id"]).one()
        row.active = False
        db.commit()
    finally:
        db.close()

    assert client.delete(f"/api/locations/{location['id']}").status_code == 409


def test_location_sample_csv_can_be_previewed_and_committed(client):
    sample_path = Path(__file__).resolve().parents[2] / "docs" / "csv-reference" / "sample-locations-import.csv"
    sample_csv = sample_path.read_text()

    preview = upload_csv(client, "/api/locations/import/preview", sample_csv)
    commit = upload_csv(client, "/api/locations/import/commit", sample_csv)

    assert preview.status_code == 200
    assert preview.json()["valid_rows"] == 4
    assert commit.status_code == 200
    assert commit.json()["created_count"] == 4
