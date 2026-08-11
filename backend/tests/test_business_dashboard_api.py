from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import User
from app.services.woocommerce_client import WooCommerceClientError
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


def woo_order(order_id, email, total, created, status="processing", city="Edmonton", postal="T5A", quantity=2):
    return {
        "id": order_id,
        "number": str(order_id),
        "status": status,
        "currency": "CAD",
        "customer_id": order_id,
        "billing": {"first_name": "Avery", "last_name": "Stone", "email": email, "phone": "555-0100", "city": city, "postcode": postal, "country": "CA"},
        "shipping": {"first_name": "Avery", "last_name": "Stone", "address_1": "1 Main St", "city": city, "postcode": postal, "country": "CA"},
        "payment_method": "stripe",
        "payment_method_title": "Stripe",
        "discount_total": "0.00",
        "shipping_total": "0.00",
        "total_tax": "0.00",
        "total": str(total),
        "date_created_gmt": created,
        "date_modified_gmt": created,
        "line_items": [
            {
                "id": order_id * 10,
                "product_id": 101,
                "variation_id": 0,
                "sku": "BD-SKU",
                "name": "Business Dashboard Item",
                "quantity": quantity,
                "price": str(float(total) / quantity),
                "subtotal": str(total),
                "total": str(total),
                "total_tax": "0.00",
                "meta_data": [{"key": "barcode", "value": "BD-SKU-BAR"}],
            }
        ],
    }


def seed_business_orders(client, monkeypatch):
    seed_item(client, sku="BD-SKU", Barcode="BD-SKU-BAR", wooProductId=101, **{"In Stock": 20, "Allocated": 0, "Unit Cost": 5})
    orders = [
        woo_order(801, "returning@example.invalid", "40.00", "2026-06-10T12:00:00", city="Edmonton"),
        woo_order(802, "returning@example.invalid", "60.00", "2026-07-08T10:00:00", city="Edmonton"),
        woo_order(803, "new@example.invalid", "30.00", "2026-07-08T11:00:00", city="Sherwood Park", postal="T8A"),
        woo_order(804, "previous@example.invalid", "50.00", "2026-06-08T10:00:00", city="Leduc", postal="T9E"),
    ]
    fake = patch_woo_orders(monkeypatch, orders)
    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert response.status_code == 200, response.text
    assert fake.write_called is False
    return fake


def test_business_dashboard_today_returns_zero_cleanly(client):
    response = client.get("/api/business-dashboard/today", params={"date": "2026-07-08"})

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["today_orders_count"] == 0
    assert any(warning["code"] == "limited_order_history" for warning in body["data_quality"])


def test_business_dashboard_today_metrics_from_local_orders(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    body = client.get("/api/business-dashboard/today", params={"date": "2026-07-08"}).json()

    assert body["summary"]["today_orders_count"] == 2
    assert body["summary"]["today_revenue"] == 90
    assert body["summary"]["average_order_value_today"] == 45


def test_business_dashboard_new_vs_returning_customers(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    body = client.get("/api/business-dashboard/today", params={"date": "2026-07-08"}).json()

    assert body["summary"]["today_new_customers"] == 1
    assert body["summary"]["today_returning_customers"] == 1


def test_business_dashboard_does_not_count_orders_without_email_as_new_customers(client, monkeypatch):
    seed_business_orders(client, monkeypatch)
    anonymous_order = woo_order(805, "", "25.00", "2026-07-08T12:00:00")
    patch_woo_orders(monkeypatch, [anonymous_order])
    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["processing"], "limit": 100})
    assert response.status_code == 200, response.text

    body = client.get("/api/business-dashboard/today", params={"date": "2026-07-08"}).json()

    assert body["summary"]["today_orders_count"] == 3
    assert body["summary"]["today_new_customers"] == 1
    assert body["summary"]["today_returning_customers"] == 1


def test_business_dashboard_excludes_failed_orders_from_sales_and_customers(client, monkeypatch):
    seed_business_orders(client, monkeypatch)
    failed_order = woo_order(806, "failed@example.invalid", "100.00", "2026-07-08T12:30:00", status="failed")
    patch_woo_orders(monkeypatch, [failed_order])
    response = client.post("/api/integrations/woocommerce/orders/commit", json={"include_statuses": ["failed"], "limit": 100})
    assert response.status_code == 200, response.text

    body = client.get("/api/business-dashboard/today", params={"date": "2026-07-08"}).json()["summary"]

    assert body["today_orders_count"] == 2
    assert body["today_revenue"] == 90
    assert body["today_new_customers"] == 1
    assert body["failed_orders_today"] == 1


def test_business_dashboard_open_orders_customer_rows(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    body = client.get("/api/business-dashboard/open-orders").json()

    assert body["rows"]
    assert {"customer_name", "customer_email", "order_number", "status"}.issubset(body["rows"][0].keys())


def test_woocommerce_open_orders_uses_live_totals_for_exact_active_statuses(client, monkeypatch):
    totals = {"processing": 7, "on-hold": 3, "pending": 2}

    class FakeLiveWooClient:
        def __init__(self, settings):
            self.timeout_seconds = settings.woocommerce_timeout_seconds
            self.last_response_headers = {}
            self.calls = []

        def list_orders(self, **params):
            self.calls.append(params)
            total = totals[params["status"]]
            self.last_response_headers = {"X-WP-Total": str(total), "X-WP-TotalPages": str(total)}
            return [{}]

    fake = FakeLiveWooClient(SimpleNamespace(woocommerce_timeout_seconds=30))
    monkeypatch.setattr("app.api.routes.business_dashboard.effective_woocommerce_settings", lambda db: SimpleNamespace(woocommerce_timeout_seconds=30))
    monkeypatch.setattr("app.api.routes.business_dashboard.WooCommerceClient", lambda settings: fake)

    response = client.get("/api/business-dashboard/woocommerce-open-orders")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "woocommerce"
    assert body["statuses"] == {"on-hold": 3, "pending": 2, "processing": 7}
    assert body["summary"] == {"open_orders_count": 12}
    assert datetime.fromisoformat(body["fetched_at"]).tzinfo is not None
    assert {call["status"] for call in fake.calls} == set(totals)
    assert all(call["page"] == 1 and call["per_page"] == 1 for call in fake.calls)
    assert fake.timeout_seconds == 5


def test_woocommerce_open_orders_fails_closed_without_remote_totals(client, monkeypatch):
    class MissingTotalsWooClient:
        timeout_seconds = 30
        last_response_headers = {}

        def __init__(self, settings):
            pass

        def list_orders(self, **params):
            self.last_response_headers = {"X-WP-Total": "4"}
            return [{}]

    monkeypatch.setattr("app.api.routes.business_dashboard.effective_woocommerce_settings", lambda db: object())
    monkeypatch.setattr("app.api.routes.business_dashboard.WooCommerceClient", MissingTotalsWooClient)

    response = client.get("/api/business-dashboard/woocommerce-open-orders")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "woocommerce_open_orders_unavailable"


def test_woocommerce_open_orders_returns_safe_503_on_woo_failure(client, monkeypatch):
    class FailedWooClient:
        timeout_seconds = 30

        def __init__(self, settings):
            pass

        def list_orders(self, **params):
            raise WooCommerceClientError("secret upstream detail")

    monkeypatch.setattr("app.api.routes.business_dashboard.effective_woocommerce_settings", lambda db: object())
    monkeypatch.setattr("app.api.routes.business_dashboard.WooCommerceClient", FailedWooClient)

    response = client.get("/api/business-dashboard/woocommerce-open-orders")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "woocommerce_open_orders_unavailable",
        "message": "Live WooCommerce open-order count is temporarily unavailable.",
    }


def test_demo_woocommerce_open_orders_never_constructs_live_client(client, monkeypatch):
    with Session(client.test_engine) as db:
        user = db.scalar(select(User).where(User.email == "pytest@example.com"))
        user.access_level = "demo"
        db.commit()

    def reject_live_access(*args, **kwargs):
        raise AssertionError("Demo must not construct a WooCommerce client.")

    monkeypatch.setattr("app.api.routes.business_dashboard.effective_woocommerce_settings", reject_live_access)
    monkeypatch.setattr("app.api.routes.business_dashboard.WooCommerceClient", reject_live_access)

    response = client.get("/api/business-dashboard/woocommerce-open-orders")

    assert response.status_code == 200, response.text
    assert response.json()["source"] == "demo"
    assert response.json()["statuses"] == {}
    assert response.json()["summary"]["open_orders_count"] >= 0


def test_business_dashboard_subscriptions_empty_state(client):
    body = client.get("/api/business-dashboard/subscriptions", params={"date": "2026-07-08"}).json()

    assert body["summary"]["subscription_data_available"] is False
    assert body["rows"] == []
    assert any(warning["code"] == "missing_subscription_data" for warning in body["data_quality"])


def test_business_dashboard_revenue_comparison_series(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    body = client.get("/api/business-dashboard/revenue-comparison", params={"date": "2026-07-08"}).json()

    assert body["summary"]["current_period_revenue"] == 90
    assert body["summary"]["previous_period_revenue"] == 50
    assert len(body["daily_series"]) == 8


def test_business_dashboard_order_map_groups_city_and_marks_approximate(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    body = client.get("/api/business-dashboard/order-map", params={"date": "2026-07-08"}).json()

    cities = {row["city"]: row["order_count"] for row in body["city_breakdown"]}
    assert cities["Edmonton"] == 1
    assert cities["Sherwood Park"] == 1
    assert all(marker["approximate"] is True for marker in body["markers"])


def test_business_dashboard_combined_endpoint_returns_all_sections(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    body = client.get("/api/business-dashboard", params={"date": "2026-07-08"}).json()

    assert {"today", "open_orders", "subscriptions", "revenue_comparison", "order_map", "data_quality"}.issubset(body.keys())


def test_business_dashboard_sql_paths_match_legacy_metric_semantics(client, monkeypatch):
    seed_business_orders(client, monkeypatch)

    from app.services.business_dashboard import (
        build_open_orders,
        build_order_map,
        build_revenue_comparison,
        build_subscriptions,
        build_today,
        eligible_order_condition,
    )

    target = datetime(2026, 7, 8).date()
    with Session(client.test_engine) as db:
        from app.models.orders import Order

        order = db.scalar(select(Order).where(Order.woo_order_id == 803))
        order.total = None
        order.raw_woo_payload = {
            "subscriptions": [
                {
                    "id": 9001,
                    "name": "Monthly food",
                    "next_payment_date": "2026-07-10",
                    "quantity": 2,
                    "status": "active",
                    "sku": "BD-SKU",
                }
            ]
        }
        db.commit()
        legacy_orders = list(
            db.scalars(
                select(Order)
                .where(eligible_order_condition())
                .options(selectinload(Order.items))
                .order_by(Order.id.asc())
            ).all()
        )

        assert build_today(db, target) == build_today(db, target, orders=legacy_orders)
        assert build_open_orders(db) == build_open_orders(db, orders=legacy_orders)
        assert build_subscriptions(db, target) == build_subscriptions(db, target, orders=legacy_orders)
        assert build_revenue_comparison(db, target) == build_revenue_comparison(db, target, orders=legacy_orders)
        assert build_order_map(db, target) == build_order_map(db, target, orders=legacy_orders)


def test_business_dashboard_open_order_preview_is_bounded_but_count_is_exact(client):
    from app.models.orders import Order
    from app.services.business_dashboard import BUSINESS_OPEN_ORDER_ROW_LIMIT, build_open_orders

    with Session(client.test_engine) as db:
        db.add_all(
            [
                Order(
                    woo_order_id=10_000 + index,
                    woo_order_number=str(10_000 + index),
                    local_status="open",
                    status="processing",
                    is_historical_snapshot=False,
                    historical_source_present=True,
                    placed_on=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
                )
                for index in range(BUSINESS_OPEN_ORDER_ROW_LIMIT + 7)
            ]
        )
        db.commit()

        result = build_open_orders(db)

    assert result["summary"]["open_orders_count"] == BUSINESS_OPEN_ORDER_ROW_LIMIT + 7
    assert len(result["rows"]) == BUSINESS_OPEN_ORDER_ROW_LIMIT


def test_business_dashboard_sql_day_bounds_use_admin_timezone(client):
    from app.models.orders import Order
    from app.services.business_dashboard import build_today

    with Session(client.test_engine) as db:
        db.add(
            Order(
                woo_order_id=20_001,
                woo_order_number="20001",
                local_status="open",
                status="processing",
                customer_email="boundary@example.invalid",
                total=10,
                is_historical_snapshot=False,
                historical_source_present=True,
                placed_on=datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc),
            )
        )
        db.commit()

        edmonton_day = build_today(db, datetime(2026, 8, 5).date())["summary"]
        following_day = build_today(db, datetime(2026, 8, 6).date())["summary"]

    assert edmonton_day["today_orders_count"] == 1
    assert edmonton_day["today_revenue"] == 10
    assert following_day["today_orders_count"] == 0


def test_business_dashboard_endpoints_are_read_only(client, monkeypatch):
    seed_business_orders(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "BD-SKU"}).json()["items"][0]
    before_orders = client.get("/api/orders/open").json()["total"]

    for endpoint in ["today", "open-orders", "subscriptions", "revenue-comparison", "order-map"]:
        assert client.get(f"/api/business-dashboard/{endpoint}", params={"date": "2026-07-08"}).status_code == 200
    assert client.get("/api/business-dashboard", params={"date": "2026-07-08"}).status_code == 200

    after_item = client.get("/api/items", params={"sku": "BD-SKU"}).json()["items"][0]
    after_orders = client.get("/api/orders/open").json()["total"]
    assert after_item["In Stock"] == before_item["In Stock"]
    assert after_item["Allocated"] == before_item["Allocated"]
    assert after_orders == before_orders


def test_business_dashboard_uses_admin_timezone_for_day_boundaries():
    from types import SimpleNamespace

    from app.services.business_dashboard import admin_today, order_day

    utc_time = datetime(2026, 8, 6, 5, 30, tzinfo=timezone.utc)
    settings = SimpleNamespace(admin_timezone="America/Edmonton")
    order = SimpleNamespace(placed_on=utc_time, date_created=None, completed_on=None, created_at=None)

    assert admin_today(utc_time, settings) == datetime(2026, 8, 5).date()
    assert order_day(order) == datetime(2026, 8, 5).date()
