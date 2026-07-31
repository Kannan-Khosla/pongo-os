import csv
from io import StringIO

from app.services.item_enrichment import ENRICHMENT_COLUMNS
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import seed_location


def mapped_item(client, sku, product_id, variation_id=None, **overrides):
    return seed_item(
        client,
        sku=sku,
        wooProductId=product_id,
        wooVariationId=variation_id,
        wooProductType="variation" if variation_id else "simple",
        wooSyncStatus="synced",
        **{"In Stock": 0, "Allocated": 0, "On Order": 0, **overrides},
    )


def exported_rows(client):
    response = client.get("/api/items/enrichment/export")
    assert response.status_code == 200, response.text
    return response.text, list(csv.DictReader(StringIO(response.text)))


def rows_csv(rows):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=ENRICHMENT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def upload(client, endpoint, text, *, opening=False, name="enrichment.csv"):
    return client.post(endpoint, files={"file": (name, text, "text/csv")}, data={"import_opening_stock": str(opening).lower()})


def test_enrichment_export_round_trip_preserves_identity_and_has_no_expiry(client):
    mapped_item(client, "ENRICH-1", 1001, Barcode="KEEP-BAR", Brand="Keep Brand", **{"Unit Cost": 4.5})
    text, rows = exported_rows(client)

    assert text.splitlines()[0].split(",")[:5] == ENRICHMENT_COLUMNS[:5]
    assert "Expiry" not in text.splitlines()[0]
    preview = upload(client, "/api/items/enrichment/preview", text)

    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_rows"] == 1
    assert preview.json()["unchanged_count"] == 1
    assert rows[0]["Woo Product ID"] == "1001"


def test_enrichment_updates_three_variations_independently_and_preserves_empty_values(client):
    for index, variation_id in enumerate([2001, 2002, 2003], start=1):
        mapped_item(client, f"VAR-{index}", 2000, variation_id, Barcode=f"OLD-{index}", Brand="Preserve Brand", **{"Unit Cost": index})
    _, rows = exported_rows(client)
    for index, row in enumerate(rows, start=1):
        row["Barcode"] = f"NEW-{index}"
        row["Unit Cost"] = str(index * 10)
        row["Brand"] = "" if index == 1 else ("__CLEAR__" if index == 2 else "Variation Brand")
    csv_text = rows_csv(rows)

    preview = upload(client, "/api/items/enrichment/preview", csv_text).json()
    commit = upload(client, "/api/items/enrichment/commit", csv_text)

    assert preview["matched_by_pongo_item_id"] == 3
    assert preview["update_count"] == 3
    assert commit.status_code == 200, commit.text
    assert commit.json()["updated_count"] == 3
    items = {item["SKU"]: item for item in client.get("/api/items").json()["items"]}
    assert [items[f"VAR-{index}"]["Barcode"] for index in range(1, 4)] == ["NEW-1", "NEW-2", "NEW-3"]
    assert [items[f"VAR-{index}"]["Unit Cost"] for index in range(1, 4)] == [10, 20, 30]
    assert items["VAR-1"]["Brand"] == "Preserve Brand"
    assert items["VAR-2"]["Brand"] is None
    assert items["VAR-3"]["Brand"] == "Variation Brand"
    assert [items[f"VAR-{index}"]["wooVariationId"] for index in range(1, 4)] == [2001, 2002, 2003]


def test_enrichment_matching_fallbacks_and_protected_conflicts(client):
    mapped_item(client, "SKU-FALLBACK", 3001, Barcode="BAR-FALLBACK", Brand="Before")
    _, rows = exported_rows(client)
    sku_row = dict(rows[0])
    sku_row["Pongo Item ID"] = ""
    sku_row["Woo Product ID"] = ""
    sku_row["Brand"] = "By SKU"
    sku_preview = upload(client, "/api/items/enrichment/preview", rows_csv([sku_row])).json()
    assert sku_preview["matched_by_sku"] == 1

    barcode_row = dict(sku_row)
    barcode_row["SKU"] = ""
    barcode_row["Manufacturer"] = "By Barcode"
    barcode_preview = upload(client, "/api/items/enrichment/preview", rows_csv([barcode_row])).json()
    assert barcode_preview["matched_by_barcode"] == 1

    conflict_row = dict(rows[0])
    conflict_row["Woo Product ID"] = "999999"
    conflict = upload(client, "/api/items/enrichment/preview", rows_csv([conflict_row])).json()
    assert conflict["conflict_count"] == 1
    assert "WooCommerce identifiers" in " ".join(error["error_message"] for error in conflict["errors"])


def test_opening_stock_is_location_level_audited_and_idempotent(client):
    seed_location(client, code="OPENING", name="Opening Location", warehouse="Main Warehouse", isDefault=True)
    mapped_item(client, "OPENING-SKU", 4001, Warehouse="Main Warehouse", **{"Inventory Location": "OPENING", "Default Location": "OPENING"})
    _, rows = exported_rows(client)
    rows[0]["In Stock"] = "8"
    csv_text = rows_csv(rows)

    preview = upload(client, "/api/items/enrichment/preview", csv_text, opening=True)
    before = client.get("/api/items", params={"sku": "OPENING-SKU"}).json()["items"][0]
    commit = upload(client, "/api/items/enrichment/commit", csv_text, opening=True)
    duplicate = upload(client, "/api/items/enrichment/commit", csv_text, opening=True)

    assert preview.status_code == 200, preview.text
    assert before["In Stock"] == 0
    assert commit.status_code == 200, commit.text
    assert duplicate.status_code == 409
    item = client.get("/api/items", params={"sku": "OPENING-SKU"}).json()["items"][0]
    location = client.get("/api/inventory/locations", params={"item_id": item["id"]}).json()["rows"][0]
    movements = client.get("/api/stock-movements", params={"movement_type": "opening_balance_import"}).json()
    assert item["In Stock"] == 8
    assert item["Allocated"] == 0
    assert item["Sellable"] == 8
    assert location["in_stock"] == 8
    assert movements["total"] == 1
    assert movements["movements"][0]["quantity_delta"] == 8


def test_opening_stock_rejects_invalid_location_negative_and_history(client):
    mapped_item(client, "BAD-OPENING", 5001, Warehouse="Missing", **{"Inventory Location": "Nowhere", "Default Location": "Nowhere"})
    _, rows = exported_rows(client)
    rows[0]["In Stock"] = "-1"
    negative = upload(client, "/api/items/enrichment/preview", rows_csv(rows), opening=True).json()
    rows[0]["In Stock"] = "3"
    invalid_location = upload(client, "/api/items/enrichment/preview", rows_csv(rows), opening=True).json()

    assert negative["conflict_count"] == 1
    assert "negative" in str(negative["errors"]).lower()
    assert invalid_location["conflict_count"] == 1
    assert "warehouse/location" in str(invalid_location["errors"])


def test_enrichment_failed_rows_are_recorded_and_downloadable(client):
    mapped_item(client, "FAILED-ROW", 6001)
    _, rows = exported_rows(client)
    rows[0]["Woo Mapping Type"] = "variation"
    response = upload(client, "/api/items/enrichment/commit", rows_csv(rows))

    assert response.status_code == 200
    body = response.json()
    assert body["failed_count"] == 1
    failed = client.get(f"/api/import-jobs/{body['import_job_id']}/failed-rows")
    assert failed.status_code == 200
    assert failed.text.splitlines()[0].startswith("Pongo Item ID,Woo Product ID,Woo Variation ID")
    assert "Woo Mapping Type" in failed.text
