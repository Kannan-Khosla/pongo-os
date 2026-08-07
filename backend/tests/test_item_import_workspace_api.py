import tracemalloc
from io import BytesIO
from time import perf_counter
from uuid import uuid4

from sqlalchemy import event

from tests.test_items_api import client, seed_item  # noqa: F401


def upload(client, outcome: str, csv_text: str, filename: str = "items.csv"):
    return client.post(
        "/api/items/import/previews",
        data={"outcome": outcome},
        files={"file": (filename, BytesIO(csv_text.encode()), "text/csv")},
    )


def commit(client, preview_id: str, key: str | None = None):
    return client.post(
        f"/api/items/import/previews/{preview_id}/commit",
        json={"idempotency_key": key or str(uuid4())},
    )


def test_schema_and_templates_are_backend_owned_and_stock_safe(client):
    schema = client.get("/api/items/import/schema")
    add_template = client.get("/api/items/import/templates/add_items")
    starting_template = client.get("/api/items/import/templates/starting_inventory")

    assert schema.status_code == 200
    assert [outcome["key"] for outcome in schema.json()["outcomes"]] == ["add_items", "update_items", "starting_inventory"]
    assert schema.headers["x-import-schema-version"] == add_template.headers["x-import-schema-version"]
    assert "On hand" not in add_template.text
    assert "Allocated" not in add_template.text
    assert starting_template.text.splitlines()[0] == "SKU,Starting quantity,Warehouse,Inventory location,Reference note"


def test_add_items_preview_is_persisted_paginated_and_idempotent(client):
    response = upload(client, "add_items", "SKU,Product name,Barcode,Unit cost\nNEW-CSV-1,New food,000123,4.25\n")

    assert response.status_code == 201, response.text
    preview = response.json()
    assert preview["status"] == "ready"
    assert preview["summary"]["create_count"] == 1
    rows = client.get(f"/api/items/import/previews/{preview['preview_id']}/rows", params={"page_size": 1}).json()
    assert rows["total"] == 1
    assert rows["rows"][0]["state"] == "will_create"

    key = str(uuid4())
    first = commit(client, preview["preview_id"], key)
    second = commit(client, preview["preview_id"], key)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["created_count"] == 1
    source = client.get(f"/api/import-jobs/{first.json()['import_job_id']}/source-file")
    assert source.status_code == 200
    assert "NEW-CSV-1,New food,000123,4.25" in source.text
    item = client.get("/api/items", params={"sku": "NEW-CSV-1"}).json()["items"][0]
    assert item["In Stock"] == item["Allocated"] == item["Sellable"] == 0
    assert client.get("/api/stock-movements", params={"item_id": item["id"]}).json()["total"] == 0


def test_update_metadata_never_changes_quantities_or_stock_history(client):
    original = seed_item(client, sku="SAFE-UPDATE", Description="Old name", **{"Unit Cost": 2.0, "In Stock": 17, "Allocated": 4})
    movements_before = client.get("/api/stock-movements", params={"item_id": original["id"]}).json()["total"]
    response = upload(client, "update_items", "SKU,Product name,Unit cost\nSAFE-UPDATE,Updated name,8.50\n")

    assert response.status_code == 201, response.text
    preview = response.json()
    assert preview["summary"]["update_count"] == 1
    result = commit(client, preview["preview_id"])
    assert result.status_code == 200, result.text
    updated = client.get(f"/api/items/{original['id']}").json()
    assert updated["Description"] == "Updated name"
    assert updated["Unit Cost"] == 8.5
    assert updated["In Stock"] == 17
    assert updated["Allocated"] == 4
    assert updated["Sellable"] == 13
    assert client.get("/api/stock-movements", params={"item_id": original["id"]}).json()["total"] == movements_before
    job_id = result.json()["import_job_id"]
    assert len(client.get(f"/api/import-jobs/{job_id}/changes").json()) == 2
    rollback = client.post(f"/api/import-jobs/{job_id}/rollback")
    assert rollback.status_code == 200, rollback.text
    restored = client.get(f"/api/items/{original['id']}").json()
    assert restored["Description"] == "Old name"
    assert restored["Unit Cost"] == 2
    assert restored["In Stock"] == 17
    assert client.get("/api/stock-movements", params={"item_id": original["id"]}).json()["total"] == movements_before


def test_duplicate_can_be_corrected_inline_before_commit(client):
    response = upload(client, "add_items", "SKU,Product name\nDUP-CSV,One\nDUP-CSV,Two\n")
    preview = response.json()
    assert preview["summary"]["duplicate_count"] == 2

    corrected = client.patch(
        f"/api/items/import/previews/{preview['preview_id']}/rows/3",
        json={"values": {"sku": "DUP-CSV-2"}},
    )
    assert corrected.status_code == 200, corrected.text
    refreshed = client.get(f"/api/items/import/previews/{preview['preview_id']}").json()
    assert refreshed["summary"]["create_count"] == 2
    assert refreshed["summary"]["duplicate_count"] == 0


def test_starting_inventory_creates_one_audited_movement_and_rejects_reuse(client):
    item = seed_item(client, sku="START-CSV", **{"In Stock": 0, "Allocated": 0})
    location = client.post(
        "/api/locations",
        json={"warehouse": "Main Warehouse", "code": "RACK-1", "name": "Rack 1", "isActive": True},
    )
    assert location.status_code == 201, location.text
    csv_text = "SKU,Starting quantity,Warehouse,Inventory location,Reference note\nSTART-CSV,12,Main Warehouse,Rack 1,Initial count\n"
    preview = upload(client, "starting_inventory", csv_text).json()

    assert preview["summary"]["starting_units"] == 12
    assert commit(client, preview["preview_id"]).json()["updated_count"] == 1
    updated = client.get(f"/api/items/{item['id']}").json()
    assert updated["In Stock"] == updated["Sellable"] == 12
    movements = client.get("/api/stock-movements", params={"item_id": item["id"]}).json()
    assert movements["total"] == 1

    blocked = upload(client, "starting_inventory", csv_text).json()
    assert blocked["summary"]["blocked_count"] == 1
    assert blocked["summary"]["ready_count"] == 0


def test_mapping_profiles_are_private_crud_resources(client):
    payload = {
        "name": "Supplier A",
        "outcome": "add_items",
        "source_headers": ["Vendor code", "Title"],
        "mapping": {"Vendor code": "sku", "Title": "product_name"},
    }
    created = client.post("/api/items/import/profiles", json=payload)
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]
    assert client.get("/api/items/import/profiles", params={"outcome": "add_items"}).json()[0]["name"] == "Supplier A"
    assert client.patch(f"/api/items/import/profiles/{profile_id}", json={"name": "Supplier A v2"}).json()["name"] == "Supplier A v2"
    assert client.delete(f"/api/items/import/profiles/{profile_id}").status_code == 204


def test_item_data_quality_is_actionable_and_filters_the_item_list(client):
    seed_item(client, sku="QUALITY-1", Barcode="QUALITY-DUP", Brand="", Category="", **{"Unit Cost": None, "In Stock": 0, "Allocated": 0})
    seed_item(client, sku="QUALITY-2", Barcode="QUALITY-DUP", **{"In Stock": 0, "Allocated": 0})

    quality = client.get("/api/items/data-quality").json()
    counts = {issue["key"]: issue["count"] for issue in quality["issues"]}
    assert counts["duplicate_barcode"] == 2
    assert counts["missing_brand"] == 1
    assert counts["missing_category"] == 1
    assert counts["missing_cost"] == 1
    assert quality["items_needing_attention"] == 2
    filtered = client.get("/api/items", params={"data_quality": "duplicate_barcode", "page": 1, "page_size": 20}).json()
    assert {row["SKU"] for row in filtered["items"]} == {"QUALITY-1", "QUALITY-2"}


def test_commit_stops_when_an_item_changed_after_preview(client):
    item = seed_item(client, sku="STALE-UPDATE", Brand="Before", **{"In Stock": 0, "Allocated": 0})
    preview = upload(client, "update_items", "SKU,Brand\nSTALE-UPDATE,From CSV\n").json()
    changed = client.patch(f"/api/items/{item['id']}", json={"Brand": "Changed after preview"})
    assert changed.status_code == 200, changed.text

    response = commit(client, preview["preview_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_preview"
    assert client.get(f"/api/items/{item['id']}").json()["Brand"] == "Changed after preview"


def test_excluded_rows_are_recorded_without_creating_items(client):
    preview = upload(client, "add_items", "SKU,Product name\nEXCLUDE-ME,Do not create\n").json()
    excluded = client.patch(f"/api/items/import/previews/{preview['preview_id']}/rows/2", json={"excluded": True})
    assert excluded.status_code == 200, excluded.text

    result = commit(client, preview["preview_id"]).json()
    assert result["excluded_count"] == 1
    assert result["created_count"] == 0
    assert client.get("/api/items", params={"sku": "EXCLUDE-ME"}).json()["total"] == 0


def test_upload_boundary_rejects_wrong_extensions_and_duplicate_headers(client):
    wrong_extension = upload(client, "add_items", "SKU\nA\n", filename="items.xlsx")
    duplicate_headers = upload(client, "add_items", "SKU, sku \nA,B\n")

    assert wrong_extension.status_code == 400
    assert wrong_extension.json()["detail"]["code"] == "invalid_file_type"
    assert duplicate_headers.status_code == 400
    assert duplicate_headers.json()["detail"]["code"] == "duplicate_headers"


def test_near_limit_5000_row_preview_has_bounded_memory_payload_and_pagination(client):
    product_name = "Premium pet food " + ("x" * 1780)
    csv_text = "SKU,Product name\n" + "".join(f"LOAD-{row:05d},{product_name}\n" for row in range(5000))
    file_bytes = len(csv_text.encode())
    query_count = 0

    def count_query(*_args):
        nonlocal query_count
        query_count += 1

    event.listen(client.test_engine, "before_cursor_execute", count_query)
    tracemalloc.start()
    started = perf_counter()
    response = upload(client, "add_items", csv_text)
    preview_seconds = perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    started = perf_counter()
    page = client.get(
        f"/api/items/import/previews/{response.json()['preview_id']}/rows",
        params={"page": 100, "page_size": 25},
    )
    page_seconds = perf_counter() - started
    preview_query_count = query_count

    tracemalloc.start()
    started = perf_counter()
    result = commit(client, response.json()["preview_id"])
    commit_seconds = perf_counter() - started
    _, commit_peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    commit_query_count = query_count - preview_query_count
    event.remove(client.test_engine, "before_cursor_execute", count_query)

    print({
        "file_bytes": file_bytes,
        "preview_seconds": round(preview_seconds, 3),
        "pagination_seconds": round(page_seconds, 3),
        "commit_seconds": round(commit_seconds, 3),
        "preview_peak_bytes": peak_bytes,
        "commit_peak_bytes": commit_peak_bytes,
        "response_bytes": len(response.content),
        "page_bytes": len(page.content),
        "preview_database_queries": preview_query_count,
        "commit_database_queries": commit_query_count,
    })
    assert 9_000_000 < file_bytes < 10 * 1024 * 1024
    assert response.status_code == 201, response.text
    assert response.json()["summary"]["total_rows"] == 5000
    assert page.status_code == 200
    assert page.json()["total"] == 5000
    assert len(page.json()["rows"]) == 25
    assert result.status_code == 200, result.text
    assert result.json()["created_count"] == 5000
    assert len(response.content) < 100_000
    assert len(page.content) < 250_000
    assert preview_seconds < 30
    assert page_seconds < 2
    assert commit_seconds < 30
    assert peak_bytes < 512 * 1024 * 1024
    assert commit_peak_bytes < 512 * 1024 * 1024
