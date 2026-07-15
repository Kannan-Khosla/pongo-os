from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base
from app.models.woocommerce import WooCommerceSyncRun
from app.services.woocommerce_orders import (
    POSTGRES_ORDER_IMPORT_LOCK_KEY,
    acquire_order_import_transaction_lock,
    commit_remote_order_records,
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
    assert client.get("/api/stock-movements").json()["total"] == 0


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


def test_order_commit_creates_local_order_lines_and_auto_allocates(client, monkeypatch):
    created_item = seed_item(client, sku="ORDER-SKU", Barcode="ORDER-BAR", wooProductId=101, **{"In Stock": 6, "Allocated": 1})
    fake = patch_woo_order_client(monkeypatch, [woo_order()])

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
    assert detail["lines"][0]["item_id"] == created_item["id"]
    assert detail["lines"][0]["quantity_allocated"] == 2
    assert detail["lines"][0]["quantity_picked"] == 0
    assert detail["lines"][0]["quantity_stock_reduced"] == 0
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 3
    assert client.get("/api/stock-movements").json()["total"] == 0
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


def test_quantity_decrease_below_allocated_flags_review_without_deallocating(client, monkeypatch):
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
    assert body["status"] == "completed_with_errors"
    assert body["error_count"] == 1
    assert body["allocation_exception_count"] == 1
    assert "allocation was preserved and requires review" in body["errors"][0]
    detail = client.get(f"/api/orders/{order['id']}").json()
    line = detail["lines"][0]
    assert line["quantity_ordered"] == 1
    assert line["quantity_allocated"] == 2
    assert line["allocation_status"] == "exception"
    assert line["allocation_exception_reason"] == "woo_quantity_below_allocated"
    assert line["sync_status"] == "needs_review"
    assert "requires review" in line["sync_error"]
    assert detail["allocation_status"] == "exception"
    assert detail["allocation_exception_reason"] == "woo_quantity_below_allocated"
    assert detail["can_pick"] is False
    assert order["id"] in {row["id"] for row in client.get("/api/orders/allocate").json()["orders"]}
    assert order["id"] not in {row["id"] for row in client.get("/api/orders/pick").json()["orders"]}
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 10
    assert item["Allocated"] == 2
    assert client.get("/api/allocations").json()["total"] == 1
    assert client.get("/api/stock-movements").json()["total"] == 0


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
    barcode_search = client.get("/api/orders/open", params={"search": "7896432"}).json()

    assert barcode_search["total"] == 1
    detail = client.get(f"/api/orders/{barcode_search['orders'][0]['id']}").json()
    assert detail["lines"][0]["sku"] == "LOCAL-ORDER-SKU"
    assert detail["lines"][0]["barcode"] == "7896432"


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
