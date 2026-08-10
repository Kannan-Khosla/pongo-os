import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AuthThrottle, Base, InventoryItem, User
from app.services.auth import registration_allowed
from tests.test_items_api import client  # noqa: F401


def test_unknown_app_environment_fails_configuration():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="prod")


def test_authenticated_session_protects_api_and_logout_revokes_it(client):
    assert client.get("/api/auth/me").json()["user"]["email"] == "pytest@example.com"
    assert client.get("/api/items").status_code == 200

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/items").status_code == 401
    assert client.post("/api/auth/login", json={"email": "pytest@example.com", "password": "correct-horse-battery-staple"}).status_code == 200
    assert client.get("/api/items").status_code == 200


def test_registration_creates_staff_access_and_rejects_duplicate_email(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "pytest@example.com", "display_name": "Duplicate", "password": "another-secure-password"},
    )

    assert response.status_code == 409
    user = client.get("/api/auth/me").json()["user"]
    assert user["access_level"] == "staff"
    assert user["data_scope"] == "production"
    assert user["permissions"] == ["read", "write"]


def test_demo_user_sees_only_mock_data_and_cannot_write_or_reach_integrations(client):
    with Session(client.test_engine) as db:
        db.add(InventoryItem(sku="PRIVATE-LIVE-SKU", description="Must never reach demo", in_stock=1, allocated=0, sellable=1, active=True))
        user = db.scalar(select(User).where(User.email == "pytest@example.com"))
        user.access_level = "demo"
        db.commit()

    me = client.get("/api/auth/me").json()["user"]
    assert me["access_level"] == "demo"
    assert me["data_scope"] == "mock"
    assert me["permissions"] == ["read"]

    items = client.get("/api/items", params={"page": 1, "page_size": 100}).json()["items"]
    assert items
    assert all(item["SKU"].startswith("DEMO-") for item in items)
    assert "PRIVATE-LIVE-SKU" not in {item["SKU"] for item in items}

    for path in (
        "/api/dashboard",
        "/api/business-dashboard",
        "/api/inventory/locations",
        "/api/locations",
        "/api/receipts",
        "/api/stock-movements",
        "/api/cycle-counts",
        "/api/orders/open",
        "/api/orders/completed",
        "/api/allocations",
        "/api/picks",
        "/api/fulfillments",
        "/api/routes",
        "/api/reports",
    ):
        response = client.get(path)
        assert response.status_code == 200, f"{path}: {response.text}"

    blocked = client.post("/api/items", json={"SKU": "DEMO-WRITE"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "demo_read_only"

    route_plan = client.post("/api/routes/open-orders/plan", json={})
    assert route_plan.status_code == 200, route_plan.text
    assert route_plan.json()["selected_order_count"] > 0

    integration = client.get("/api/integrations/woocommerce/status")
    assert integration.status_code == 403
    assert integration.json()["detail"]["code"] == "demo_external_access_blocked"


def test_password_policy_is_enforced(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "display_name": "Short", "password": "too-short"},
    )

    assert response.status_code == 422


def test_first_production_registration_requires_the_configured_access_code():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        app_env="production",
        registration_enabled=True,
        registration_access_code="private-bootstrap-code-with-32-random-bytes",
    )

    with Session(engine) as db:
        assert registration_allowed(db, settings, None) is False
        assert registration_allowed(db, settings, "wrong") is False
        assert registration_allowed(db, settings, "private-bootstrap-code-with-32-random-bytes") is True


def test_production_registration_rejects_weak_codes_and_rate_limits_guesses():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    weak = Settings(_env_file=None, app_env="production", registration_enabled=True, registration_access_code="x")
    strong = Settings(
        _env_file=None,
        app_env="production",
        registration_enabled=True,
        registration_access_code="private-bootstrap-code-with-32-random-bytes",
        auth_max_failed_logins=3,
    )

    with Session(engine) as db:
        assert registration_allowed(db, weak, "x") is False
        for _ in range(3):
            assert registration_allowed(db, strong, "wrong") is False
        throttle = db.scalar(select(AuthThrottle))
        assert throttle.locked_until is not None
        assert registration_allowed(db, strong, strong.registration_access_code) is False
