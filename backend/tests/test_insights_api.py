from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryItem
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
    seed_item(client, sku="DOG-FOOD", Description="A deliberately long marketing description that must not replace the concise order-line title", Brand="Acana", Category="Dog Food", **{"In Stock": 12, "Allocated": 2, "Unit Cost": 10, "Par Level": 8, "Default Lead Time Days": 5})
    seed_item(client, sku="CAT-TOY", Brand="Kong", Category="Cat Toys", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 3, "Par Level": 4, "Default Lead Time Days": 7})
    recent = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    orders = [
        woo_order(701, "repeat@example.invalid", "DOG-FOOD", "40.00", (recent - timedelta(days=25)).isoformat(), quantity=2, coupons=[{"code": "WELCOME", "discount": "5.00"}]),
        woo_order(702, "repeat@example.invalid", "DOG-FOOD", "50.00", (recent - timedelta(days=6)).isoformat(), quantity=2),
        woo_order(703, "new@example.invalid", "CAT-TOY", "12.00", (recent - timedelta(days=5)).isoformat(), quantity=1, payment="cod"),
        woo_order(704, "new@example.invalid", "DOG-FOOD", "40.00", (recent - timedelta(days=5, minutes=-15)).isoformat(), status="failed", quantity=1, payment="stripe"),
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
    assert body["summary"]["average_order_value"] is None
    assert body["summary"]["refund_amount"] is None
    assert body["empty_state"] == "No matching completed or active sales orders"
    assert any(warning["code"] == "limited_order_history" for warning in body["data_quality"])


def test_insights_orders_revenue_calculates_aov(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/orders-revenue").json()

    assert body["summary"]["total_orders"] == 3
    assert body["summary"]["average_order_value"] == 34
    assert body["summary"]["refund_amount"] is None
    assert body["summary"]["refund_rate"] is None
    assert {"total_orders", "gross_sales", "net_sales", "average_order_value", "units_sold", "discount_amount"} <= body["summary"].keys()
    assert "gross_revenue" not in body["summary"]
    assert "net_revenue" not in body["summary"]
    assert "total_revenue" not in body["summary"]
    assert "total_sales" not in body["summary"]
    assert "total_units_sold" not in body["summary"]
    assert any(warning["code"] == "missing_refund_data" for warning in body["data_quality"])
    assert body["rows"]


def test_insights_revenue_definitions_exclude_shipping_and_tax(client, monkeypatch):
    order = woo_order(801, "metrics@example.invalid", "METRIC-SKU", "115.00", "2026-06-22T12:00:00", quantity=2)
    order["discount_total"] = "20.00"
    order["shipping_total"] = "10.00"
    order["total_tax"] = "5.00"
    order["line_items"][0]["subtotal"] = "120.00"
    order["line_items"][0]["total"] = "100.00"
    fake = patch_woo_orders(monkeypatch, [order])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert committed.status_code == 200, committed.text
    assert fake.write_called is False

    body = client.get("/api/insights/orders-revenue").json()

    assert body["summary"]["gross_sales"] == 120
    assert body["summary"]["discount_amount"] == 20
    assert body["summary"]["net_sales"] == 100
    assert body["summary"]["average_order_value"] == 100
    assert body["summary"]["shipping_revenue"] == 10
    assert body["summary"]["tax_total"] == 5
    assert body["tables"]["status_breakdown"][0]["revenue"] == 100
    assert body["tables"]["payment_methods"][0]["revenue"] == 100

    payment_health = client.get("/api/insights/payment-health").json()
    assert payment_health["rows"][0]["revenue"] == 100


def test_insights_uses_imported_woo_refund_summaries(client, monkeypatch):
    order = woo_order(802, "refund@example.invalid", "REFUND-SKU", "100.00", "2026-06-22T12:00:00", quantity=2)
    order["refunds"] = [{"id": 9001, "total": "-25.00"}]
    patch_woo_orders(monkeypatch, [order])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert committed.status_code == 200, committed.text

    body = client.get("/api/insights/orders-revenue").json()

    assert body["summary"]["net_sales"] == 75
    assert body["summary"]["refund_amount"] == 25
    assert body["summary"]["refund_rate"] == 25
    assert all(warning["code"] != "missing_refund_data" for warning in body["data_quality"])


def test_insights_includes_fully_refunded_orders_in_gross_and_returns(client, monkeypatch):
    order = woo_order(803, "refunded@example.invalid", "REFUNDED-SKU", "100.00", "2026-06-22T12:00:00", status="refunded", quantity=2)
    order["refunds"] = [{"id": 9002, "total": "-100.00"}]
    patch_woo_orders(monkeypatch, [order])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["refunded"], "limit": 100})
    assert committed.status_code == 200, committed.text

    body = client.get("/api/insights/orders-revenue").json()["summary"]

    assert body["total_orders"] == 1
    assert body["gross_sales"] == 100
    assert body["refund_amount"] == 100
    assert body["net_sales"] == 0


def test_insights_brand_and_category_filters_use_mapped_inventory_item(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    by_brand = client.get("/api/insights/overview", params={"brand": "Acana"}).json()
    by_category = client.get("/api/insights/overview", params={"category": "Dog Food"}).json()
    missing = client.get("/api/insights/overview", params={"brand": "Missing Brand"}).json()

    assert by_brand["summary"]["total_orders"] == 2
    assert by_category["summary"]["total_orders"] == 2
    assert missing["summary"]["total_orders"] == 0
    assert missing["empty_state"] == "No matching completed or active sales orders"


def test_insights_product_filters_scope_mixed_order_lines_across_sales_breakdowns(client, monkeypatch):
    seed_item(client, sku="MIX-A", Brand="Alpha", Category="Dogs")
    seed_item(client, sku="MIX-B", Brand="Beta", Category="Cats")
    order = woo_order(821, "mixed@example.invalid", "MIX-A", "20.00", "2026-06-22T12:00:00", quantity=1)
    order["line_items"].append(
        {
            "id": 8211,
            "product_id": 102,
            "variation_id": 0,
            "sku": "MIX-B",
            "name": "MIX-B Item",
            "quantity": 2,
            "price": "15.00",
            "subtotal": "30.00",
            "total": "30.00",
            "total_tax": "0.00",
            "meta_data": [{"key": "barcode", "value": "MIX-B-BAR"}],
        }
    )
    order["total"] = "50.00"
    fake = patch_woo_orders(monkeypatch, [order])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert committed.status_code == 200, committed.text
    assert fake.write_called is False

    params = {"brand": "Alpha"}
    revenue = client.get("/api/insights/orders-revenue", params=params).json()
    assert revenue["summary"]["total_orders"] == 1
    assert revenue["summary"]["gross_sales"] == 20
    assert revenue["summary"]["net_sales"] == 20
    assert revenue["summary"]["units_sold"] == 1
    assert revenue["rows"][0]["net_sales"] == 20
    assert revenue["tables"]["status_breakdown"][0]["revenue"] == 20
    assert revenue["tables"]["payment_methods"][0]["revenue"] == 20

    product = client.get("/api/insights/product-sku", params=params).json()
    assert [row["sku"] for row in product["rows"]] == ["MIX-A"]
    assert product["summary"]["revenue"] == 20

    customers = client.get("/api/insights/customer-metrics", params=params).json()
    assert customers["rows"][0]["lifetime_spend"] == 20
    geography = client.get("/api/insights/geography", params=params).json()
    assert geography["rows"][0]["revenue"] == 20
    payment = client.get("/api/insights/payment-health", params=params).json()
    assert payment["rows"][0]["revenue"] == 20


def test_insights_customer_metrics_calculates_new_and_returning(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)
    today = datetime.now(timezone.utc).date()
    params = {"start_date": (today - timedelta(days=10)).isoformat(), "end_date": today.isoformat()}

    body = client.get("/api/insights/customer-metrics", params=params).json()
    overview = client.get("/api/insights/overview", params=params).json()

    assert body["summary"]["total_customers"] == 2
    assert body["summary"]["returning_customers"] == 1
    assert body["summary"]["new_customers"] == 1
    assert overview["summary"]["returning_customers"] == 1
    assert overview["summary"]["new_customers"] == 1


def test_insights_keep_email_less_pos_sales_out_of_customer_counts(client, monkeypatch):
    seed_item(client, sku="POS-SKU", Brand="POS")
    orders = [
        woo_order(831, "", "POS-SKU", "10.00", "2026-07-02T12:00:00", quantity=1),
        woo_order(832, "", "POS-SKU", "15.00", "2026-07-03T12:00:00", quantity=1),
    ]
    for order in orders:
        order["customer_id"] = 0
        order["billing"] = {}
        order["shipping"] = {}
    fake = patch_woo_orders(monkeypatch, orders)
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert committed.status_code == 200, committed.text
    assert fake.write_called is False

    revenue = client.get("/api/insights/orders-revenue").json()
    customers = client.get("/api/insights/customer-metrics").json()

    assert revenue["summary"]["total_orders"] == 2
    assert revenue["summary"]["net_sales"] == 25
    assert customers["summary"]["total_customers"] == 0
    assert customers["summary"]["new_customers"] == 0
    assert customers["summary"]["anonymous_orders_without_email"] == 2
    assert all(warning["code"] != "missing_customer_email" for warning in customers["data_quality"])


def test_insights_compare_period_and_weekly_sales(client, monkeypatch):
    seed_item(client, sku="COMPARE-SKU")
    orders = [
        woo_order(841, "one@example.invalid", "COMPARE-SKU", "10.00", "2026-06-02T12:00:00", quantity=1),
        woo_order(842, "two@example.invalid", "COMPARE-SKU", "20.00", "2026-07-08T12:00:00", quantity=1),
        woo_order(843, "three@example.invalid", "COMPARE-SKU", "30.00", "2026-07-09T12:00:00", quantity=1),
    ]
    patch_woo_orders(monkeypatch, orders)
    assert client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100}).status_code == 200

    body = client.get("/api/insights/orders-revenue", params={
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "compare_start_date": "2026-06-01",
        "compare_end_date": "2026-06-30",
        "granularity": "week",
    }).json()

    assert body["summary"]["net_sales"] == 50
    assert body["comparison"]["summary"]["net_sales"] == 10
    assert body["comparison"]["changes"]["net_sales"] == 400
    assert len(body["trends"]["daily_revenue"]) == 1
    assert body["trends"]["daily_revenue"][0]["date"] == "2026-07-06"


def test_unfiltered_sales_headlines_use_authoritative_woo_analytics(client, monkeypatch):
    settings = get_settings().model_copy(update={
        "app_env": "production",
        "woocommerce_base_url": "https://woo.example.invalid",
        "woocommerce_consumer_key": "ck_test",
        "woocommerce_consumer_secret": "cs_test",
    })
    monkeypatch.setattr("app.services.insights.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.insights.effective_woocommerce_settings", lambda _db, value: value)
    monkeypatch.setattr(
        "app.services.insights.WooCommerceClient.analytics_stats",
        lambda _self, *_args, **_kwargs: {
            "totals": {
                "orders_count": 265,
                "num_items_sold": 1006,
                "gross_sales": 27497.84,
                "net_revenue": 26491.41,
                "avg_order_value": 101.702792,
                "refunds": 459.83,
                "coupons": 546.60,
                "shipping": 109.89,
                "taxes": 1299.07,
                "avg_items_per_order": 3.8189,
                "total_customers": 229,
            },
            "intervals": [{
                "interval": "2026-07-01",
                "subtotals": {"orders_count": 9, "gross_sales": 900, "net_revenue": 850, "num_items_sold": 31},
            }],
        },
    )

    body = client.get(
        "/api/insights/orders-revenue",
        params={"start_date": "2026-07-01", "end_date": "2026-07-31"},
    ).json()

    assert {
        "total_orders": 265,
        "gross_sales": 27497.84,
        "net_sales": 26491.41,
        "refund_amount": 459.83,
        "discount_amount": 546.6,
        "shipping_revenue": 109.89,
        "tax_total": 1299.07,
    }.items() <= body["summary"].items()
    assert body["rows"] == [{"date": "2026-07-01", "order_count": 9, "gross_sales": 900.0, "net_sales": 850.0, "units_sold": 31.0}]
    assert all(warning["code"] != "missing_refund_data" for warning in body["data_quality"])


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
    dog = next(row for row in body["rows"] if row["sku"] == "DOG-FOOD")
    assert dog["product_title"] == "DOG-FOOD Item"
    assert dog["description"] == dog["product_title"]


def test_insights_product_profitability_distinguishes_missing_and_zero_cost(client, monkeypatch):
    seed_item(client, sku="MISSING-COST", Brand="Cost Test", **{"Unit Cost": None})
    seed_item(client, sku="ZERO-COST", Brand="Cost Test", **{"Unit Cost": 0})
    orders = [
        woo_order(811, "cost@example.invalid", "MISSING-COST", "25.00", "2026-06-22T12:00:00", quantity=1),
        woo_order(812, "cost@example.invalid", "ZERO-COST", "30.00", "2026-06-22T13:00:00", quantity=1),
    ]
    fake = patch_woo_orders(monkeypatch, orders)
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert committed.status_code == 200, committed.text
    assert fake.write_called is False

    body = client.get("/api/insights/product-sku", params={"brand": "Cost Test"}).json()
    rows = {row["sku"]: row for row in body["rows"]}

    assert rows["MISSING-COST"]["cost_available"] is False
    assert rows["MISSING-COST"]["estimated_cost"] is None
    assert rows["MISSING-COST"]["estimated_margin"] is None
    assert rows["MISSING-COST"]["margin_percent"] is None
    assert rows["ZERO-COST"]["cost_available"] is True
    assert rows["ZERO-COST"]["estimated_cost"] == 0
    assert rows["ZERO-COST"]["estimated_margin"] == 30
    assert rows["ZERO-COST"]["margin_percent"] == 100
    assert body["summary"]["estimated_margin"] is None
    assert body["summary"]["cost_data_available"] is False
    assert any(warning["code"] == "missing_unit_cost" for warning in body["data_quality"])

    zero_only = client.get("/api/insights/product-sku", params={"sku": "ZERO-COST"}).json()
    assert zero_only["summary"]["estimated_margin"] == 30
    assert zero_only["summary"]["cost_data_available"] is True
    assert not any(warning["code"] == "missing_unit_cost" for warning in zero_only["data_quality"])


def test_insights_subscriptions_empty_state(client):
    body = client.get("/api/insights/subscriptions").json()

    assert body["empty_state"] == "No subscription data synced yet"
    assert body["summary"]["data_available"] is False
    assert body["summary"]["active_subscriptions"] is None
    assert body["summary"]["subscription_revenue"] is None
    assert body["summary"]["monthly_recurring_revenue"] is None
    assert any(warning["code"] == "missing_subscription_data" for warning in body["data_quality"])


def test_insights_subscription_products_empty_state(client):
    body = client.get("/api/insights/subscription-products").json()

    assert body["empty_state"] == "No subscription data synced yet"
    assert body["rows"] == []
    assert body["summary"] == {
        "data_available": False,
        "products_on_subscription_count": None,
        "stockout_risk_for_subscription_products": None,
    }


def test_insights_inventory_forecasting_calculates_days_left(client, monkeypatch):
    seed_insight_orders(client, monkeypatch)

    body = client.get("/api/insights/inventory-forecasting").json()
    dog = next(row for row in body["rows"] if row["sku"] == "DOG-FOOD")

    assert dog["daily_velocity"] > 0
    assert dog["days_of_stock_left"] is not None


def test_insights_forecasting_marks_no_sales_history_unavailable(client):
    seed_item(client, sku="NO-HISTORY", Brand="Forecast Test")

    body = client.get("/api/insights/inventory-forecasting", params={"sku": "NO-HISTORY"}).json()
    row = body["rows"][0]

    assert row["forecast_available"] is False
    assert row["forecast_status"] == "insufficient_history"
    assert row["risk_level"] == "insufficient_history"
    assert row["daily_velocity"] is None
    assert row["suggested_reorder_qty"] is None
    assert row["forecasted_30_day_demand"] is None
    assert row["forecasted_60_day_demand"] is None
    assert row["forecasted_90_day_demand"] is None
    assert body["summary"]["forecast_status"] == "insufficient_history"
    assert body["summary"]["forecast_available_count"] == 0
    assert body["summary"]["forecasted_30_day_demand"] is None
    assert any(warning["code"] == "insufficient_sales_history" for warning in body["data_quality"])


def test_insights_forecasting_uses_filtered_successful_sales_and_item_scope(client, monkeypatch):
    target = seed_item(client, sku="FORECAST-TARGET", Description="A long marketing description that must not become the forecast title", Brand="Acana", Category="Dog Food")
    seed_item(client, sku="FORECAST-OTHER", Brand="Kong", Category="Cat Toys")
    db_override = app.dependency_overrides[get_db]()
    db = next(db_override)
    try:
        db.get(InventoryItem, target["id"]).woo_name = "Concise forecast title"
        db.commit()
    finally:
        db_override.close()
    recent_day = (datetime.now(timezone.utc) - timedelta(days=2)).date()
    older_day = (datetime.now(timezone.utc) - timedelta(days=10)).date()
    recent_created = f"{recent_day.isoformat()}T12:00:00"
    older_created = f"{older_day.isoformat()}T12:00:00"

    recent_success = woo_order(901, "forecast@example.invalid", "FORECAST-TARGET", "20.00", recent_created, quantity=2)
    recent_success["line_items"].append(
        {
            "id": 9011,
            "product_id": 102,
            "variation_id": 0,
            "sku": "FORECAST-OTHER",
            "name": "Forecast Other Item",
            "quantity": 4,
            "price": "5.00",
            "subtotal": "20.00",
            "total": "20.00",
            "total_tax": "0.00",
            "meta_data": [{"key": "barcode", "value": "FORECAST-OTHER-BAR"}],
        }
    )
    recent_success["total"] = "40.00"
    failed = woo_order(902, "forecast@example.invalid", "FORECAST-TARGET", "70.00", recent_created, status="failed", quantity=7)
    older_success = woo_order(903, "forecast@example.invalid", "FORECAST-TARGET", "30.00", older_created, quantity=3)
    fake = patch_woo_orders(monkeypatch, [recent_success, failed, older_success])
    committed = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing", "failed"], "limit": 100})
    assert committed.status_code == 200, committed.text
    assert fake.write_called is False

    overview = client.get("/api/insights/overview").json()
    overview_target = next(row for row in overview["tables"]["stockout_risk"] if row["sku"] == "FORECAST-TARGET")
    assert overview_target["units_sold_30d"] == 5

    for filter_params in [
        {"sku": "FORECAST-TARGET"},
        {"brand": "Acana"},
        {"category": "Dog Food"},
    ]:
        forecast = client.get("/api/insights/inventory-forecasting", params=filter_params).json()
        assert [row["sku"] for row in forecast["rows"]] == ["FORECAST-TARGET"]
        assert forecast["rows"][0]["units_sold_30d"] == 5
        assert forecast["rows"][0]["product_title"] == "Concise forecast title"
        assert forecast["rows"][0]["description"] == "Concise forecast title"

    dated = client.get(
        "/api/insights/inventory-forecasting",
        params={"sku": "FORECAST-TARGET", "start_date": recent_day.isoformat(), "end_date": recent_day.isoformat()},
    ).json()
    assert [row["sku"] for row in dated["rows"]] == ["FORECAST-TARGET"]
    assert dated["rows"][0]["units_sold_30d"] == 2


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
