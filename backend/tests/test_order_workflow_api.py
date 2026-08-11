from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.orders import Order, OrderItem
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def sync_auto_allocated_order(client, monkeypatch, sku="WORKFLOW-SKU", barcode="WORKFLOW-BAR", woo_id=850, product_id=850, stock=6, allocated=1, quantity=2):
    seed_item(client, sku=sku, Barcode=barcode, wooProductId=product_id, **{"In Stock": stock, "Allocated": allocated})
    patch_woo_order_client(
        monkeypatch,
        [
            woo_order(
                id=woo_id,
                number=str(woo_id),
                line_items=[
                    {
                        **woo_order()["line_items"][0],
                        "id": woo_id + 1000,
                        "product_id": product_id,
                        "sku": sku,
                        "quantity": quantity,
                        "meta_data": [{"key": "barcode", "value": barcode}],
                    }
                ],
            )
        ],
    )
    response = client.post("/api/integrations/woocommerce/orders/quick-sync", json={})
    assert response.status_code == 200, response.text
    order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == woo_id][0]
    return client.get(f"/api/orders/{order['id']}").json()


def test_order_views_show_auto_allocated_order_in_open_and_pick_not_allocate(client, monkeypatch):
    order = sync_auto_allocated_order(client, monkeypatch)

    open_orders = client.get("/api/orders/open").json()["orders"]
    pick_orders = client.get("/api/orders/pick").json()["orders"]
    allocate_orders = client.get("/api/orders/allocate").json()["orders"]
    workflow = client.get(f"/api/orders/{order['id']}/workflow").json()

    assert order["id"] in {row["id"] for row in open_orders}
    open_order = next(row for row in open_orders if row["id"] == order["id"])
    assert open_order["ship_from"] == "Main Warehouse"
    assert open_order["item_names"]
    assert open_order["total_quantity_fulfilled"] == 0
    assert order["id"] in {row["id"] for row in pick_orders}
    assert order["id"] not in {row["id"] for row in allocate_orders}
    assert workflow["workflow"]["shows_in_open_orders"] is True
    assert workflow["workflow"]["shows_in_pick_orders"] is True
    assert workflow["workflow"]["shows_in_allocate"] is False


def test_non_inventory_lines_do_not_enter_allocate_or_pick(client, monkeypatch):
    seed_item(client, sku="SERVICE-SKU", Barcode="SERVICE-BAR", wooProductId=849, nonInventory=True)
    patch_woo_order_client(
        monkeypatch,
        [
            woo_order(
                id=849,
                number="SERVICE-ORDER",
                line_items=[{
                    **woo_order()["line_items"][0],
                    "id": 1849,
                    "product_id": 849,
                    "sku": "SERVICE-SKU",
                    "quantity": 1,
                    "meta_data": [{"key": "barcode", "value": "SERVICE-BAR"}],
                }],
            )
        ],
    )
    assert client.post("/api/integrations/woocommerce/orders/quick-sync", json={}).status_code == 200

    order = next(row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_number"] == "SERVICE-ORDER")
    workflow = client.get(f"/api/orders/{order['id']}/workflow").json()["workflow"]

    assert workflow["shows_in_allocate"] is False
    assert workflow["shows_in_pick_orders"] is False
    assert order["id"] not in {row["id"] for row in client.get("/api/orders/allocate").json()["orders"]}
    assert order["id"] not in {row["id"] for row in client.get("/api/orders/pick").json()["orders"]}


def test_allocation_exceptions_are_stably_paginated_and_exported_in_full(client):
    item = seed_item(client, sku="ALLOC-PAGE-SKU", Barcode="ALLOC-PAGE-BAR", wooProductId=848, **{"In Stock": 0, "Allocated": 0})
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        for index in range(1, 22):
            order = Order(
                woo_order_id=8400 + index,
                woo_order_number="ALLOC%1" if index == 1 else f"ALLOC-PAGE-{index}",
                woo_status="processing",
                local_status="open",
                completion_status="open",
                customer_name=f"Customer {index}",
            )
            db.add(order)
            db.flush()
            db.add(OrderItem(
                order_id=order.id,
                inventory_item_id=item["id"],
                line_number=index,
                sku="ALLOC-PAGE-SKU",
                barcode="ALLOC-PAGE-BAR",
                name=f"Allocation item {index}",
                quantity_ordered=1,
                quantity_allocated=0,
                quantity_picked=0,
                quantity_fulfilled=0,
                quantity_stock_reduced=0,
                matched_status="matched",
                allocation_status="unallocated",
            ))
        db.commit()
    finally:
        db_override.close()

    default_page = client.get("/api/allocations/exceptions").json()
    pages = [
        client.get("/api/allocations/exceptions", params={"page": page, "page_size": 10}).json()
        for page in range(1, 4)
    ]

    assert default_page["returned_count"] == 20
    assert pages[0]["total_lines"] == 21
    assert pages[0]["total_orders"] == 21
    assert pages[0]["total_item_groups"] == 1
    assert pages[0]["total_pages"] == 3
    assert pages[2]["returned_count"] == 1
    line_ids = [line["order_line_id"] for page in pages for line in page["lines"]]
    assert len(line_ids) == len(set(line_ids)) == 21

    grouped_items = client.get(
        "/api/allocations/exceptions",
        params={"view": "items", "page": 1, "page_size": 10},
    ).json()
    assert grouped_items["view"] == "items"
    assert grouped_items["total_item_groups"] == 1
    assert grouped_items["returned_item_groups"] == 1
    assert grouped_items["returned_count"] == 1
    assert grouped_items["lines"] == []
    assert len(grouped_items["item_groups"]) == 1
    assert grouped_items["item_groups"][0]["affected_order_count"] == 21
    assert grouped_items["item_groups"][0]["quantity_unallocated"] == 21

    affected_pages = [
        client.get(
            "/api/allocations/exceptions",
            params={"view": "orders", "item_id": item["id"], "page": page, "page_size": 10},
        ).json()
        for page in range(1, 4)
    ]
    affected_line_ids = [line["order_line_id"] for page in affected_pages for line in page["lines"]]
    assert affected_pages[0]["total_lines"] == 21
    assert [page["returned_count"] for page in affected_pages] == [10, 10, 1]
    assert len(affected_line_ids) == len(set(affected_line_ids)) == 21

    invalid_group = client.get(
        "/api/allocations/exceptions",
        params={"item_id": item["id"], "unmatched_line_id": affected_line_ids[0]},
    )
    assert invalid_group.status_code == 422

    literal_percent = client.get("/api/allocations/exceptions", params={"search": "%"}).json()
    assert [line["woo_order_number"] for line in literal_percent["lines"]] == ["ALLOC%1"]
    export = client.get("/api/allocations/exceptions/export").text
    assert "ALLOC%1" in export
    assert "ALLOC-PAGE-21" in export


def test_complete_picked_order_does_not_reduce_stock_again(client, monkeypatch):
    settings = get_settings().model_copy(update={"woocommerce_writeback_dry_run": False})
    monkeypatch.setattr("app.api.routes.orders.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.routes.orders.WooCommerceClient.guarded_write",
        lambda self, operation_type, method, path, payload: {"id": 851, "status": payload["status"]},
    )
    order = sync_auto_allocated_order(client, monkeypatch, sku="COMPLETE-PICK-SKU", barcode="COMPLETE-PICK-BAR", woo_id=851, product_id=851)
    pick = client.post("/api/picks/commit", json={"idempotency_key": "workflow-complete-pick", "order_ids": [order["id"]], "allow_partial": True})
    assert pick.json()["status"] == "posted"
    before = client.get("/api/items", params={"sku": "COMPLETE-PICK-SKU"}).json()["items"][0]

    complete = client.post(f"/api/orders/{order['id']}/complete/commit", json={"completion_mode": "complete"})

    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert complete.json()["woo_writeback_queue_id"]
    assert complete.json()["woo_sync_status"] == "sent"
    after = client.get("/api/items", params={"sku": "COMPLETE-PICK-SKU"}).json()["items"][0]
    assert after["In Stock"] == before["In Stock"] == 4
    assert after["Allocated"] == before["Allocated"] == 1
    assert order["id"] not in {row["id"] for row in client.get("/api/orders/open").json()["orders"]}
    assert order["id"] in {row["id"] for row in client.get("/api/orders/completed").json()["orders"]}
    assert client.get("/api/stock-movements", params={"movement_type": "pick_stock_reduction"}).json()["total"] == 1


def test_picked_completion_fails_closed_when_any_inventory_line_is_not_fully_picked(client, monkeypatch):
    order = sync_auto_allocated_order(client, monkeypatch, sku="INCOMPLETE-PICK-SKU", barcode="INCOMPLETE-PICK-BAR", woo_id=859, product_id=859, quantity=2)

    response = client.post(f"/api/orders/{order['id']}/complete/commit", json={"completion_mode": "complete_picked"})

    assert response.status_code == 400
    assert "fully picked" in response.text
    assert client.get(f"/api/orders/{order['id']}").json()["local_status"] != "completed"


def test_picked_completion_fails_closed_for_order_without_inventory_lines(client):
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        order = Order(order_number="EMPTY-PICKED", local_status="picked", woo_status="processing")
        db.add(order)
        db.commit()
        order_id = order.id
    finally:
        db_override.close()

    response = client.post(
        f"/api/orders/{order_id}/complete/commit",
        json={"completion_mode": "complete_picked", "queue_woo_status_update": False},
    )

    assert response.status_code == 400
    assert "at least one inventory line" in response.text


def test_historical_snapshot_cannot_be_completed_directly(client):
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        order = Order(
            order_number="HISTORICAL-SNAPSHOT",
            local_status="completed",
            woo_status="completed",
            is_historical_snapshot=True,
        )
        db.add(order)
        db.commit()
        order_id = order.id
    finally:
        db_override.close()

    response = client.post(
        f"/api/orders/{order_id}/complete/commit",
        json={"completion_mode": "complete_without_picking", "reason": "Must remain reporting only."},
    )

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_complete_without_picking_releases_allocation_and_does_not_reduce_stock(client, monkeypatch):
    order = sync_auto_allocated_order(client, monkeypatch, sku="NO-PICK-COMPLETE-SKU", barcode="NO-PICK-COMPLETE-BAR", woo_id=852, product_id=852)
    before = client.get("/api/items", params={"sku": "NO-PICK-COMPLETE-SKU"}).json()["items"][0]
    assert before["In Stock"] == 6
    assert before["Allocated"] == 3

    complete = client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={"completion_mode": "complete", "reason": "Customer picked up outside warehouse flow."},
    )

    assert complete.status_code == 200
    assert complete.json()["status"] == "completed_without_picking"
    after = client.get("/api/items", params={"sku": "NO-PICK-COMPLETE-SKU"}).json()["items"][0]
    assert after["In Stock"] == 6
    assert after["Allocated"] == 1
    movements = client.get("/api/stock-movements").json()
    assert movements["total"] == 1
    assert movements["movements"][0]["movement_type"] == "opening_balance_import"
    completed = [row for row in client.get("/api/orders/completed").json()["orders"] if row["id"] == order["id"]][0]
    assert completed["completed_without_picking"] is True
    assert completed["total_quantity_stock_reduced"] == 0


def test_fifo_auto_allocation_gives_oldest_processing_order_first_claim(client, monkeypatch):
    seed_item(client, sku="FIFO-SKU", Barcode="FIFO-BAR", wooProductId=910, **{"In Stock": 3, "Allocated": 0})
    base_line = {
        **woo_order()["line_items"][0],
        "product_id": 910,
        "sku": "FIFO-SKU",
        "quantity": 2,
        "meta_data": [{"key": "barcode", "value": "FIFO-BAR"}],
    }
    newest = woo_order(id=911, number="NEWER", date_created_gmt="2026-07-07T12:00:00", line_items=[{**base_line, "id": 9911}])
    oldest = woo_order(id=910, number="OLDER", date_created_gmt="2026-07-07T10:00:00", line_items=[{**base_line, "id": 9910}])
    patch_woo_order_client(monkeypatch, [newest, oldest])

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    orders = {row["woo_order_number"]: row for row in client.get("/api/orders/open").json()["orders"]}
    older = client.get(f"/api/orders/{orders['OLDER']['id']}").json()
    newer = client.get(f"/api/orders/{orders['NEWER']['id']}").json()
    assert older["lines"][0]["quantity_allocated"] == 2
    assert newer["lines"][0]["quantity_allocated"] == 1
    assert newer["lines"][0]["remaining_to_allocate"] == 1
    pick_numbers = {row["woo_order_number"] for row in client.get("/api/orders/pick").json()["orders"]}
    assert "OLDER" in pick_numbers
    assert "NEWER" not in pick_numbers
    exceptions = client.get("/api/allocations/exceptions").json()
    assert [(row["woo_order_number"], row["quantity_unallocated"]) for row in exceptions["lines"]] == [("NEWER", 1)]
    filtered = client.get(
        "/api/allocations/exceptions",
        params={"search": "FIFO-BAR", "ordered_from": "2026-07-07", "ordered_to": "2026-07-07"},
    )
    assert filtered.status_code == 200
    assert [row["woo_order_number"] for row in filtered.json()["lines"]] == ["NEWER"]


def test_fifo_virtual_stock_ledger_prevents_two_same_sku_lines_from_overallocating(client, monkeypatch):
    seed_item(client, sku="SAME-SKU", Barcode="SAME-BAR", wooProductId=915, **{"In Stock": 3, "Allocated": 0})
    base_line = {
        **woo_order()["line_items"][0],
        "product_id": 915,
        "sku": "SAME-SKU",
        "quantity": 2,
        "meta_data": [{"key": "barcode", "value": "SAME-BAR"}],
    }
    patch_woo_order_client(
        monkeypatch,
        [
            woo_order(
                id=915,
                number="SAME-LINES",
                line_items=[{**base_line, "id": 9915}, {**base_line, "id": 9916}],
            )
        ],
    )

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200, response.text
    order = next(row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_number"] == "SAME-LINES")
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert [line["quantity_allocated"] for line in detail["lines"]] == [2, 1]
    assert detail["pick_status"] == "not_ready"
    assert detail["shows_in_allocate"] is True
    assert detail["shows_in_pick_orders"] is False
    item = client.get("/api/items", params={"sku": "SAME-SKU"}).json()["items"][0]
    assert item["Allocated"] == 3
    assert item["Sellable"] == 0


def test_stock_adjustment_retries_fifo_waiting_orders_and_auto_endpoint_is_idempotent(client, monkeypatch):
    item = seed_item(client, sku="RESTOCK-SKU", Barcode="RESTOCK-BAR", wooProductId=920, **{"In Stock": 0, "Allocated": 0})
    base_line = {
        **woo_order()["line_items"][0],
        "product_id": 920,
        "sku": "RESTOCK-SKU",
        "quantity": 2,
        "meta_data": [{"key": "barcode", "value": "RESTOCK-BAR"}],
    }
    orders = [
        woo_order(id=921, number="RESTOCK-NEW", date_created_gmt="2026-07-07T12:00:00", line_items=[{**base_line, "id": 9921}]),
        woo_order(id=920, number="RESTOCK-OLD", date_created_gmt="2026-07-07T10:00:00", line_items=[{**base_line, "id": 9920}]),
    ]
    patch_woo_order_client(monkeypatch, orders)
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    location = client.get("/api/inventory/locations", params={"item_id": item["id"]}).json()["rows"][0]

    adjustment = client.post(
        "/api/inventory/adjustments",
        json={
            "idempotency_key": "fifo-restock-adjustment",
            "adjustment_type": "manual_increase",
            "reason": "FIFO restock test",
            "created_by": "pytest",
            "lines": [{"item_id": item["id"], "inventory_item_location_id": location["id"], "new_quantity": 3}],
        },
    )

    assert adjustment.status_code == 201, adjustment.text
    open_orders = {row["woo_order_number"]: row for row in client.get("/api/orders/open").json()["orders"]}
    old_detail = client.get(f"/api/orders/{open_orders['RESTOCK-OLD']['id']}").json()
    new_detail = client.get(f"/api/orders/{open_orders['RESTOCK-NEW']['id']}").json()
    assert old_detail["lines"][0]["quantity_allocated"] == 2
    assert new_detail["lines"][0]["quantity_allocated"] == 1
    before = client.get("/api/items", params={"sku": "RESTOCK-SKU"}).json()["items"][0]["Allocated"]
    rerun = client.post("/api/allocations/auto/commit")
    after = client.get("/api/items", params={"sku": "RESTOCK-SKU"}).json()["items"][0]["Allocated"]
    assert rerun.status_code == 200
    assert rerun.json()["total_quantity_allocated"] == 0
    assert after == before == 3


def test_bulk_complete_marks_selected_open_orders_completed(client, monkeypatch):
    settings = get_settings().model_copy(update={"woocommerce_writeback_dry_run": False})
    monkeypatch.setattr("app.api.routes.orders.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.routes.orders.WooCommerceClient.guarded_write",
        lambda self, operation_type, method, path, payload: {"id": 852, "status": payload["status"]},
    )
    order = sync_auto_allocated_order(client, monkeypatch, sku="BULK-COMPLETE-SKU", barcode="BULK-COMPLETE-BAR", woo_id=852, product_id=852)

    response = client.post("/api/orders/bulk/complete", json={"order_ids": [order["id"]], "reason": "Bulk completion test"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 0
    assert body["results"][0]["woo_writeback_queue_id"]
    assert body["results"][0]["woo_sync_status"] == "sent"
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["completion_status"] == "completed_without_picking"
    assert detail["shows_in_open_orders"] is False


def test_pending_order_never_reserves_stock_or_enters_operational_queues(client, monkeypatch):
    seed_item(client, sku="PENDING-SKU", Barcode="PENDING-BAR", wooProductId=930, **{"In Stock": 4, "Allocated": 0})
    pending_line = {
        **woo_order()["line_items"][0],
        "product_id": 930,
        "sku": "PENDING-SKU",
        "meta_data": [{"key": "barcode", "value": "PENDING-BAR"}],
    }
    patch_woo_order_client(monkeypatch, [woo_order(id=930, number="PENDING", status="pending", line_items=[pending_line])])

    client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["pending"]})

    item = client.get("/api/items", params={"sku": "PENDING-SKU"}).json()["items"][0]
    assert item["Allocated"] == 0
    assert client.get("/api/orders/open").json()["total"] == 0
    assert client.get("/api/orders/allocate").json()["total"] == 0
    assert client.get("/api/orders/pick").json()["total"] == 0


def test_cancelled_order_releases_stock_to_next_fifo_processing_order(client, monkeypatch):
    seed_item(client, sku="CANCEL-SKU", Barcode="CANCEL-BAR", wooProductId=940, **{"In Stock": 2, "Allocated": 0})
    base_line = {
        **woo_order()["line_items"][0],
        "product_id": 940,
        "sku": "CANCEL-SKU",
        "quantity": 2,
        "meta_data": [{"key": "barcode", "value": "CANCEL-BAR"}],
    }
    older = woo_order(id=940, number="CANCEL-OLD", date_created_gmt="2026-07-07T10:00:00", line_items=[{**base_line, "id": 9940}])
    newer = woo_order(id=941, number="CANCEL-NEXT", date_created_gmt="2026-07-07T11:00:00", line_items=[{**base_line, "id": 9941}])
    fake = patch_woo_order_client(monkeypatch, [newer, older])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    before = {row["woo_order_number"]: row for row in client.get("/api/orders/open").json()["orders"]}
    assert client.get(f"/api/orders/{before['CANCEL-OLD']['id']}").json()["lines"][0]["quantity_allocated"] == 2
    assert client.get(f"/api/orders/{before['CANCEL-NEXT']['id']}").json()["lines"][0]["quantity_allocated"] == 0

    fake.orders = [{**older, "status": "cancelled", "date_modified_gmt": "2026-07-07T13:00:00"}]
    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["cancelled"]})

    assert response.status_code == 200
    remaining = {row["woo_order_number"]: row for row in client.get("/api/orders/open").json()["orders"]}
    assert "CANCEL-OLD" not in remaining
    next_detail = client.get(f"/api/orders/{remaining['CANCEL-NEXT']['id']}").json()
    assert next_detail["lines"][0]["quantity_allocated"] == 2
    item = client.get("/api/items", params={"sku": "CANCEL-SKU"}).json()["items"][0]
    assert item["Allocated"] == 2
