import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO

from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryItem, InventoryItemLocation, MovementType, StockAdjustment, StockAdjustmentLine, StockMovement
from app.models.orders import Order, OrderItem
from app.models.receipts import Receipt, ReceiptItem
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
    assert history.json()["rows"][0]["title"] == "Opening Balance Import"


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


def test_item_bulk_edit_adds_tags_cost_and_real_location_without_moving_stock(client):
    first = setup_stock_item(client, sku="BULK-META-1", barcode="BULK-META-BAR-1", location="BULK-A", in_stock=4)
    second = setup_stock_item(client, sku="BULK-META-2", barcode="BULK-META-BAR-2", location="BULK-B", in_stock=7)
    destination = seed_location(client, code="BULK-C", name="Bulk C")
    payload = {
        "item_ids": [first["id"], second["id"]],
        "updates": {
            "client": "Shared Client",
            "description": "Shared bulk description",
            "brand": "Shared Brand",
            "unit_cost": 8.75,
            "add_tags": "Frozen, Priority",
            "location_id": destination["id"],
            "make_default_location": True,
        },
    }

    preview = client.post("/api/items/bulk/preview", json=payload)
    assert preview.status_code == 200
    assert preview.json()["can_commit"] is True
    assert preview.json()["affected_count"] == 2

    commit = client.post("/api/items/bulk/commit", json=payload)
    assert commit.status_code == 200
    assert commit.json()["updated_count"] == 2

    refreshed_first = client.get(f"/api/items/{first['id']}").json()
    refreshed_second = client.get(f"/api/items/{second['id']}").json()
    assert refreshed_first["Client"] == refreshed_second["Client"] == "Shared Client"
    assert refreshed_first["Description"] == refreshed_second["Description"] == "Shared bulk description"
    assert refreshed_first["Brand"] == refreshed_second["Brand"] == "Shared Brand"
    assert refreshed_first["Unit Cost"] == refreshed_second["Unit Cost"] == 8.75
    assert refreshed_first["Tags"] == refreshed_second["Tags"] == "Frozen, Priority"
    assert refreshed_first["In Stock"] == 4
    assert refreshed_second["In Stock"] == 7
    first_locations = client.get(f"/api/items/{first['id']}/locations").json()["locations"]
    assert any(row["inventory_location"] == "BULK-C" and row["is_default_location"] for row in first_locations)


def test_item_bulk_edit_fails_closed_for_unique_and_unknown_fields(client):
    item = setup_stock_item(client, sku="PROTECTED-SKU")

    for updates in (
        {"sku": "DUPLICATE"},
        {"barcode": "DUPLICATE"},
        {"made_up_field": "value"},
        {"unit_cost": "not-a-number"},
        {"unit_cost": -1},
    ):
        preview = client.post("/api/items/bulk/preview", json={"item_ids": [item["id"]], "updates": updates})
        assert preview.status_code == 200
        assert preview.json()["can_commit"] is False
        commit = client.post("/api/items/bulk/commit", json={"item_ids": [item["id"]], "updates": updates})
        assert commit.status_code == 400

    assert client.get(f"/api/items/{item['id']}").json()["SKU"] == "PROTECTED-SKU"


def test_saved_views_crud_and_item_search(client):
    setup_stock_item(client, sku="SEARCH-001", barcode="SEARCH-BAR")

    search = client.get("/api/items/search", params={"q": "SEARCH"})
    assert search.status_code == 200
    assert search.json()["items"][0]["sku"] == "SEARCH-001"

    created = client.post("/api/ui/saved-views", json={"page": "items", "name": "Warehouse view", "filters": {"warehouse": "Main Warehouse"}, "columns": ["SKU"], "created_by": "forged@example.com"})
    assert created.status_code == 201
    assert created.json()["created_by"] == "pytest@example.com"
    view_id = created.json()["id"]
    listed = client.get("/api/ui/saved-views", params={"page": "items"})
    assert listed.json()["total"] == 1
    patched = client.patch(f"/api/ui/saved-views/{view_id}", json={"name": "Updated view", "created_by": "forged@example.com"})
    assert patched.json()["name"] == "Updated view"
    assert patched.json()["created_by"] == "pytest@example.com"
    deleted = client.delete(f"/api/ui/saved-views/{view_id}")
    assert deleted.json()["deleted"] is True


def test_bulk_receiving_preview_commit_detail_export(client):
    item = setup_stock_item(client, sku="BULK-001", barcode="BULK-BAR", in_stock=4, allocated=1)
    payload = {
        "idempotency_key": "bulk-receipt-detail",
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
    assert len(movements) == 3

    detail = client.get(f"/api/receipts/{body['id']}/detail")
    assert detail.status_code == 200
    export = client.get(f"/api/receipts/{body['id']}/export")
    assert export.status_code == 200
    assert "BULK-001" in export.text


def test_bulk_receiving_invalid_blocks_by_default(client):
    setup_stock_item(client, sku="BLOCK-001")
    payload = {"idempotency_key": "bulk-receipt-invalid", "warehouse": "Main Warehouse", "lines": [{"sku": "BLOCK-001", "quantity": 1, "inventory_location": "BULK-01"}, {"sku": "MISSING", "quantity": 1, "inventory_location": "BULK-01"}]}

    response = client.post("/api/receipts/bulk/commit", json=payload)

    assert response.status_code == 400
    assert client.get("/api/items", params={"sku": "BLOCK-001"}).json()["items"][0]["In Stock"] == 4


def test_bulk_receiving_and_scanner_fail_closed_for_duplicate_barcode(client):
    setup_stock_item(client, sku="DUP-BULK-A", barcode="DUP-BULK")
    seed_item(client, sku="DUP-BULK-B", Barcode="DUP-BULK")
    payload = {
        "idempotency_key": "duplicate-bulk-receipt",
        "warehouse": "Main Warehouse",
        "lines": [{"barcode": "DUP-BULK", "quantity": 1, "inventory_location": "BULK-01"}],
    }

    bulk = client.post("/api/receipts/bulk/commit", json=payload)
    scanner = client.get("/api/scanner/inventory/lookup", params={"scan_input": "DUP-BULK"})

    assert bulk.status_code == 400
    assert scanner.status_code == 409


def test_bulk_receiving_transfer_and_adjustment_idempotency(client):
    item = setup_stock_item(client, sku="IDEMP-STOCK", barcode="IDEMP-STOCK-BAR", location="IDEMP-A", in_stock=10, allocated=1)
    seed_location(client, code="IDEMP-B", name="IDEMP-B")

    receipt_payload = {
        "idempotency_key": "bulk-receipt-1",
        "warehouse": "Main Warehouse",
        "lines": [{"sku": "IDEMP-STOCK", "quantity": 2, "inventory_location": "IDEMP-A"}],
    }
    first_receipt = client.post("/api/receipts/bulk/commit", json=receipt_payload)
    replay_receipt = client.post("/api/receipts/bulk/commit", json=receipt_payload)
    assert replay_receipt.json() == first_receipt.json()

    source = client.get("/api/inventory/locations", params={"item_id": item["id"], "inventory_location": "IDEMP-A"}).json()["rows"][0]
    transfer_payload = {
        "idempotency_key": "transfer-1",
        "created_by": "pytest",
        "lines": [
            {
                "item_id": item["id"],
                "from_inventory_item_location_id": source["id"],
                "to_warehouse": "Main Warehouse",
                "to_inventory_location": "IDEMP-B",
                "quantity": 3,
            }
        ],
    }
    first_transfer = client.post("/api/inventory/transfers", json=transfer_payload)
    replay_transfer = client.post("/api/inventory/transfers", json=transfer_payload)
    changed_transfer = client.post(
        "/api/inventory/transfers",
        json={**transfer_payload, "lines": [{**transfer_payload["lines"][0], "quantity": 2}]},
    )
    assert replay_transfer.json() == first_transfer.json()
    assert changed_transfer.status_code == 409

    destination = client.get("/api/inventory/locations", params={"item_id": item["id"], "inventory_location": "IDEMP-B"}).json()["rows"][0]
    adjustment_payload = {
        "idempotency_key": "adjustment-1",
        "adjustment_type": "correction",
        "reason": "Idempotency check",
        "created_by": "pytest",
        "lines": [{"item_id": item["id"], "inventory_item_location_id": destination["id"], "quantity_change": -1}],
    }
    first_adjustment = client.post("/api/inventory/adjustments", json=adjustment_payload)
    replay_adjustment = client.post("/api/inventory/adjustments", json=adjustment_payload)
    changed_adjustment = client.post(
        "/api/inventory/adjustments",
        json={**adjustment_payload, "reason": "Different request"},
    )
    assert replay_adjustment.json() == first_adjustment.json()
    assert changed_adjustment.status_code == 409

    rows = client.get("/api/inventory/locations", params={"item_id": item["id"]}).json()["rows"]
    assert sum(row["in_stock"] for row in rows) == 11
    assert next(row for row in rows if row["inventory_location"] == "IDEMP-B")["in_stock"] == 2


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

    receiving = client.post("/api/scanner/receiving/scan/commit", json={"idempotency_key": "scanner-receive", "scan_input": "SCAN-BAR", "warehouse": "Main Warehouse", "inventory_location": "SCAN-01", "quantity": 1})
    assert receiving.status_code == 200

    missing_reason = client.post("/api/scanner/cycle-count/preview", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-01", "counted_quantity": 7})
    assert missing_reason.json()["can_commit"] is False
    counted = client.post("/api/scanner/cycle-count/commit", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-01", "counted_quantity": 7, "reason": "Scanner variance"})
    assert counted.status_code == 200

    transfer_preview = client.post("/api/scanner/transfers/preview", json={"scan_input": "SCAN-001", "from_warehouse": "Main Warehouse", "from_inventory_location": "SCAN-01", "to_warehouse": "Main Warehouse", "to_inventory_location": "SCAN-02", "quantity": 99})
    assert transfer_preview.json()["can_commit"] is False
    transfer = client.post("/api/scanner/transfers/commit", json={"idempotency_key": "scanner-transfer", "scan_input": "SCAN-001", "from_warehouse": "Main Warehouse", "from_inventory_location": "SCAN-01", "to_warehouse": "Main Warehouse", "to_inventory_location": "SCAN-02", "quantity": 1})
    assert transfer.status_code == 200

    no_reason = client.post("/api/scanner/adjustments/preview", json={"scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-02", "quantity_change": -1})
    assert no_reason.json()["can_commit"] is False
    adjustment = client.post("/api/scanner/adjustments/commit", json={"idempotency_key": "scanner-adjustment", "scan_input": "SCAN-001", "warehouse": "Main Warehouse", "inventory_location": "SCAN-02", "quantity_change": -1, "reason": "Damage", "adjustment_type": "damage"})
    assert adjustment.status_code == 200


def test_expanded_reports_and_dashboard(client):
    setup_stock_item(client, sku="RPT-001", barcode="RPT-BAR", in_stock=2, allocated=0)
    client.post("/api/receipts/bulk/commit", json={"idempotency_key": "report-receipt", "warehouse": "Main Warehouse", "lines": [{"sku": "RPT-001", "quantity": 2, "unit_cost": 3, "inventory_location": "BULK-01"}]})
    client.post("/api/scanner/adjustments/commit", json={"idempotency_key": "report-adjustment", "scan_input": "RPT-001", "warehouse": "Main Warehouse", "inventory_location": "BULK-01", "quantity_change": -1, "reason": "Loss", "adjustment_type": "loss"})

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


def assert_filtered_report(client, report, params, count_key, expected_sku):
    rows_response = client.get(f"/api/reports/{report}", params=params)
    assert rows_response.status_code == 200, rows_response.text
    assert [row["sku"] for row in rows_response.json()] == [expected_sku]

    summary_response = client.get(f"/api/reports/{report}/summary", params=params)
    assert summary_response.status_code == 200, summary_response.text
    assert summary_response.json()[count_key] == 1

    export_response = client.get(f"/api/reports/{report}/export", params=params)
    assert export_response.status_code == 200, export_response.text
    assert [row["sku"] for row in csv.DictReader(StringIO(export_response.text))] == [expected_sku]


def test_expanded_report_rows_summaries_and_exports_share_each_filter(client):
    target = setup_stock_item(client, sku="FILTER-TARGET", barcode="FILTER-TARGET-BAR", location="TARGET-LOC")
    other = setup_stock_item(client, sku="FILTER-OTHER", barcode="FILTER-OTHER-BAR", location="OTHER-LOC")
    target_date = datetime(2026, 7, 10, 12, 0)
    other_date = datetime(2026, 6, 10, 12, 0)

    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        for movement in db.scalars(
            select(StockMovement).where(
                StockMovement.inventory_item_id.in_([target["id"], other["id"]]),
                StockMovement.movement_type == MovementType.opening_balance_import,
            )
        ):
            db.delete(movement)
        target_location = db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == target["id"]))
        other_location = db.scalar(select(InventoryItemLocation).where(InventoryItemLocation.inventory_item_id == other["id"]))
        target_location.warehouse = "Target Warehouse"
        other_location.warehouse = "Other Warehouse"
        db.get(InventoryItem, target["id"]).brand = "Target Brand"
        db.get(InventoryItem, target["id"]).category = "Target Category"
        db.get(InventoryItem, other["id"]).brand = "Other Brand"
        db.get(InventoryItem, other["id"]).category = "Other Category"

        target_order = Order(order_number="FILTER-ORDER-TARGET")
        other_order = Order(order_number="FILTER-ORDER-OTHER")
        db.add_all([target_order, other_order])
        db.flush()
        db.add_all(
            [
                OrderItem(order_id=target_order.id, inventory_item_id=target["id"], sku="FILTER-TARGET", quantity_ordered=Decimal("2"), quantity_fulfilled=Decimal("1"), unit_cost=Decimal("4"), line_total=Decimal("20"), created_at=target_date),
                OrderItem(order_id=other_order.id, inventory_item_id=other["id"], sku="FILTER-OTHER", quantity_ordered=Decimal("3"), unit_cost=Decimal("2"), line_total=Decimal("12"), created_at=other_date),
            ]
        )

        target_receipt = Receipt(receipt_number="FILTER-RECEIPT-TARGET", warehouse="Target Warehouse", received_date=date(2026, 7, 10))
        other_receipt = Receipt(receipt_number="FILTER-RECEIPT-OTHER", warehouse="Other Warehouse", received_date=date(2026, 6, 10))
        db.add_all([target_receipt, other_receipt])
        db.flush()
        db.add_all(
            [
                ReceiptItem(receipt_id=target_receipt.id, inventory_item_id=target["id"], sku="FILTER-TARGET", warehouse="Target Warehouse", inventory_location_name="TARGET-LOC", quantity=Decimal("2"), quantity_received=Decimal("2"), unit_cost_total=Decimal("8"), created_at=target_date),
                ReceiptItem(receipt_id=other_receipt.id, inventory_item_id=other["id"], sku="FILTER-OTHER", warehouse="Other Warehouse", inventory_location_name="OTHER-LOC", quantity=Decimal("3"), quantity_received=Decimal("3"), unit_cost_total=Decimal("6"), created_at=other_date),
            ]
        )

        target_adjustment = StockAdjustment(adjustment_number="FILTER-ADJ-TARGET", status="committed", adjustment_type="loss", reason="Target loss")
        other_adjustment = StockAdjustment(adjustment_number="FILTER-ADJ-OTHER", status="committed", adjustment_type="damage", reason="Other damage")
        db.add_all([target_adjustment, other_adjustment])
        db.flush()
        db.add_all(
            [
                StockAdjustmentLine(adjustment_id=target_adjustment.id, inventory_item_id=target["id"], inventory_item_location_id=target_location.id, sku="FILTER-TARGET", warehouse="Target Warehouse", inventory_location="TARGET-LOC", old_quantity=Decimal("4"), new_quantity=Decimal("3"), quantity_change=Decimal("-1"), unit_cost=Decimal("4"), created_at=target_date),
                StockAdjustmentLine(adjustment_id=other_adjustment.id, inventory_item_id=other["id"], inventory_item_location_id=other_location.id, sku="FILTER-OTHER", warehouse="Other Warehouse", inventory_location="OTHER-LOC", old_quantity=Decimal("4"), new_quantity=Decimal("2"), quantity_change=Decimal("-2"), unit_cost=Decimal("2"), created_at=other_date),
            ]
        )
        db.add_all(
            [
                StockMovement(inventory_item_id=target["id"], sku="FILTER-TARGET", barcode="FILTER-TARGET-BAR", movement_type=MovementType.loss, quantity_change=Decimal("-1"), warehouse="Target Warehouse", inventory_location_name="TARGET-LOC", created_at=target_date),
                StockMovement(inventory_item_id=other["id"], sku="FILTER-OTHER", barcode="FILTER-OTHER-BAR", movement_type=MovementType.damage, quantity_change=Decimal("-2"), warehouse="Other Warehouse", inventory_location_name="OTHER-LOC", created_at=other_date),
            ]
        )
        db.commit()
    finally:
        db_override.close()

    for params, expected_sku in [
        ({"start_date": "2026-07-01"}, "FILTER-TARGET"),
        ({"end_date": "2026-06-30"}, "FILTER-OTHER"),
        ({"sku": "FILTER-TARGET"}, "FILTER-TARGET"),
        ({"barcode": "FILTER-TARGET-BAR"}, "FILTER-TARGET"),
        ({"movement_type": "loss"}, "FILTER-TARGET"),
    ]:
        assert_filtered_report(client, "item-activity", params, "total_rows", expected_sku)

    for params, expected_sku in [
        ({"start_date": "2026-07-01"}, "FILTER-TARGET"),
        ({"end_date": "2026-06-30"}, "FILTER-OTHER"),
        ({"sku": "FILTER-TARGET"}, "FILTER-TARGET"),
        ({"brand": "Target Brand"}, "FILTER-TARGET"),
        ({"category": "Target Category"}, "FILTER-TARGET"),
    ]:
        assert_filtered_report(client, "margin-by-sku", params, "total_skus", expected_sku)

    for params, expected_sku in [
        ({"start_date": "2026-07-01"}, "FILTER-TARGET"),
        ({"end_date": "2026-06-30"}, "FILTER-OTHER"),
        ({"sku": "FILTER-TARGET"}, "FILTER-TARGET"),
        ({"warehouse": "Target Warehouse"}, "FILTER-TARGET"),
        ({"inventory_location": "TARGET-LOC"}, "FILTER-TARGET"),
    ]:
        assert_filtered_report(client, "receiving-cost", params, "total_rows", expected_sku)

    for params, expected_sku in [
        ({"adjustment_type": "loss"}, "FILTER-TARGET"),
        ({"sku": "FILTER-TARGET"}, "FILTER-TARGET"),
        ({"warehouse": "Target Warehouse"}, "FILTER-TARGET"),
        ({"inventory_location": "TARGET-LOC"}, "FILTER-TARGET"),
    ]:
        assert_filtered_report(client, "adjustments", params, "total_rows", expected_sku)
