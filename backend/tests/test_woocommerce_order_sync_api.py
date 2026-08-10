from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.models import Base
from app.models.orders import Order
from app.models.woocommerce import WooCommerceSyncRun
from app.services import woocommerce_orders as order_service
from app.services.woocommerce_orders import (
    POSTGRES_ORDER_IMPORT_LOCK_KEY,
    acquire_order_import_transaction_lock,
    commit_remote_order_records,
    count_pick_ready_operational_orders,
)
from tests.test_items_api import client, seed_item  # noqa: F401


class FakeWooOrderClient:
    configured = True

    def __init__(self, orders=None):
        self.orders = orders or []
        self.write_called = False
        self.last_statuses = None

    def fetch_all_orders(self, statuses=None, limit=None, after=None, before=None, modified_after=None, modified_before=None):
        self.last_statuses = statuses
        rows = [order for order in self.orders if not statuses or order["status"] in statuses]
        return rows[:limit] if limit else rows

    def list_orders(self, page=1, per_page=None, status=None, after=None, before=None, modified_after=None, modified_before=None):
        self.last_statuses = [status] if status else None
        rows = [order for order in self.orders if not status or order["status"] == status]
        return rows[:per_page] if per_page else rows

    def check_connection(self):
        return None


def patch_woo_order_client(monkeypatch, orders):
    fake = FakeWooOrderClient(orders)
    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: fake)
    return fake


def woo_order(**overrides):
    order = {
        "id": 501,
        "number": "1001",
        "status": "processing",
        "currency": "CAD",
        "customer_id": 33,
        "billing": {
            "first_name": "Avery",
            "last_name": "Stone",
            "email": "avery@example.invalid",
            "phone": "555-0100",
            "city": "Calgary",
            "state": "AB",
            "postcode": "T2X",
            "country": "CA",
        },
        "shipping": {
            "first_name": "Avery",
            "last_name": "Stone",
            "address_1": "1 Main St",
            "city": "Calgary",
            "state": "AB",
            "postcode": "T2X",
            "country": "CA",
        },
        "payment_method": "cod",
        "payment_method_title": "Cash on delivery",
        "discount_total": "0.00",
        "shipping_total": "5.00",
        "total_tax": "1.00",
        "total": "30.00",
        "date_created_gmt": "2026-07-07T12:00:00",
        "date_modified_gmt": "2026-07-07T12:30:00",
        "line_items": [
            {
                "id": 9001,
                "product_id": 101,
                "variation_id": 0,
                "sku": "ORDER-SKU",
                "name": "Order Item",
                "quantity": 2,
                "price": "12.00",
                "subtotal": "24.00",
                "total": "24.00",
                "total_tax": "1.00",
                "meta_data": [{"key": "barcode", "value": "ORDER-BAR"}],
            }
        ],
    }
    order.update(overrides)
    return order


def test_commit_remote_order_records_can_leave_transaction_to_caller():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        sync_run, response = commit_remote_order_records(db, [], [], "pytest", commit=False)

        assert sync_run.id is not None
        assert response.total_remote_records == 0
        assert db.in_transaction() is True
        db.rollback()
        assert list(db.scalars(select(WooCommerceSyncRun)).all()) == []


def test_postgres_order_import_lock_uses_transaction_advisory_lock():
    class FakeSession:
        def __init__(self):
            self.calls = []

        def get_bind(self):
            return type("Bind", (), {"dialect": type("Dialect", (), {"name": "postgresql"})()})()

        def execute(self, statement, params):
            self.calls.append((str(statement), params))

    db = FakeSession()

    acquire_order_import_transaction_lock(db)

    assert db.calls == [
        ("SELECT pg_advisory_xact_lock(:lock_key)", {"lock_key": POSTGRES_ORDER_IMPORT_LOCK_KEY})
    ]


def test_pick_ready_operational_count_uses_one_database_aggregate():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _connection, _cursor, statement, _parameters, _context, _executemany: statements.append(statement),
    )

    with Session(engine) as db:
        db.add_all([
            Order(woo_order_id=1, woo_status="processing", pick_status="ready_to_pick", is_historical_snapshot=False),
            Order(woo_order_id=2, woo_status="processing", pick_status="partially_picked", is_historical_snapshot=False),
            Order(woo_order_id=3, woo_status="processing", pick_status="picked", is_historical_snapshot=False),
            Order(woo_order_id=4, woo_status="processing", pick_status="not_ready", is_historical_snapshot=False),
            Order(woo_order_id=5, woo_status="processing", pick_status="ready_to_pick", is_historical_snapshot=True),
            Order(woo_order_id=6, woo_status="cancelled", pick_status="ready_to_pick", is_historical_snapshot=False),
            Order(woo_order_id=7, woo_status="completed", payment_method="FooSales POS", pick_status="ready_to_pick", is_historical_snapshot=False),
        ])
        db.commit()
        statements.clear()

        assert count_pick_ready_operational_orders(db) == 4

    assert len(statements) == 1
    assert "count(" in statements[0].lower()
    assert "order_items" not in statements[0].lower()


def test_order_preview_matches_lines_and_does_not_write_or_allocate(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 6, "Allocated": 1})
    patch_woo_order_client(monkeypatch, [woo_order()])

    response = client.post("/api/integrations/woocommerce/orders/preview", json={"include_statuses": ["processing", "on-hold"], "limit": 100})

    assert response.status_code == 200
    body = response.json()
    assert body["total_remote_records"] == 1
    assert body["create_count"] == 1
    assert body["matched_count"] == 1
    assert body["available_count"] == 1
    line = body["preview_orders"][0]["lines"][0]
    assert line["matched_status"] == "matched"
    assert line["availability_status"] == "available"
    assert line["sellable_snapshot"] == 5
    assert client.get("/api/orders/open").json()["total"] == 0
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 1
    movements = client.get("/api/stock-movements").json()
    assert movements["total"] == 1
    assert movements["movements"][0]["movement_type"] == "opening_balance_import"


def test_order_preview_reports_unmatched_and_shortage(client, monkeypatch):
    patch_woo_order_client(monkeypatch, [woo_order(line_items=[{**woo_order()["line_items"][0], "sku": "MISSING", "meta_data": []}])])

    response = client.post("/api/integrations/woocommerce/orders/preview", json={})

    line = response.json()["preview_orders"][0]["lines"][0]
    assert line["matched_status"] == "unmatched"
    assert line["availability_status"] == "unknown"
    assert line["shortage_quantity"] == 2
    assert response.json()["error_count"] == 1


def test_order_preview_detects_conflicting_matches(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="SKU-BAR")
    seed_item(client, sku="OTHER-SKU", Barcode="ORDER-BAR")
    patch_woo_order_client(monkeypatch, [woo_order()])

    response = client.post("/api/integrations/woocommerce/orders/preview", json={})

    line = response.json()["preview_orders"][0]["lines"][0]
    assert line["matched_status"] == "conflict"
    assert response.json()["conflict_count"] == 1


def test_order_preview_fails_closed_for_duplicate_sku(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="DUPLICATE-ONE")
    seed_item(client, sku="ORDER-SKU", Barcode="DUPLICATE-TWO")
    order = woo_order(line_items=[{**woo_order()["line_items"][0], "product_id": 0, "variation_id": 0, "meta_data": []}])
    patch_woo_order_client(monkeypatch, [order])

    response = client.post("/api/integrations/woocommerce/orders/preview", json={})

    line = response.json()["preview_orders"][0]["lines"][0]
    assert line["matched_status"] == "conflict"
    assert line["item_id"] is None
    assert "Duplicate SKU" in line["errors"][0]


def test_order_commit_creates_local_order_lines_and_auto_allocates(client, monkeypatch):
    created_item = seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 6, "Allocated": 1})
    fake = patch_woo_order_client(monkeypatch, [woo_order(customer_note="Please leave the order beside the garage.")])

    response = client.post("/api/integrations/woocommerce/orders/commit", json={"created_by": "pytest"})

    assert response.status_code == 200
    body = response.json()
    assert body["sync_run_id"]
    assert body["created_count"] == 1
    open_orders = client.get("/api/orders/open").json()
    assert open_orders["total"] == 1
    order_id = open_orders["orders"][0]["id"]
    detail = client.get(f"/api/orders/{order_id}").json()
    assert detail["woo_order_id"] == 501
    assert detail["woo_order_number"] == "1001"
    assert detail["local_status"] == "allocated"
    assert detail["allocation_status"] == "auto_allocated"
    assert detail["pick_status"] == "ready_to_pick"
    assert detail["customer_note"] == "Please leave the order beside the garage."
    assert detail["lines"][0]["item_id"] == created_item["id"]
    assert detail["lines"][0]["quantity_allocated"] == 2
    assert detail["lines"][0]["quantity_picked"] == 0
    assert detail["lines"][0]["quantity_stock_reduced"] == 0
    assert detail["lines"][0]["unit_price"] == 12
    assert detail["lines"][0]["line_tax"] == 1
    assert detail["lines"][0]["line_total"] == 24
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 3
    movements = client.get("/api/stock-movements").json()
    assert movements["total"] == 1
    assert movements["movements"][0]["movement_type"] == "opening_balance_import"
    assert body["auto_allocated_count"] == 1
    assert body["pick_ready_count"] == 1
    assert fake.write_called is False


def test_quick_order_sync_fetches_recent_orders_per_open_status(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 8, "Allocated": 0})
    orders = [
        woo_order(id=501, number="1001", status="processing", date_modified_gmt="2026-07-07T12:30:00"),
        woo_order(id=502, number="1002", status="processing", date_modified_gmt="2026-07-07T12:20:00"),
        woo_order(id=503, number="1003", status="pending", date_modified_gmt="2026-07-07T12:40:00"),
    ]
    patch_woo_order_client(monkeypatch, orders)

    response = client.post("/api/integrations/woocommerce/orders/quick-sync?per_status_limit=1", json={"include_statuses": ["processing", "pending"], "limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 2
    open_orders = client.get("/api/orders/open").json()["orders"]
    assert {order["woo_order_number"] for order in open_orders} == {"1001"}


def test_order_commit_updates_existing_order_without_duplicate_lines(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order(total="30.00")])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    patch_woo_order_client(monkeypatch, [woo_order(total="35.00")])

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.json()["updated_count"] == 1
    open_orders = client.get("/api/orders/open").json()
    assert open_orders["total"] == 1
    detail = client.get(f"/api/orders/{open_orders['orders'][0]['id']}").json()
    assert detail["total"] == 35
    assert len(detail["lines"]) == 1


def test_processing_resync_does_not_reopen_or_reallocate_locally_completed_order(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = client.get("/api/orders/open").json()["orders"][0]
    assert client.get("/api/allocations").json()["total"] == 1

    completion = client.post(
        f"/api/orders/{order['id']}/complete/commit",
        json={"completion_mode": "complete_without_picking", "reason": "Regression test completion."},
    )
    assert completion.status_code == 200
    assert client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]["Allocated"] == 0

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    assert response.json()["updated_count"] == 1
    assert response.json()["auto_allocated_count"] == 0
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["local_status"] == "completed"
    assert detail["completion_status"] == "completed_without_picking"
    assert detail["completed_without_picking"] is True
    assert order["id"] not in {row["id"] for row in client.get("/api/orders/open").json()["orders"]}
    assert client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]["Allocated"] == 0
    assert client.get("/api/allocations").json()["total"] == 1


def test_quantity_decrease_releases_only_unpicked_excess_and_records_reconciliation(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    fake = patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = client.get("/api/orders/open").json()["orders"][0]
    changed_line = {
        **woo_order()["line_items"][0],
        "quantity": 1,
        "subtotal": "12.00",
        "total": "12.00",
    }
    fake.orders = [woo_order(total="18.00", line_items=[changed_line])]

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["error_count"] == 0
    detail = client.get(f"/api/orders/{order['id']}").json()
    line = detail["lines"][0]
    assert line["quantity_ordered"] == 1
    assert line["quantity_allocated"] == 1
    assert line["allocation_status"] == "allocated"
    assert line["allocation_exception_reason"] is None
    assert detail["allocation_exception_reason"] is None
    assert detail["can_pick"] is True
    assert "released 1.000 unpicked units" in detail["workflow_notes"]
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 10
    assert item["Allocated"] == 1
    assert client.get("/api/allocations").json()["total"] == 1
    assert client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]["Allocated"] == 1


def test_quantity_below_picked_preserves_history_and_blocks_further_picking(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    fake = patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = client.get("/api/orders/open").json()["orders"][0]
    line = client.get(f"/api/orders/{order['id']}").json()["lines"][0]
    picked = client.post(
        "/api/picks/commit",
        json={"idempotency_key": "woo-quantity-change-pick", "lines": [{"order_line_id": line["id"], "quantity_to_pick": 2}], "allow_partial": False},
    )
    assert picked.status_code == 200
    changed_line = {**woo_order()["line_items"][0], "quantity": 1, "subtotal": "12.00", "total": "12.00"}
    fake.orders = [woo_order(total="18.00", line_items=[changed_line])]

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "completed_with_errors"
    detail = client.get(f"/api/orders/{order['id']}").json()
    updated_line = detail["lines"][0]
    assert updated_line["quantity_ordered"] == 1
    assert updated_line["quantity_allocated"] == 2
    assert updated_line["quantity_picked"] == 2
    assert updated_line["quantity_stock_reduced"] == 2
    assert updated_line["allocation_status"] == "exception"
    assert updated_line["allocation_exception_reason"] == "woo_quantity_below_allocated"
    assert "history was preserved" in updated_line["sync_error"]
    assert detail["can_pick"] is False


def test_failed_line_reconciliation_rolls_back_that_order_savepoint(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    fake = patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = client.get("/api/orders/open").json()["orders"][0]
    changed_line = {**woo_order()["line_items"][0], "quantity": 1, "subtotal": "12.00", "total": "12.00"}
    fake.orders = [woo_order(total="18.00", line_items=[changed_line])]
    real_upsert = order_service.upsert_order_lines

    def fail_after_reconciliation(*args, **kwargs):
        real_upsert(*args, **kwargs)
        raise RuntimeError("simulated reconciliation failure")

    monkeypatch.setattr(order_service, "upsert_order_lines", fail_after_reconciliation)

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "completed_with_errors"
    assert response.json()["error_count"] == 1
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["lines"][0]["quantity_ordered"] == 2
    assert detail["lines"][0]["quantity_allocated"] == 2
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["Allocated"] == 2


def test_product_change_on_unpicked_line_moves_reservation_to_new_item(client, monkeypatch):
    first = seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    second = seed_item(client, sku="SECOND-SKU", Barcode="SECOND-BAR", wooProductId=102, **{"In Stock": 10, "Allocated": 0})
    fake = patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = client.get("/api/orders/open").json()["orders"][0]
    changed_line = {
        **woo_order()["line_items"][0],
        "product_id": 102,
        "sku": "SECOND-SKU",
        "name": "Second Item",
        "meta_data": [{"key": "barcode", "value": "SECOND-BAR"}],
    }
    fake.orders = [woo_order(date_modified_gmt="2026-07-07T13:30:00", line_items=[changed_line])]

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    detail = client.get(f"/api/orders/{order['id']}").json()
    assert detail["lines"][0]["item_id"] == second["id"]
    assert detail["lines"][0]["quantity_allocated"] == 2
    assert detail["lines"][0]["allocation_exception_reason"] is None
    assert client.get(f"/api/items/{first['id']}").json()["Allocated"] == 0
    assert client.get(f"/api/items/{second['id']}").json()["Allocated"] == 2
    assert "changed inventory item" in detail["workflow_notes"]


def test_product_change_after_pick_preserves_original_item_history_as_exception(client, monkeypatch):
    first = seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 10, "Allocated": 0})
    second = seed_item(client, sku="SECOND-SKU", Barcode="SECOND-BAR", wooProductId=102, **{"In Stock": 10, "Allocated": 0})
    fake = patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = client.get("/api/orders/open").json()["orders"][0]
    line = client.get(f"/api/orders/{order['id']}").json()["lines"][0]
    client.post(
        "/api/picks/commit",
        json={"idempotency_key": "woo-product-change-pick", "lines": [{"order_line_id": line["id"], "quantity_to_pick": 2}], "allow_partial": False},
    )
    changed_line = {
        **woo_order()["line_items"][0],
        "product_id": 102,
        "sku": "SECOND-SKU",
        "name": "Second Item",
        "meta_data": [{"key": "barcode", "value": "SECOND-BAR"}],
    }
    fake.orders = [woo_order(date_modified_gmt="2026-07-07T13:30:00", line_items=[changed_line])]

    response = client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "completed_with_errors"
    detail = client.get(f"/api/orders/{order['id']}").json()
    updated_line = detail["lines"][0]
    assert updated_line["item_id"] == first["id"]
    assert updated_line["quantity_picked"] == 2
    assert updated_line["quantity_stock_reduced"] == 2
    assert updated_line["allocation_status"] == "exception"
    assert "original item history was preserved" in updated_line["sync_error"]
    assert client.get(f"/api/items/{second['id']}").json()["Allocated"] == 0


def test_open_orders_filters_and_export(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 1, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order()])
    client.post("/api/integrations/woocommerce/orders/commit", json={})

    filtered = client.get("/api/orders/open", params={"availability_status": "partial"})
    exported = client.get("/api/orders/open/export", params={"availability_status": "partial"})

    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert exported.status_code == 200
    assert "Order Number" in exported.text.splitlines()[0]
    assert "1001" in exported.text


def test_open_order_search_uses_order_customer_and_matched_inventory_identifiers(client, monkeypatch):
    seed_item(client, sku="LOCAL-ORDER-SKU", Barcode="7896432", wooProductId=101, **{"In Stock": 4, "Allocated": 0})
    line_without_woo_identifiers = {**woo_order()["line_items"][0], "sku": "", "meta_data": []}
    patch_woo_order_client(monkeypatch, [woo_order(line_items=[line_without_woo_identifiers])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})

    assert client.get("/api/orders/open", params={"search": "1001"}).json()["total"] == 1
    assert client.get("/api/orders/open", params={"search": "Avery Stone"}).json()["total"] == 1
    assert client.get("/api/orders/open", params={"search": "LOCAL-ORDER-SKU"}).json()["total"] == 1
    assert client.get("/api/orders/open", params={"customer": "Avery"}).json()["total"] == 1
    assert client.get("/api/orders/open", params={"containing_item": "LOCAL-ORDER-SKU"}).json()["total"] == 1
    assert client.get("/api/orders/open", params={"warehouse": "Main Warehouse"}).json()["total"] == 1
    barcode_search = client.get("/api/orders/open", params={"search": "7896432"}).json()

    assert barcode_search["total"] == 1
    detail = client.get(f"/api/orders/{barcode_search['orders'][0]['id']}").json()
    assert detail["lines"][0]["sku"] == "LOCAL-ORDER-SKU"
    assert detail["lines"][0]["barcode"] == "7896432"


def test_open_and_pick_order_pagination_preserves_the_complete_stable_queue(client, monkeypatch):
    seed_item(client, sku="PAGE-SKU", Barcode="PAGE-BAR", wooProductId=101, **{"In Stock": 30, "Allocated": 0})
    base_line = {
        **woo_order()["line_items"][0],
        "sku": "PAGE-SKU",
        "quantity": 1,
        "meta_data": [{"key": "barcode", "value": "PAGE-BAR"}],
    }
    orders = [
        woo_order(id=700 + index, number=f"PAGE-{index}", line_items=[{**base_line, "id": 9700 + index}])
        for index in range(1, 22)
    ]
    patch_woo_order_client(monkeypatch, orders)
    assert client.post("/api/integrations/woocommerce/orders/commit", json={}).status_code == 200

    default_open = client.get("/api/orders/open").json()
    first = client.get("/api/orders/open", params={"page": 1, "page_size": 10}).json()
    second = client.get("/api/orders/open", params={"page": 2, "page_size": 10}).json()
    third = client.get("/api/orders/open", params={"page": 3, "page_size": 10}).json()

    assert default_open["page_size"] == 20
    assert default_open["returned_count"] == 20
    assert first["total"] == 21
    assert first["total_pages"] == 3
    assert first["returned_count"] == 10
    assert first["has_previous"] is False
    assert first["has_next"] is True
    assert third["returned_count"] == 1
    assert third["has_next"] is False
    paged_open_ids = [row["id"] for page in (first, second, third) for row in page["orders"]]
    assert len(paged_open_ids) == len(set(paged_open_ids)) == 21

    filtered = client.get(
        "/api/orders/open",
        params={"order_number": "PAGE-3", "page": 1, "page_size": 2},
    ).json()
    assert filtered["total"] == 1
    assert [row["woo_order_number"] for row in filtered["orders"]] == ["PAGE-3"]

    default_pick = client.get("/api/orders/pick").json()
    pick_pages = [
        client.get("/api/orders/pick", params={"page": page, "page_size": 10}).json()
        for page in range(1, 4)
    ]
    paged_pick_ids = [row["id"] for page in pick_pages for row in page["orders"]]
    assert default_pick["returned_count"] == 20
    assert len(paged_pick_ids) == len(set(paged_pick_ids)) == 21
    export = client.get("/api/orders/open/export").text
    assert "PAGE-1" in export
    assert "PAGE-21" in export


def test_paginated_order_queues_extract_shipping_without_loading_raw_payload_blobs(client, monkeypatch):
    seed_item(client, sku="LIGHT-SKU", Barcode="LIGHT-BAR", wooProductId=101, **{"In Stock": 2, "Allocated": 0})
    payload = woo_order(
        id=798,
        number="LIGHT-PAGE",
        shipping_lines=[{"method_title": "Local delivery"}],
        large_unused_payload="x" * 250_000,
        line_items=[{
            **woo_order()["line_items"][0],
            "sku": "LIGHT-SKU",
            "quantity": 1,
            "meta_data": [{"key": "barcode", "value": "LIGHT-BAR"}],
        }],
    )
    patch_woo_order_client(monkeypatch, [payload])
    assert client.post("/api/integrations/woocommerce/orders/commit", json={}).status_code == 200

    statements = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(
        client.test_engine,
        "before_cursor_execute",
        capture_statement,
    )
    try:
        open_orders = client.get("/api/orders/open", params={"page": 1, "page_size": 20}).json()
        pick_orders = client.get("/api/orders/pick", params={"page": 1, "page_size": 20}).json()
        allocation_lines = client.get("/api/allocations/exceptions", params={"page": 1, "page_size": 20}).json()
    finally:
        event.remove(client.test_engine, "before_cursor_execute", capture_statement)

    assert open_orders["orders"][0]["shipping_via"] == "Local delivery"
    assert pick_orders["orders"][0]["shipping_via"] == "Local delivery"
    assert allocation_lines["returned_count"] <= 20
    assert not any("orders.raw_woo_payload AS orders_raw_woo_payload" in statement for statement in statements)


def test_order_queue_membership_uses_line_truth_when_cached_workflow_status_is_stale(client, monkeypatch):
    seed_item(client, sku="STALE-SKU", Barcode="STALE-BAR", wooProductId=101, **{"In Stock": 5, "Allocated": 0})
    line = {
        **woo_order()["line_items"][0],
        "sku": "STALE-SKU",
        "quantity": 1,
        "meta_data": [{"key": "barcode", "value": "STALE-BAR"}],
    }
    patch_woo_order_client(monkeypatch, [woo_order(id=799, number="STALE-STATUS", line_items=[line])])
    assert client.post("/api/integrations/woocommerce/orders/commit", json={}).status_code == 200

    with Session(client.test_engine) as db:
        order = db.scalar(select(Order).where(Order.woo_order_id == 799))
        order.local_status = "completed"
        order.completion_status = "open"
        order.allocation_status = "unallocated"
        order.pick_status = "not_ready"
        db.commit()

    pick = client.get("/api/orders/pick", params={"page": 1, "page_size": 20}).json()
    assert [row["woo_order_number"] for row in pick["orders"]] == ["STALE-STATUS"]
    assert pick["orders"][0]["can_pick"] is True
    assert pick["orders"][0]["local_status"] == "allocated"


def test_order_search_treats_like_metacharacters_as_literal_text(client, monkeypatch):
    seed_item(client, sku="LIKE-SKU", Barcode="LIKE-BAR", wooProductId=101, **{"In Stock": 5, "Allocated": 0})
    base_line = {
        **woo_order()["line_items"][0],
        "sku": "LIKE-SKU",
        "quantity": 1,
        "meta_data": [{"key": "barcode", "value": "LIKE-BAR"}],
    }
    patch_woo_order_client(monkeypatch, [
        woo_order(id=810, number="ABC_1", line_items=[{**base_line, "id": 9810}]),
        woo_order(id=811, number="ABCX1", line_items=[{**base_line, "id": 9811}]),
        woo_order(id=812, number="PCT%1", line_items=[{**base_line, "id": 9812}]),
    ])
    assert client.post("/api/integrations/woocommerce/orders/commit", json={}).status_code == 200

    underscore = client.get("/api/orders/open", params={"order_number": "_"}).json()
    percent = client.get("/api/orders/open", params={"order_number": "%"}).json()

    assert [row["woo_order_number"] for row in underscore["orders"]] == ["ABC_1"]
    assert [row["woo_order_number"] for row in percent["orders"]] == ["PCT%1"]


def test_order_commit_stores_completed_snapshot_without_open_order(client, monkeypatch):
    patch_woo_order_client(monkeypatch, [woo_order(status="completed")])

    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["completed"]})

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    assert response.json()["skipped_count"] == 0
    assert client.get("/api/orders/open").json()["total"] == 0
    dashboard = client.get("/api/business-dashboard/today", params={"date": "2026-07-07"}).json()
    assert dashboard["summary"]["today_orders_count"] == 1
    assert dashboard["summary"]["completed_orders_today"] == 1
    assert dashboard["summary"]["today_revenue"] == 30


def test_completed_foosales_order_enters_normal_pick_workflow(client, monkeypatch):
    seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 6, "Allocated": 0})
    patch_woo_order_client(
        monkeypatch,
        [woo_order(status="completed", payment_method="foosales-stripe-reader", payment_method_title="FooSales POS")],
    )

    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["completed"]})

    assert response.status_code == 200
    assert response.json()["auto_allocated_count"] == 1
    order = client.get("/api/orders/pick").json()["orders"][0]
    assert order["woo_status"] == "completed"
    assert order["local_status"] == "allocated"
    assert client.get(f"/api/orders/{order['id']}").json()["payment_method"] == "foosales-stripe-reader"
