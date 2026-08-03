from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.models.woocommerce import WooCommerceSyncRun
from app.services.woocommerce_client import WooCommerceClientError
from app.services.woocommerce_order_reconciliation import (
    DEFAULT_STATUSES,
    reconciliation_health,
    reconciliation_should_start,
    run_order_reconciliation_once,
)


def reconciliation_settings(**overrides):
    values = {
        "app_env": "production",
        "woocommerce_base_url": "https://woo.example.invalid",
        "woocommerce_consumer_key": "ck_placeholder",
        "woocommerce_consumer_secret": "cs_placeholder",
        "woocommerce_read_enabled": True,
        "woocommerce_order_reconciliation_enabled": True,
        "woocommerce_order_reconciliation_interval_seconds": 120,
        "woocommerce_order_reconciliation_stale_after_seconds": 300,
        "woocommerce_order_reconciliation_lookback_hours": 168,
        "order_reconciliation_statuses": DEFAULT_STATUSES,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def remote_order(order_id):
    return {
        "id": order_id,
        "number": str(order_id),
        "status": "processing",
        "currency": "CAD",
        "total": "0.00",
        "date_created_gmt": "2026-07-26T12:00:00",
        "date_modified_gmt": "2026-07-26T12:01:00",
        "billing": {},
        "shipping": {},
        "line_items": [],
    }


def test_scheduler_fetches_all_active_orders_and_recent_terminal_changes():
    factory = session_factory()
    with factory() as db:
        db.add(WooCommerceSyncRun(
            sync_type="order_job",
            status="completed",
            started_at=datetime.now(timezone.utc) - timedelta(minutes=3),
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            created_by="server-order-reconciliation",
        ))
        db.commit()

    class Client:
        configured = True

        def __init__(self):
            self.calls = []

        def list_orders(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["status"] == "cancelled" and kwargs["page"] == 1:
                return [{**remote_order(999), "status": "cancelled"}]
            if kwargs["status"] != "processing":
                return []
            start = (kwargs["page"] - 1) * kwargs["per_page"] + 1
            return [remote_order(order_id) for order_id in range(start, min(start + kwargs["per_page"], 121))]

    fake = Client()
    result = run_order_reconciliation_once(
        reconciliation_settings(),
        session_factory=factory,
        client_factory=lambda _settings: fake,
    )

    assert result["status"] == "completed"
    assert result["total_remote_records"] == 121
    assert all(call["per_page"] == 25 for call in fake.calls)
    assert all(call["modified_after"] is None for call in fake.calls if call["status"] in {"processing", "on-hold", "pending"})
    assert all(call["modified_after"].endswith("Z") for call in fake.calls if call["status"] in {"completed", "failed", "cancelled", "refunded"})
    assert [call["page"] for call in fake.calls if call["status"] == "processing"] == [1, 2, 3, 4, 5]
    with factory() as db:
        health = reconciliation_health(db, reconciliation_settings(), running=True)
        assert health["healthy"] is True
        assert health["last_status"] == "completed"
        assert health["error_count"] == 0


def test_scheduler_failure_is_durable_and_visible_in_health(caplog):
    factory = session_factory()

    class FailingClient:
        configured = True

        def list_orders(self, **_kwargs):
            try:
                raise RuntimeError("consumer_secret=must-not-reach-logs")
            except RuntimeError as error:
                raise WooCommerceClientError("WooCommerce credentials expired.") from error

    result = run_order_reconciliation_once(
        reconciliation_settings(),
        session_factory=factory,
        client_factory=lambda _settings: FailingClient(),
    )

    assert result["status"] == "failed"
    assert "must-not-reach-logs" not in caplog.text
    with factory() as db:
        health = reconciliation_health(db, reconciliation_settings(), running=True)
        assert health["healthy"] is False
        assert health["last_status"] == "failed"
        assert health["error_count"] == 1
        assert health["last_error"] == "WooCommerce credentials expired."


def test_health_reports_that_first_reconciliation_is_starting():
    factory = session_factory()
    with factory() as db:
        health = reconciliation_health(db, reconciliation_settings(), running=True)

    assert health["healthy"] is False
    assert health["last_status"] is None
    assert health["message"] == "The first server order reconciliation is starting."


def test_completed_with_errors_advances_remote_cursor_and_reports_mapping_review():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as db:
        run = WooCommerceSyncRun(
            sync_type="order_job",
            status="completed_with_errors",
            started_at=now - timedelta(seconds=10),
            completed_at=now,
            error_count=1,
            notes="Order line needs mapping review.",
        )
        db.add(run)
        db.commit()

        health = reconciliation_health(db, reconciliation_settings(), running=True, now=now)

    assert health["healthy"] is False
    assert health["degraded"] is True
    assert health["stale"] is False
    assert health["last_success_at"] == now
    assert health["last_error"] == "Order line needs mapping review."


def test_scheduler_does_not_start_in_tests(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "scheduler-test")
    assert reconciliation_should_start(reconciliation_settings()) is False
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert reconciliation_should_start(reconciliation_settings()) is True
    assert reconciliation_should_start(reconciliation_settings(woocommerce_base_url="")) is True
    assert reconciliation_should_start(reconciliation_settings(app_env="test")) is False
