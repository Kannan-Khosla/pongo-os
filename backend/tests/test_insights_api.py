from tests.test_items_api import client, seed_item  # noqa: F401


class FakeWooOrderClient:
    configured = True

    def __init__(self, orders):
        self.orders = orders
        self.write_called = False

    def fetch_all_orders(self, statuses=None, limit=None, after=None, before=None, modified_after=None, modified_before=None):
        rows = [order for order in self.orders if not statuses or order["status"] in statuses]
        return rows[:limit] if limit else rows

    def check_connection(self):
        return None


def patch_woo_orders(monkeypatch, orders):
    fake = FakeWooOrderClient(orders)
    monkeypatch.setattr("app.api.routes.woocommerce.create_woocommerce_client", lambda: fake)
    return fake


def woo_order(order_id, email, sku, total, created, status="processing", city="Calgary", postal="T2X", payment="stripe", quantity=2, coupons=None):
    return {
        "id": order_id,
        "number": str(order_id),
        "status": status,
        "currency": "CAD",
        "customer_id": order_id,
        "billing": {"first_name": "Avery", "last_name": "Stone", "email": email, "phone": "555-0100", "city": city, "postcode": postal, "country": "CA"},
        "shipping": {"first_name": "Avery", "last_name": "Stone", "address_1": "1 Main St", "city": city, "postcode": postal, "country": "CA"},
        "payment_method": payment,
        "payment_method_title": payment.title(),
        "discount_total": "5.00" if coupons else "0.00",
        "shipping_total": "0.00",
        "total_tax": "0.00",
        "total": str(total),
        "date_created_gmt": created,
        "date_modified_gmt": created,
        "coupon_lines": coupons or [],
        "line_items": [
            {
                "id": order_id * 10,
                "product_id": 101,
                "variation_id": 0,
                "sku": sku,
                "name": f"{sku} Item",
                "quantity": quantity,
                "price": str(float(total) / quantity),
                "subtotal": str(total),
                "total": str(total),
                "total_tax": "0.00",
                "meta_data": [{"key": "barcode", "value": f"{sku}-BAR"}],
            }
        ],
    }


def seed_insight_orders(client, monkeypatch):
    seed_item(client, sku="DOG-FOOD", Brand="Acana", Category="Dog Food", **{"In Stock": 12, "Allocated": 2, "Unit Cost": 10, "Par Level": 8, "Default Lead Time Days": 5})
    seed_item(client, sku="CAT-TOY", Brand="Kong", Category="Cat Toys", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 3, "Par Level": 4, "Default Lead Time Days": 7})
    orders = [
        woo_order(701, "repeat@example.invalid", "DOG-FOOD", "40.00", "2026-06-01T12:00:00", quantity=2, coupons=[{"code": "WELCOME", "discount": "5.00"}]),
        woo_order(702, "repeat@example.invalid", "DOG-FOOD", "50.00", "2026-06-20T12:00:00", quantity=2),
        woo_order(703, "new@example.invalid", "CAT-TOY", "12.00", "2026-06-21T12:00:00", quantity=1, payment="cod"),
        woo_order(704, "new@example.invalid", "DOG-FOOD", "40.00", "2026-06-21T12:15:00", status="failed", quantity=1, payment="stripe"),
    ]
    fake = patch_woo_orders(monkeypatch, orders)
    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing", "failed"], "limit": 100})
    assert response.status_code == 200, response.text
    assert fake.write_called is False
    return fake


def test_insights_overview_returns_clean_empty_state(client):
    response = client.get("/api/insights/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["dashboard"] == "overview"
    assert body["summary"]["total_orders"] == 0
    assert any(warning["code"] == "limited_order_history" for warning in body["data_quality"])


def test_insights_orders_revenue_calculates_aov(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/orders-revenue").json()

    assert body["summary"]["total_orders"] == 3
    assert body["summary"]["average_order_value"] == 34
    assert body["rows"]


def test_insights_customer_metrics_calculates_new_and_returning(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/customer-metrics").json()

    assert body["summary"]["total_customers"] == 2
    assert body["summary"]["returning_customers"] == 1
    assert body["summary"]["new_customers"] == 1


def test_insights_customer_segmentation_returns_segment_counts(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/customer-segmentation").json()

    assert body["summary"]["segment_counts"]
    assert body["tables"]["segments"]


def test_insights_product_sku_returns_sku_metrics(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/product-sku").json()

    skus = {row["sku"] for row in body["rows"]}
    assert "DOG-FOOD" in skus
    assert body["summary"]["units_sold"] >= 5


def test_insights_subscriptions_empty_state(client):
    body = client.get("/api/insights/subscriptions").json()

    assert body["empty_state"] == "No subscription data synced yet"
    assert any(warning["code"] == "missing_subscription_data" for warning in body["data_quality"])


def test_insights_subscription_products_empty_state(client):
    body = client.get("/api/insights/subscription-products").json()

    assert body["empty_state"] == "No subscription data synced yet"
    assert body["rows"] == []


def test_insights_inventory_forecasting_calculates_days_left(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/inventory-forecasting").json()
    dog = next(row for row in body["rows"] if row["sku"] == "DOG-FOOD")

    assert dog["daily_velocity"] > 0
    assert dog["days_of_stock_left"] is not None


def test_insights_coupons_returns_warning_or_coupon_data(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/coupons").json()

    assert "coupon_discount_total" in body["summary"]
    assert body["rows"] or any(warning["code"] == "missing_coupon_data" for warning in body["data_quality"])


def test_insights_payment_health_groups_methods(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/payment-health").json()

    methods = {row["payment_method"] for row in body["rows"]}
    assert "Stripe" in methods
    assert "Cod" in methods


def test_insights_geography_groups_city_postal(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/geography").json()

    assert body["rows"][0]["city"] == "Calgary"
    assert body["rows"][0]["postal_code"] == "T2X"


def test_insights_product_affinity_empty_or_pairs(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/product-affinity").json()

    assert body["dashboard"] == "product-affinity"
    assert "rows" in body


def test_insights_reorder_forecast_returns_candidates_or_empty(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/reorder-forecast").json()

    assert body["dashboard"] == "reorder-forecast"
    assert body["rows"] or body["empty_state"]


def test_insights_export_endpoints_return_csv(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    response = client.get("/api/insights/orders-revenue/export")

    assert response.status_code == 200
    assert "date,order_count,gross_sales,net_sales,units_sold" in response.text.splitlines()[0]


def test_insights_endpoints_do_not_mutate_inventory_or_orders(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "DOG-FOOD"}).json()["items"][0]
    before_orders = client.get("/api/orders/open").json()["total"]

    for endpoint in [
        "overview",
        "orders-revenue",
        "customer-metrics",
        "customer-segmentation",
        "product-sku",
        "subscriptions",
        "subscription-products",
        "inventory-forecasting",
        "coupons",
        "payment-health",
        "geography",
        "product-affinity",
        "reorder-forecast",
    ]:
        assert client.get(f"/api/insights/{endpoint}").status_code == 200

    after_item = client.get("/api/items", params={"sku": "DOG-FOOD"}).json()["items"][0]
    after_orders = client.get("/api/orders/open").json()["total"]
    assert after_item["In Stock"] == before_item["In Stock"]
    assert after_item["Allocated"] == before_item["Allocated"]
    assert after_orders == before_orders
