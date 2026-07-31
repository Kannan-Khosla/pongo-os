from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.models.woocommerce import WooCommerceSyncError, WooCommerceSyncRun
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
        "woocommerce_order_reconciliation_interval_seconds": 60,
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

    class Client:
        configured = True

        def __init__(self):
            self.calls = []

        def fetch_all_orders(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("modified_after"):
                return [{**remote_order(999), "status": "cancelled"}]
            return [remote_order(order_id) for order_id in range(1, 121)]

    fake = Client()
    result = run_order_reconciliation_once(
        reconciliation_settings(),
        session_factory=factory,
        client_factory=lambda _settings: fake,
    )

    assert result["status"] == "completed"
    assert result["total_remote_records"] == 121
    assert len(fake.calls) == 2
    active_call, terminal_call = fake.calls
    assert active_call == {"statuses": ["processing", "on-hold", "pending"], "limit": None}
    assert {"completed", "failed", "cancelled", "refunded"} <= set(terminal_call["statuses"])
    assert terminal_call["limit"] is None
    assert terminal_call["modified_after"].endswith("Z")
    with factory() as db:
        health = reconciliation_health(db, reconciliation_settings(), running=True)
        assert health["healthy"] is True
        assert health["last_status"] == "completed"
        assert health["error_count"] == 0


def test_scheduler_failure_is_durable_and_visible_in_health(caplog):
    factory = session_factory()

    class FailingClient:
        configured = True

        def fetch_all_orders(self, **_kwargs):
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


def test_completed_with_errors_does_not_advance_success_cursor_and_reports_degraded_health():
    factory = session_factory()
    now = datetime.now(timezone.utc)
    with factory() as db:
        run = WooCommerceSyncRun(
            sync_type="orders",
            status="completed_with_errors",
            started_at=now - timedelta(seconds=10),
            completed_at=now,
            created_by="server-order-reconciliation",
            error_count=1,
        )
        db.add(run)
        db.flush()
        db.add(WooCommerceSyncError(sync_run_id=run.id, error_message="Order line needs mapping review."))
        db.commit()

        health = reconciliation_health(db, reconciliation_settings(), running=True, now=now)

    assert health["healthy"] is False
    assert health["degraded"] is True
    assert health["stale"] is True
    assert health["last_error"] == "Order line needs mapping review."


def test_scheduler_does_not_start_in_tests(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "scheduler-test")
    assert reconciliation_should_start(reconciliation_settings()) is False
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    assert reconciliation_should_start(reconciliation_settings()) is True
    assert reconciliation_should_start(reconciliation_settings(woocommerce_base_url="")) is True
    assert reconciliation_should_start(reconciliation_settings(app_env="test")) is False
