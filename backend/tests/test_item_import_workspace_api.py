import tracemalloc
from decimal import Decimal
from io import BytesIO
from time import perf_counter
from uuid import uuid4

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryItem, InventoryItemLocation, InventoryLocation, StockAdjustmentLine
from app.services import item_import_workflow
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
    stock_template = client.get("/api/items/import/templates/update_stock")
    starting_template = client.get("/api/items/import/templates/starting_inventory")

    assert schema.status_code == 200
    assert [outcome["key"] for outcome in schema.json()["outcomes"]] == ["add_items", "update_items", "update_stock", "starting_inventory"]
    assert next(outcome for outcome in schema.json()["outcomes"] if outcome["key"] == "update_stock")["required_fields"] == ["sku", "stock_quantity"]
    assert schema.headers["x-import-schema-version"] == add_template.headers["x-import-schema-version"]
    assert "On hand" not in add_template.text
    assert "Allocated" not in add_template.text
    assert stock_template.text.splitlines()[0] == "SKU,Warehouse,Inventory location,In stock,Reference note"
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
    changes = client.get(f"/api/import-jobs/{job_id}/changes", params={"page": 1, "page_size": 1}).json()
    assert changes["total"] == 2
    assert changes["page"] == 1
    assert changes["page_size"] == 1
    assert changes["total_pages"] == 2
    assert changes["returned_count"] == 1
    assert changes["has_previous"] is False
    assert changes["has_next"] is True
    assert set(changes["changes"][0]) == {"id", "item_id", "sku", "field", "before", "after", "source_filename", "created_by", "created_at"}
    second_change = client.get(f"/api/import-jobs/{job_id}/changes", params={"page": 2, "page_size": 1}).json()
    assert second_change["page"] == 2
    assert second_change["has_previous"] is True
    assert second_change["has_next"] is False
    assert {changes["changes"][0]["field"], second_change["changes"][0]["field"]} == {"description", "unit_cost"}
    assert client.get(f"/api/import-jobs/{job_id}/changes", params={"page_size": 101}).status_code == 422

    legacy_jobs = client.get("/api/import-jobs", params={"item_imports_only": True, "limit": 200}).json()
    paged_jobs = client.get("/api/import-jobs", params={"item_imports_only": True, "page": 1, "page_size": 1}).json()
    assert isinstance(legacy_jobs, list)
    assert paged_jobs["total"] == 1
    assert paged_jobs["jobs"][0]["id"] == job_id
    assert paged_jobs["returned_count"] == 1
    rollback = client.post(f"/api/import-jobs/{job_id}/rollback")
    assert rollback.status_code == 200, rollback.text
    restored = client.get(f"/api/items/{original['id']}").json()
    assert restored["Description"] == "Old name"
    assert restored["Unit Cost"] == 2
    assert restored["In Stock"] == 17
    assert client.get("/api/stock-movements", params={"item_id": original["id"]}).json()["total"] == movements_before


def test_stock_csv_sets_exact_location_quantity_with_one_audited_adjustment(client):
    item = seed_item(client, sku="STOCK-CSV", **{"In Stock": 10, "Allocated": 3})
    movements_before = client.get("/api/stock-movements", params={"item_id": item["id"]}).json()["total"]
    editable = client.get("/api/items/import/templates/update_stock", params={"include_existing": True})
    assert "STOCK-CSV,Main Warehouse,Rack 1,10," in editable.text
    csv_text = "SKU,Warehouse,Inventory Location,In Stock,Reference note\nSTOCK-CSV,Main Warehouse,Rack 1,4,Physical count\n"
    preview = upload(client, "update_stock", csv_text).json()

    assert preview["summary"]["update_count"] == 1
    assert preview["summary"]["stock_units_delta"] == -6
    row = client.get(f"/api/items/import/previews/{preview['preview_id']}/rows").json()["rows"][0]
    assert row["proposed_changes"]["in_stock"] == {"field": "stock_quantity", "label": "In stock · Main Warehouse / Rack 1", "before": 10, "after": 4}
    assert row["proposed_changes"]["variance"]["after"] == -6

    key = str(uuid4())
    first = commit(client, preview["preview_id"], key)
    replay = commit(client, preview["preview_id"], key)
    assert first.status_code == replay.status_code == 200, first.text
    assert first.json() == replay.json()
    assert first.json()["updated_count"] == 1
    assert first.json()["stock_adjustment_id"]
    updated = client.get(f"/api/items/{item['id']}").json()
    assert updated["In Stock"] == 4
    assert updated["Allocated"] == 3
    assert updated["Sellable"] == 1
    movements = client.get("/api/stock-movements", params={"item_id": item["id"]}).json()
    assert movements["total"] == movements_before + 1
    assert movements["movements"][0]["quantity_delta"] == -6


def test_stock_csv_rejects_negative_duplicate_and_stale_location_counts(client):
    item = seed_item(client, sku="STOCK-STALE", **{"In Stock": 10, "Allocated": 0})
    duplicate = upload(client, "update_stock", "SKU,Warehouse,Inventory Location,In Stock\nSTOCK-STALE,Main Warehouse,Rack 1,7\nSTOCK-STALE,Main Warehouse,Rack 1,8\n").json()
    assert duplicate["summary"]["duplicate_count"] == 2

    negative = upload(client, "update_stock", "SKU,Warehouse,Inventory Location,In Stock\nSTOCK-STALE,Main Warehouse,Rack 1,-1\n").json()
    assert negative["summary"]["needs_attention_count"] == 1

    preview = upload(client, "update_stock", "SKU,Warehouse,Inventory Location,In Stock\nSTOCK-STALE,Main Warehouse,Rack 1,5\n").json()
    location = client.get("/api/inventory/locations", params={"item_id": item["id"]}).json()["rows"][0]
    changed = client.post(
        "/api/inventory/adjustments",
        json={
            "idempotency_key": str(uuid4()),
            "adjustment_type": "correction",
            "reason": "Changed after CSV preview",
            "lines": [{"item_id": item["id"], "inventory_item_location_id": location["id"], "quantity_change": 1}],
        },
    )
    assert changed.status_code == 201, changed.text

    response = commit(client, preview["preview_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_preview"
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 11


def test_stock_csv_rejects_two_aliases_for_the_same_location(client):
    location = client.post(
        "/api/locations",
        json={"warehouse": "Main Warehouse", "code": "ALIAS-CODE", "name": "Alias Display", "isActive": True},
    )
    assert location.status_code == 201, location.text
    item = seed_item(client, sku="STOCK-ALIAS", **{"Inventory Location": "Alias Display", "Default Location": "Alias Display", "In Stock": 10, "Allocated": 0})

    preview = upload(
        client,
        "update_stock",
        "SKU,Warehouse,Inventory Location,In Stock\nSTOCK-ALIAS,Main Warehouse,Alias Display,8\nSTOCK-ALIAS,Main Warehouse,ALIAS-CODE,7\n",
    ).json()

    assert preview["summary"]["duplicate_count"] == 2
    assert commit(client, preview["preview_id"]).status_code == 409
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 10


def test_full_inventory_export_updates_stock_and_accepts_blank_zero_location(client):
    changed = seed_item(client, sku="FULL-EXPORT-CHANGED", **{"In Stock": 10, "Allocated": 0})
    unchanged = seed_item(
        client,
        sku="FULL-EXPORT-ZERO",
        Warehouse=None,
        **{"Inventory Location": None, "Default Location": None, "In Stock": 0, "Allocated": 0},
    )
    csv_text = (
        "Client,SKU,Description,Warehouse,Inventory Location,In Stock,Allocated,Brand\n"
        "Pongo,FULL-EXPORT-CHANGED,Changed,Main Warehouse,,12,0,Test Brand\n"
        "Pongo,FULL-EXPORT-ZERO,Zero,Main Warehouse,,0,0,Test Brand\n"
    )

    response = upload(client, "update_stock", csv_text, "inventoryexport.csv")
    assert response.status_code == 201, response.text
    preview = response.json()
    assert preview["summary"]["missing_required_mappings"] == []
    assert preview["summary"]["update_count"] == 1
    assert preview["summary"]["no_changes_count"] == 1
    assert preview["summary"]["needs_attention_count"] == 0

    result = commit(client, preview["preview_id"])
    assert result.status_code == 200, result.text
    assert result.json()["updated_count"] == 1
    assert result.json()["unchanged_count"] == 1
    assert client.get(f"/api/items/{changed['id']}").json()["In Stock"] == 12
    assert client.get(f"/api/items/{unchanged['id']}").json()["In Stock"] == 0


def test_stock_csv_accepts_an_existing_description_longer_than_the_preview_label(client):
    description = "Long product description " * 30
    item = seed_item(client, sku="LONG-STOCK-DESCRIPTION", Description=description, **{"In Stock": 1, "Allocated": 0})

    response = upload(client, "update_stock", "SKU,In Stock\nLONG-STOCK-DESCRIPTION,2\n")

    assert response.status_code == 201, response.text
    preview = response.json()
    row = client.get(f"/api/items/import/previews/{preview['preview_id']}/rows").json()["rows"][0]
    assert row["product_name"] == description[:500]
    result = commit(client, preview["preview_id"])
    assert result.status_code == 200, result.text
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 2


def test_stock_csv_is_all_or_nothing_and_cannot_exclude_errors(client):
    item = seed_item(client, sku="ATOMIC-STOCK", **{"In Stock": 10, "Allocated": 0})
    movements_before = client.get("/api/stock-movements", params={"item_id": item["id"]}).json()["total"]
    preview = upload(
        client,
        "update_stock",
        "SKU,In Stock\nATOMIC-STOCK,4\nUNKNOWN-STOCK,7\n",
    ).json()
    assert preview["summary"]["update_count"] == 1
    assert preview["summary"]["unmatched_count"] == 1

    excluded = client.patch(
        f"/api/items/import/previews/{preview['preview_id']}/rows/3",
        json={"excluded": True},
    )
    assert excluded.status_code == 200, excluded.text
    response = commit(client, preview["preview_id"])
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stock_import_not_ready"
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 10
    assert client.get("/api/stock-movements", params={"item_id": item["id"]}).json()["total"] == movements_before


def test_stock_csv_blocks_quantity_below_existing_allocation(client):
    item = seed_item(client, sku="ALLOCATED-STOCK", **{"In Stock": 10, "Allocated": 3})
    preview = upload(client, "update_stock", "SKU,In Stock\nALLOCATED-STOCK,2\n").json()

    assert preview["summary"]["needs_attention_count"] == 1
    row = client.get(f"/api/items/import/previews/{preview['preview_id']}/rows").json()["rows"][0]
    assert row["issues"][0]["code"] == "stock_below_allocated"
    assert commit(client, preview["preview_id"]).status_code == 409
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 10


def test_stock_commit_locks_every_row_before_the_final_stale_check(client, monkeypatch):
    seed_item(client, sku="LOCKED-NO-CHANGE", **{"In Stock": 10, "Allocated": 0})
    preview = upload(client, "update_stock", "SKU,In Stock\nLOCKED-NO-CHANGE,10\n").json()
    calls = []
    original_lock = item_import_workflow.lock_inventory_stock
    original_stale = item_import_workflow.stale_rows

    def lock_first(db, item_ids):
        calls.append("lock")
        return original_lock(db, item_ids)

    def check_after_lock(saved_preview, rows, db):
        calls.append("stale")
        assert calls[:2] == ["lock", "stale"]
        return original_stale(saved_preview, rows, db)

    monkeypatch.setattr(item_import_workflow, "lock_inventory_stock", lock_first)
    monkeypatch.setattr(item_import_workflow, "stale_rows", check_after_lock)

    result = commit(client, preview["preview_id"])
    assert result.status_code == 200, result.text
    assert result.json()["unchanged_count"] == 1
    assert calls[:2] == ["lock", "stale"]


def test_1500_stock_rows_commit_in_one_adjustment(client):
    with Session(client.test_engine) as db:
        location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code="BULK", location_name="Bulk", active=True)
        db.add(location)
        db.flush()
        items = [
            InventoryItem(
                client="Pongo",
                sku=f"BULK-STOCK-{index:04d}",
                description="Bulk stock test",
                warehouse="Main Warehouse",
                inventory_location="Bulk",
                default_location="Bulk",
                in_stock=Decimal("1"),
                allocated=Decimal("0"),
                sellable=Decimal("1"),
                on_order=Decimal("0"),
                active=True,
                non_inventory=False,
            )
            for index in range(1500)
        ]
        db.add_all(items)
        db.flush()
        db.add_all([
            InventoryItemLocation(
                inventory_item_id=item.id,
                location_id=location.id,
                client="Pongo",
                warehouse="Main Warehouse",
                inventory_location="Bulk",
                location_code="BULK",
                location_name="Bulk",
                is_default_location=True,
                in_stock=Decimal("1"),
                allocated=Decimal("0"),
                sellable=Decimal("1"),
                on_order=Decimal("0"),
                under_par=False,
                active=True,
            )
            for item in items
        ])
        db.commit()

    csv_text = "SKU,In Stock\n" + "".join(f"BULK-STOCK-{index:04d},2\n" for index in range(1500))
    preview = upload(client, "update_stock", csv_text).json()
    assert preview["summary"]["update_count"] == 1500

    result = commit(client, preview["preview_id"])
    assert result.status_code == 200, result.text
    assert result.json()["updated_count"] == 1500
    assert result.json()["failed_count"] == 0
    with Session(client.test_engine) as db:
        assert db.scalar(select(func.count()).select_from(StockAdjustmentLine).where(StockAdjustmentLine.adjustment_id == result.json()["stock_adjustment_id"])) == 1500
        assert db.scalar(select(func.count()).select_from(InventoryItem).where(InventoryItem.sku.like("BULK-STOCK-%"), InventoryItem.in_stock == 2)) == 1500


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


def test_add_items_commit_stops_when_sku_or_barcode_appears_after_preview(client):
    preview = upload(
        client,
        "add_items",
        "SKU,Product name,Barcode\nSTALE-SKU,One,STALE-BC-1\nSTALE-BC-SOURCE,Two,STALE-BC-2\n",
    ).json()
    seed_item(client, sku="STALE-SKU", Barcode="OTHER-BARCODE")
    seed_item(client, sku="OTHER-SKU", Barcode="STALE-BC-2")

    response = commit(client, preview["preview_id"])

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_preview"
    assert response.json()["detail"]["row_numbers"] == [2, 3]


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


def test_upload_accepts_standard_escaped_quotes(client):
    response = upload(client, "add_items", 'SKU,Product name\nQUOTED-CSV-1,"Original"", Cat Treats"\n')

    assert response.status_code == 201, response.text
    preview = response.json()
    rows = client.get(f"/api/items/import/previews/{preview['preview_id']}/rows").json()
    assert rows["rows"][0]["product_name"] == 'Original", Cat Treats'


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
    # Wall-clock time on shared CI runners is diagnostic only. Query ceilings
    # catch N+1 regressions deterministically without treating runner speed as
    # a production PostgreSQL service-level objective.
    assert preview_query_count <= 5_100
    assert commit_query_count <= 31_000
    assert peak_bytes < 512 * 1024 * 1024
    assert commit_peak_bytes < 512 * 1024 * 1024
