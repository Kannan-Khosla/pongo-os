from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import seed_location


def setup_stock_item(client, sku="NEW-001", barcode="NEW-BAR", location="BULK-01", in_stock=4, allocated=1):
    item = seed_item(client, sku=sku, Barcode=barcode, **{"Inventory Location": location, "Default Location": location, "In Stock": in_stock, "Allocated": allocated, "Unit Cost": 2, "Sales Price": 5, "Par Level": 5, "Re-Order": True})
    seed_location(client, code=location, name=location)
    return item


def test_item_detail_activity_history_and_notes(client):
    item = setup_stock_item(client)

    detail = client.get(f"/api/items/{item['id']}/detail")
    assert detail.status_code == 200
    body = detail.json()
    assert body["item"]["sku"] == "NEW-001"
    assert body["stock_by_location"][0]["inventory_location"] == "BULK-01"
    assert "quick_stats" in body

    note = client.post(f"/api/items/{item['id']}/notes", json={"note": "Watch reorder shelf.", "note_type": "warning"})
    assert note.status_code == 201
    activity = client.get(f"/api/items/{item['id']}/activity", params={"type": "note"})
    assert activity.status_code == 200
    assert activity.json()["activity"][0]["type"] == "note"

    history = client.get(f"/api/items/{item['id']}/stock-movements")
    assert history.status_code == 200
    assert history.json()["rows"] == []


def test_item_bulk_edit_blocks_stock_and_updates_metadata(client):
    item = setup_stock_item(client)

    preview = client.post("/api/items/bulk/preview", json={"item_ids": [item["id"]], "updates": {"brand": "Bulk Brand", "in_stock": 99}})
    assert preview.status_code == 200
    assert preview.json()["can_commit"] is False
    assert "Blocked" in preview.json()["warnings"][0]

    commit = client.post("/api/items/bulk/commit", json={"item_ids": [item["id"]], "updates": {"brand": "Bulk Brand"}})
    assert commit.status_code == 200
    assert commit.json()["updated_count"] == 1
    refreshed = client.get(f"/api/items/{item['id']}").json()
    assert refreshed["Brand"] == "Bulk Brand"
    assert refreshed["In Stock"] == 4


def test_saved_views_crud_and_item_search(client):
    setup_stock_item(client, sku="SEARCH-001", barcode="SEARCH-BAR")

    search = client.get("/api/items/search", params={"q": "SEARCH"})
    assert search.status_code == 200
    assert search.json()["items"][0]["sku"] == "SEARCH-001"

    created = client.post("/api/ui/saved-views", json={"page": "items", "name": "Warehouse view", "filters": {"warehouse": "Main Warehouse"}, "columns": ["SKU"]})
    assert created.status_code == 201
    view_id = created.json()["id"]
    listed = client.get("/api/ui/saved-views", params={"page": "items"})
    assert listed.json()["total"] == 1
    patched = client.patch(f"/api/ui/saved-views/{view_id}", json={"name": "Updated view"})
    assert patched.json()["name"] == "Updated view"
    deleted = client.delete(f"/api/ui/saved-views/{view_id}")
    assert deleted.json()["deleted"] is True


def test_bulk_receiving_preview_commit_detail_export(client):
    item = setup_stock_item(client, sku="BULK-001", barcode="BULK-BAR", in_stock=4, allocated=1)
    payload = {
        "warehouse": "Main Warehouse",
        "notes": "Bulk session",
        "lines": [
            {"sku": "BULK-001", "quantity": 3, "unit_cost": 2.5, "inventory_location": "BULK-01", "scan_input": "BULK-001"},
            {"barcode": "BULK-BAR", "quantity": 2, "unit_cost": 2.5, "inventory_location": "BULK-01", "scan_input": "BULK-BAR"},
        ],
    }

    preview = client.post("/api/receipts/bulk/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["valid_line_count"] == 2
    assert preview.json()["total_quantity"] == 5

    commit = client.post("/api/receipts/bulk/commit", json=payload)
    assert commit.status_code == 200, commit.text
    body = commit.json()
    assert body["receipt_number"].startswith("RCPT-")
    assert len(body["lines"]) == 2
    refreshed = client.get(f"/api/items/{item['id']}").json()
    assert refreshed["In Stock"] == 9
    movements = client.get("/api/stock-movements", params={"sku": "BULK-001"}).json()["movements"]
    assert len(movements) == 2

    detail = client.get(f"/api/receipts/{body['id']}/detail")
    assert detail.status_code == 200
    export = client.get(f"/api/receipts/{body['id']}/export")
    assert export.status_code == 200
    assert "BULK-001" in export.text


def test_bulk_receiving_invalid_blocks_by_default(client):
    setup_stock_item(client, sku="BLOCK-001")
    payload = {"warehouse": "Main Warehouse", "lines": [{"sku": "BLOCK-001", "quantity": 1, "inventory_location": "BULK-01"}, {"sku": "MISSING", "quantity": 1, "inventory_location": "BULK-01"}]}

    response = client.post("/api/receipts/bulk/commit", json=payload)

    assert response.status_code == 400
    assert client.get("/api/items", params={"sku": "BLOCK-001"}).json()["items"][0]["In Stock"] == 4


def test_scanner_lookup_receiving_cycle_transfer_adjustment(client):
    item = setup_stock_item(client, sku="SCAN-001", barcode="SCAN-BAR", location="SCAN-01", in_stock=10, allocated=1)
    seed_location(client, code="SCAN-02", name="SCAN-02")

    lookup = client.get("/api/scanner/inventory/lookup", params={"scan_input": "SCAN-001"})
    assert lookup.status_code == 200
    assert lookup.json()["matched"] is True
    assert client.get("/api/scanner/inventory/lookup", params={"scan_input": "NOPE"}).json()["matched"] is False

    location = client.get("/api/scanner/location/lookup", params={"scan_input": "SCAN-01"})
    assert location.status_code == 200
    assert location.json()["matched"] is True

    receiving = client.post("/api/scanner/receiving/scan/commit", json={"scan_input": "SCAN-BAR", "warehouse": "Main Warehouse", "inventory_location": "SCAN-01", "quantity": 1})
    assert receiving.status_code == 200

    missing_reason = client.post("/api/scanner/cycle-count/preview", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-01", "counted_quantity": 7})
    assert missing_reason.json()["can_commit"] is False
    counted = client.post("/api/scanner/cycle-count/commit", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-01", "counted_quantity": 7, "reason": "Scanner variance"})
    assert counted.status_code == 200

    transfer_preview = client.post("/api/scanner/transfers/preview", json={"scan_input": "SCAN-001", "from_warehouse": "Main Warehouse", "from_inventory_location": "SCAN-01", "to_warehouse": "Main Warehouse", "to_inventory_location": "SCAN-02", "quantity": 99})
    assert transfer_preview.json()["can_commit"] is False
    transfer = client.post("/api/scanner/transfers/commit", json={"scan_input": "SCAN-001", "from_warehouse": "Main Warehouse", "from_inventory_location": "SCAN-01", "to_warehouse": "Main Warehouse", "to_inventory_location": "SCAN-02", "quantity": 1})
    assert transfer.status_code == 200

    no_reason = client.post("/api/scanner/adjustments/preview", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-02", "quantity_change": -1})
    assert no_reason.json()["can_commit"] is False
    adjustment = client.post("/api/scanner/adjustments/commit", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-02", "quantity_change": -1, "reason": "Damage", "adjustment_type": "damage"})
    assert adjustment.status_code == 200


def test_expanded_reports_and_dashboard(client):
    setup_stock_item(client, sku="RPT-001", barcode="RPT-BAR", in_stock=2, allocated=0)
    client.post("/api/receipts/bulk/commit", json={"warehouse": "Main Warehouse", "lines": [{"sku": "RPT-001", "quantity": 2, "unit_cost": 3, "inventory_location": "BULK-01"}]})
    client.post("/api/scanner/adjustments/commit", json={"scan_input": "RPT-001", "warehouse": "Main Warehouse", "inventory_location": "BULK-01", "quantity_change": -1, "reason": "Loss", "adjustment_type": "loss"})

    for report in ["inventory-valuation", "low-stock", "stock-movement-ledger", "item-activity", "location-utilization", "margin-by-sku", "receiving-cost", "adjustments"]:
        rows = client.get(f"/api/reports/{report}")
        assert rows.status_code == 200, report
        summary = client.get(f"/api/reports/{report}/summary")
        assert summary.status_code == 200, report
        export = client.get(f"/api/reports/{report}/export")
        assert export.status_code == 200, report

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert "reorder_count" in dashboard.json()["inventory_health"]
