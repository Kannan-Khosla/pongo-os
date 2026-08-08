from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_picks_api import allocated_order
from tests.test_routes_api import fulfilled_route_order, route_payload
from sqlalchemy import event


def test_dashboard_empty_db(client):
    response = client.get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["inventory_health"]["total_items"] == 0
    assert body["order_operations"]["open_orders_count"] == 0
    assert body["routes"]["draft_routes_count"] == 0
    assert body["warnings"] == []
    assert body["activity"] == []


def test_dashboard_seeded_summary_warnings_and_activity(client, monkeypatch):
    seed_item(client, sku="DASH-WARN", **{"In Stock": 1, "Allocated": 1, "Unit Cost": None, "Sales Price": None, "Default Location": ""})
    order, _ = allocated_order(client, monkeypatch, sku="DASH-PICK", barcode="DASH-BAR")
    client.post(f"/api/picks/orders/{order['id']}/scan/commit", json={"idempotency_key": "dashboard-scan-pick", "sku_or_barcode": "DASH-PICK", "quantity": 1})

    response = client.get("/api/dashboard/activity", params={"limit": 10})
    warnings = client.get("/api/dashboard/warnings").json()
    summary = client.get("/api/dashboard/summary").json()

    assert response.status_code == 200
    assert len(response.json()) >= 1
    assert summary["inventory_health"]["missing_unit_cost_count"] >= 1
    assert any(group["code"] == "items_missing_unit_cost" for group in warnings)


def test_dashboard_entity_preview_queries_are_bounded(client):
    statements = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(" ".join(statement.lower().split()))

    event.listen(client.test_engine, "before_cursor_execute", capture_statement)
    try:
        response = client.get("/api/dashboard", params={"limit": 5})
    finally:
        event.remove(client.test_engine, "before_cursor_execute", capture_statement)

    assert response.status_code == 200
    entity_prefixes = (
        "select inventory_items.id",
        "select orders.id",
        "select routes.id",
    )
    entity_queries = [statement for statement in statements if statement.startswith(entity_prefixes)]
    assert entity_queries
    assert all(" limit " in statement for statement in entity_queries)


def test_woo_remap_candidates_preview_commit(client):
    item = seed_item(client, sku="REMAP-SKU", wooProductId=9101)

    candidates = client.get("/api/integrations/woocommerce/remap/candidates")
    preview = client.post("/api/integrations/woocommerce/remap/preview", json={"woo_product_id": 9101, "woo_variation_id": None, "item_id": item["id"]})
    commit = client.post("/api/integrations/woocommerce/remap/commit", json={"woo_product_id": 9101, "woo_variation_id": None, "item_id": item["id"], "note": "pytest"})
    mappings = client.get("/api/integrations/woocommerce/remap/mappings")

    assert candidates.status_code == 200
    assert preview.status_code == 200
    assert "will not change WooCommerce or inventory" in preview.json()["safe_message"]
    assert commit.status_code == 200
    assert commit.json()["status"] == "mapped"
    assert mappings.json()["total"] == 1


def test_woo_remap_blocks_duplicate_target_preserves_stock_and_audits(client):
    first = seed_item(client, sku="REMAP-FIRST", wooProductId=9301, **{"In Stock": 7, "Allocated": 2})
    second = seed_item(client, sku="REMAP-SECOND", **{"In Stock": 4, "Allocated": 1})
    committed = client.post("/api/integrations/woocommerce/remap/commit", json={"woo_product_id": 9301, "woo_variation_id": None, "item_id": first["id"], "note": "authoritative"})
    preview = client.post("/api/integrations/woocommerce/remap/preview", json={"woo_product_id": 9301, "woo_variation_id": None, "item_id": second["id"]})
    blocked = client.post("/api/integrations/woocommerce/remap/commit", json={"woo_product_id": 9301, "woo_variation_id": None, "item_id": second["id"]})

    assert committed.status_code == 200
    assert preview.status_code == 200
    assert preview.json()["errors"]
    assert blocked.status_code == 409
    first_after = client.get(f"/api/items/{first['id']}").json()
    second_after = client.get(f"/api/items/{second['id']}").json()
    assert (first_after["In Stock"], first_after["Allocated"]) == (7, 2)
    assert (second_after["In Stock"], second_after["Allocated"]) == (4, 1)
    activity = client.get("/api/dashboard/activity", params={"limit": 20}).json()
    assert any(row["title"] == "Audit: woocommerce_remap" for row in activity)


def test_pick_scanner_match_no_match_and_overpick(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch, sku="SCAN-SKU", barcode="SCAN-BAR", quantity=2)

    scanner = client.get(f"/api/picks/orders/{order['id']}/scanner")
    no_match = client.post(f"/api/picks/orders/{order['id']}/scan/preview", json={"sku_or_barcode": "NOPE", "quantity": 1})
    overpick = client.post(f"/api/picks/orders/{order['id']}/scan/preview", json={"sku_or_barcode": "SCAN-SKU", "quantity": 99})
    commit = client.post(f"/api/picks/orders/{order['id']}/scan/commit", json={"idempotency_key": "hardening-scan-pick", "sku_or_barcode": "SCAN-BAR", "quantity": 1})

    assert scanner.status_code == 200
    assert scanner.json()["line_count"] == 1
    assert no_match.json()["status"] == "not_found"
    assert overpick.json()["status"] == "rejected"
    assert commit.json()["status"] == "posted"
    item = client.get("/api/items", params={"sku": "SCAN-SKU"}).json()["items"][0]
    assert item["In Stock"] == 5
    assert item["Allocated"] == 2
    movements = client.get("/api/stock-movements", params={"movement_type": "pick_stock_reduction"}).json()
    assert movements["total"] == 1


def test_sku_orders_report_rows_summary_export(client, monkeypatch):
    order, _ = allocated_order(client, monkeypatch, sku="SKU-ORDERS", barcode="SKU-ORDERS-BAR", quantity=3)
    client.post(f"/api/picks/orders/{order['id']}/scan/commit", json={"idempotency_key": "orders-scan-pick", "sku_or_barcode": "SKU-ORDERS", "quantity": 1})

    rows = client.get("/api/reports/sku-orders", params={"sku": "SKU-ORDERS"})
    summary = client.get("/api/reports/sku-orders/summary", params={"sku": "SKU-ORDERS"})
    exported = client.get("/api/reports/sku-orders/export", params={"sku": "SKU-ORDERS"})

    assert rows.status_code == 200
    assert rows.json()[0]["sku"] == "SKU-ORDERS"
    assert rows.json()[0]["total_quantity_ordered"] == 3
    assert summary.json()["total_quantity_ordered"] == 3
    assert exported.status_code == 200
    assert exported.text.splitlines()[0].startswith("SKU,Item ID,Description")


def test_route_advanced_local_endpoints(client, monkeypatch):
    first = fulfilled_route_order(client, monkeypatch, sku="ADV-ROUTE-1", barcode="ADV-BAR-1", woo_id=9201, product_id=8201)
    second = fulfilled_route_order(client, monkeypatch, sku="ADV-ROUTE-2", barcode="ADV-BAR-2", woo_id=9202, product_id=8202)
    created = client.post("/api/routes/commit", json=route_payload([first["id"], second["id"]])).json()
    route_id = created["route_id"]
    detail = client.get(f"/api/routes/{route_id}").json()
    stop_ids = [stop["id"] for stop in detail["stops"]]

    metadata = client.patch(f"/api/routes/{route_id}", json={"route_name": "Edited Route", "driver_name": "Driver 2"})
    reorder = client.post(f"/api/routes/{route_id}/stops/reorder", json={"ordered_stop_ids": list(reversed(stop_ids))})
    invalid_reorder = client.post(f"/api/routes/{route_id}/stops/reorder", json={"ordered_stop_ids": [stop_ids[0]]})
    stop_edit = client.patch(f"/api/routes/{route_id}/stops/{stop_ids[0]}", json={"delivery_notes": "Door", "internal_notes": "Call", "latitude": 51.1, "longitude": -114.1})
    map_payload = client.get(f"/api/routes/{route_id}/map")
    geocode = client.post(f"/api/routes/{route_id}/geocode/preview")
    optimize = client.post(f"/api/routes/{route_id}/optimize/commit")

    assert metadata.json()["route_name"] == "Edited Route"
    assert [stop["id"] for stop in reorder.json()["stops"]] == list(reversed(stop_ids))
    assert invalid_reorder.status_code == 400
    assert stop_edit.status_code == 200
    edited_stop = [stop for stop in stop_edit.json()["stops"] if stop["id"] == stop_ids[0]][0]
    assert edited_stop["delivery_notes"] == "Door"
    assert map_payload.json()["provider_config_public"]["provider"] == "disabled"
    assert geocode.json()["status"] == "disabled"
    assert optimize.json()["status"] == "disabled"
