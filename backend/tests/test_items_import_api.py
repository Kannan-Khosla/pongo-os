import csv
from io import StringIO

from app.services.items import CANONICAL_ITEM_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401


def csv_text(rows, header=None):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header or CANONICAL_ITEM_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def upload_csv(client, endpoint, text, filename="items.csv"):
    return client.post(endpoint, files={"file": (filename, text, "text/csv")})


def base_row(sku="IMPORT-001", barcode="IMPORT001", **overrides):
    row = {
        "Client": "Pongo",
        "SKU": sku,
        "Description": "Import Test Item",
        "Category": "Import Category",
        "Unit of Measurement": "Each",
        "Warehouse": "Main Warehouse",
        "Inventory Location": "Import Rack",
        "Default Location": "Import Rack",
        "In Stock": "10",
        "Allocated": "2",
        "Sellable": "999",
        "Under Par": "yes",
        "On Order": "0",
        "Barcode": barcode,
        "Manufacturer": "Import Maker",
        "Manufacturer Website": "https://example.invalid/import",
        "Recommended Retail Price": "12.99",
        "Sales Price": "10.99",
        "Unit Cost": "4.25",
        "Weight": "1",
        "Default Econ Order": "6",
        "Default Lead Time Days": "5",
        "Par Level": "8",
        "Assembly": "N",
        "Serializable": "0",
        "Track Lot": "Y",
        "Perishable": "false",
        "Re-Order": "true",
        "Storage Length": "2",
        "Storage Width": "3",
        "Storage Height": "4",
        "Storage Volume": "999",
        "Brand": "Import Brand",
    }
    row.update(overrides)
    return row


def test_preview_accepts_valid_canonical_csv(client):
    response = upload_csv(client, "/api/items/import/preview", csv_text([base_row()]))

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 1
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 0
    assert body["create_count"] == 1
    assert body["preview_rows"][0]["row"]["Sellable"] == 8


def test_preview_accepts_legacy_product_header_without_manufacturer(client):
    header = [
        "Client",
        "SKU",
        "Description",
        "Category",
        "Unit of Measurement",
        "Warehouse",
        "Inventory Location",
        "Default Location",
        "In Stock",
        "Allocated",
        "Sellable",
        "Under Par",
        "On Order",
        "Barcode",
        "Manufacturer Website",
        "Recommended Retail Price",
        "Sales Price",
        "Unit Cost",
        "Weight",
        "Default Econ Order",
        "Default Lead Time (Days)",
        "Par Level",
        "Assembly",
        "Serializable",
        "Track Lot",
        "Perishable",
        "Re-Order",
        "Storage Length",
        "Storage Width",
        "Storage Height",
        "Storage Volume",
        "Brand",
    ]
    row = base_row()
    row["Default Lead Time (Days)"] = row.pop("Default Lead Time Days")

    response = upload_csv(client, "/api/items/import/preview", csv_text([row], header=header))

    assert response.status_code == 200
    body = response.json()
    assert body["valid_rows"] == 1
    assert body["preview_rows"][0]["row"]["Manufacturer"] == ""
    assert body["preview_rows"][0]["row"]["Default Lead Time Days"] == 5


def test_preview_accepts_tab_delimited_product_export(client):
    header = [column for column in CANONICAL_ITEM_COLUMNS if column != "Manufacturer"]
    header[header.index("Default Lead Time Days")] = "Default Lead Time (Days)"
    row = base_row()
    row["Default Lead Time (Days)"] = row.pop("Default Lead Time Days")
    text = "\t".join(header) + "\n" + "\t".join(str(row.get(column, "")) for column in header) + "\n"

    response = upload_csv(client, "/api/items/import/preview", text, filename="items.tsv")

    assert response.status_code == 200
    assert response.json()["valid_rows"] == 1


def test_preview_rejects_missing_required_header(client):
    header = [column for column in CANONICAL_ITEM_COLUMNS if column != "SKU"]

    response = upload_csv(client, "/api/items/import/preview", csv_text([base_row()], header=header))

    assert response.status_code == 400
    assert "SKU" in response.text


def test_preview_reports_extra_columns_as_warnings(client):
    header = [*CANONICAL_ITEM_COLUMNS, "Extra Column"]
    row = {**base_row(), "Extra Column": "ignored"}

    response = upload_csv(client, "/api/items/import/preview", csv_text([row], header=header))

    assert response.status_code == 200
    assert "Extra column ignored: Extra Column" in response.json()["warnings"]


def test_commit_creates_new_items(client):
    response = upload_csv(client, "/api/items/import/commit", csv_text([base_row()]))

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 1
    list_response = client.get("/api/items", params={"search": "IMPORT-001"})
    assert list_response.json()["items"][0]["SKU"] == "IMPORT-001"


def test_commit_updates_existing_items_by_sku(client):
    seed_item(client, sku="IMPORT-UPDATE", Description="Old")

    response = upload_csv(client, "/api/items/import/commit", csv_text([base_row(sku="IMPORT-UPDATE", Description="Updated")]))

    assert response.status_code == 200
    assert response.json()["updated_count"] == 1
    item = client.get("/api/items", params={"search": "IMPORT-UPDATE"}).json()["items"][0]
    assert item["Description"] == "Updated"


def test_commit_updates_existing_items_by_barcode_when_sku_does_not_match(client):
    seed_item(client, sku="OLD-SKU", Barcode="SHARED-BARCODE")

    response = upload_csv(client, "/api/items/import/commit", csv_text([base_row(sku="NEW-SKU", barcode="SHARED-BARCODE")]))

    assert response.status_code == 200
    assert response.json()["updated_count"] == 1
    item = client.get("/api/items", params={"search": "NEW-SKU"}).json()["items"][0]
    assert item["SKU"] == "NEW-SKU"
    assert item["Barcode"] == "SHARED-BARCODE"


def test_conflict_when_sku_and_barcode_match_different_items(client):
    seed_item(client, sku="SKU-ITEM", Barcode="BAR-1")
    seed_item(client, sku="OTHER-ITEM", Barcode="BAR-2")

    response = upload_csv(client, "/api/items/import/preview", csv_text([base_row(sku="SKU-ITEM", barcode="BAR-2")]))

    assert response.status_code == 200
    body = response.json()
    assert body["invalid_rows"] == 1
    assert "different existing items" in body["errors"][0]["error_message"]


def test_calculated_fields_override_imported_values(client):
    response = upload_csv(client, "/api/items/import/preview", csv_text([base_row(**{"In Stock": "3", "Allocated": "2", "Par Level": "3", "Sellable": "100", "Under Par": "no", "Storage Volume": "100"})]))

    assert response.status_code == 200
    row = response.json()["preview_rows"][0]["row"]
    assert row["Sellable"] == 1
    assert row["Under Par"] is True
    assert row["Storage Volume"] == 24
    assert response.json()["warnings"]


def test_failed_rows_are_recorded_and_downloadable(client):
    response = upload_csv(client, "/api/items/import/commit", csv_text([base_row(sku="")]))

    assert response.status_code == 200
    body = response.json()
    assert body["failed_count"] == 1
    job_id = body["import_job_id"]
    detail = client.get(f"/api/import-jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["errors"][0]["error_message"] == "SKU is required for item import."

    failed_rows = client.get(f"/api/import-jobs/{job_id}/failed-rows")
    assert failed_rows.status_code == 200
    assert "Error Message" in failed_rows.text.splitlines()[0]


def test_exported_csv_can_be_imported_again(client):
    seed_item(client, sku="ROUNDTRIP-001", Barcode="ROUNDTRIP-BAR")
    exported = client.get("/api/items/export", params={"search": "ROUNDTRIP-001"})

    response = upload_csv(client, "/api/items/import/preview", exported.text)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_rows"] == 1
    assert body["update_count"] == 1
