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


def test_order_commit_creates_local_order_lines_only(client, monkeypatch):
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
    assert detail["local_status"] == "open"
    assert detail["lines"][0]["item_id"] == created_item["id"]
    assert detail["lines"][0]["quantity_allocated"] == 0
    assert detail["lines"][0]["quantity_picked"] == 0
    assert detail["lines"][0]["sellable_snapshot"] == 5
    item = client.get("/api/items", params={"sku": "ORDER-SKU"}).json()["items"][0]
    assert item["In Stock"] == 6
    assert item["Allocated"] == 1
    assert client.get("/api/stock-movements").json()["total"] == 0
    assert fake.write_called is False


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


def test_order_commit_skips_non_open_status(client, monkeypatch):
    patch_woo_order_client(monkeypatch, [woo_order(status="completed")])

    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["completed"]})

    assert response.status_code == 200
    assert response.json()["skipped_count"] == 1
    assert client.get("/api/orders/open").json()["total"] == 0
