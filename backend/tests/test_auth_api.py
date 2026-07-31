import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AuthThrottle, Base
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


def test_registration_has_no_roles_and_rejects_duplicate_email(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "pytest@example.com", "display_name": "Duplicate", "password": "another-secure-password"},
    )

    assert response.status_code == 409
    assert "role" not in client.get("/api/auth/me").text.casefold()


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
