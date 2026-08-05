from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from app.models.inventory import InventoryItem, StockMovement
from app.models.orders import Order, OrderItem
from app.models.woocommerce import WooCommerceSyncRun
from app.services.business_dashboard import build_today
from app.services.picks import get_scanner_order
from app.services.woocommerce_client import WooCommerceClientError
from app.services.woocommerce_orders import commit_remote_order_records
from app.services.woocommerce_order_reconciliation import (
    BATCH_SIZE,
    DEFAULT_STATUSES,
    HISTORY_BATCH_SIZE,
    enqueue_order_history_import,
    order_history_coverage,
    process_next_order_history_import,
    reconciliation_health,
    reconciliation_should_start,
    run_order_reconciliation_once,
)
from app.services.routes import list_route_candidates


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


def test_historical_import_resumes_by_page_and_never_enters_operations():
    factory = session_factory()
    settings = reconciliation_settings()
    completed_orders = [
        {
            **remote_order(order_id),
            "status": "custom-fulfilled" if order_id == HISTORY_BATCH_SIZE + 1 else "completed",
            "payment_method": "foosales_pos",
            "billing": {"email": f"customer-{order_id}@example.invalid"},
            "line_items": [{
                "id": order_id * 100,
                "product_id": 0,
                "variation_id": 0,
                "sku": "HISTORY-SKU",
                "name": "Historical Item",
                "quantity": 2,
                "subtotal": "10.00",
                "total": "10.00",
                "total_tax": "0.50",
            }],
        }
        for order_id in range(1, HISTORY_BATCH_SIZE + 2)
    ]

    class ReadOnlyClient:
        def __init__(self):
            self.calls = []
            self.last_response_headers = {}

        def list_orders(self, **kwargs):
            self.calls.append(kwargs)
            rows = completed_orders if kwargs["status"] == "any" else []
            self.last_response_headers = {
                "X-WP-Total": str(len(rows)),
                "X-WP-TotalPages": str((len(rows) + kwargs["per_page"] - 1) // kwargs["per_page"]),
            }
            start = (kwargs["page"] - 1) * kwargs["per_page"]
            return rows[start:start + kwargs["per_page"]]

    remote = ReadOnlyClient()
    with factory() as db:
        db.add(InventoryItem(sku="HISTORY-SKU", in_stock=Decimal("10"), allocated=Decimal("3"), sellable=Decimal("7")))
        db.commit()
        job = enqueue_order_history_import(db, "pytest", settings)
        job_id = job.id

    first = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)
    assert first["status"] == "queued"
    assert first["progress"]["current_status"] == "any"
    assert first["progress"]["next_page"] == 2

    result = first
    while result["status"] == "queued":
        result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)

    assert result["status"] == "completed"
    assert result["sync_run_id"] == job_id
    assert result["total_remote_records"] == HISTORY_BATCH_SIZE + 1
    assert result["created_count"] == HISTORY_BATCH_SIZE + 1
    assert [(call["status"], call["page"]) for call in remote.calls] == [
        ("any", 1),
        ("any", 2),
    ]
    assert all(call["before"] for call in remote.calls)

    with factory() as db:
        orders = list(db.scalars(select(Order).order_by(Order.id)).all())
        assert len(orders) == HISTORY_BATCH_SIZE + 1
        assert all(order.is_historical_snapshot for order in orders)
        assert {order.local_status for order in orders} == {"completed", "custom-fulfilled"}
        assert all(order.allocation_status == "unallocated" for order in orders)
        assert all(order.pick_status == "not_ready" for order in orders)
        assert all(line.quantity_allocated == 0 and line.quantity_stock_reduced == 0 for order in orders for line in order.items)
        item = db.scalars(select(InventoryItem).where(InventoryItem.sku == "HISTORY-SKU")).one()
        assert (item.in_stock, item.allocated, item.sellable) == (Decimal("10"), Decimal("3"), Decimal("7"))
        assert list(db.scalars(select(StockMovement)).all()) == []
        assert list_route_candidates(db).total_candidates == 0
        assert get_scanner_order(db, orders[0].id) is None
        coverage = order_history_coverage(db, settings)
        assert coverage["verified_complete"] is True
        assert coverage["local_order_count"] == HISTORY_BATCH_SIZE + 1
        assert coverage["historical_snapshot_count"] == HISTORY_BATCH_SIZE + 1
        assert coverage["distinct_order_dates"] == 1


def test_historical_import_uses_woo_total_pages_at_exact_batch_boundary():
    factory = session_factory()
    settings = reconciliation_settings()
    rows = [{**remote_order(order_id), "status": "completed"} for order_id in range(1, HISTORY_BATCH_SIZE + 1)]

    class Client:
        last_response_headers = {"X-WP-Total": str(HISTORY_BATCH_SIZE), "X-WP-TotalPages": "1"}

        def list_orders(self, **_kwargs):
            return rows

    with factory() as db:
        enqueue_order_history_import(db, "pytest", settings)

    result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: Client())

    assert result["total_remote_records"] == HISTORY_BATCH_SIZE
    assert result["status"] == "completed"
    assert result["progress"]["current_status"] is None
    assert result["progress"]["next_page"] == 1


def test_legacy_history_checkpoint_keeps_its_original_batch_size():
    factory = session_factory()
    settings = reconciliation_settings()

    class Client:
        last_response_headers = {"X-WP-Total": "0", "X-WP-TotalPages": "0"}

        def __init__(self):
            self.per_page = None

        def list_orders(self, **kwargs):
            self.per_page = kwargs["per_page"]
            return []

    remote = Client()
    with factory() as db:
        job = enqueue_order_history_import(db, "pytest", settings)
        progress = dict(job.progress or {})
        progress.pop("batch_size")
        job.progress = progress
        db.commit()

    process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)

    assert remote.per_page == BATCH_SIZE


def test_historical_import_does_not_verify_coverage_if_woo_pagination_changes():
    factory = session_factory()
    settings = reconciliation_settings()
    rows = [{**remote_order(order_id), "status": "completed"} for order_id in range(1, 27)]

    class Client:
        def __init__(self):
            self.last_response_headers = {}

        def list_orders(self, **kwargs):
            total = 26 if kwargs["page"] == 1 else 25
            self.last_response_headers = {
                "X-WP-Total": str(total),
                "X-WP-TotalPages": "2" if kwargs["page"] == 1 else "1",
            }
            start = (kwargs["page"] - 1) * kwargs["per_page"]
            return rows[start:start + kwargs["per_page"]]

    remote = Client()
    with factory() as db:
        enqueue_order_history_import(db, "pytest", settings)

    result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)
    result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)

    assert result["status"] == "completed"
    assert result["progress"]["pagination_changed"] is True
    assert result["progress"]["coverage_complete"] is False


def test_historical_import_does_not_verify_coverage_for_duplicate_page_ids():
    factory = session_factory()
    settings = reconciliation_settings()
    first_page = [{**remote_order(order_id), "status": "completed"} for order_id in range(1, HISTORY_BATCH_SIZE + 1)]

    class Client:
        last_response_headers = {"X-WP-Total": str(HISTORY_BATCH_SIZE + 1), "X-WP-TotalPages": "2"}

        def list_orders(self, **kwargs):
            return first_page if kwargs["page"] == 1 else [first_page[-1]]

    remote = Client()
    with factory() as db:
        enqueue_order_history_import(db, "pytest", settings)

    result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)
    result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)

    assert result["status"] == "completed"
    assert result["total_remote_records"] == HISTORY_BATCH_SIZE + 1
    assert result["progress"]["distinct_remote_records"] == HISTORY_BATCH_SIZE
    assert result["progress"]["coverage_complete"] is False


def test_historical_import_does_not_mutate_an_existing_operational_order():
    factory = session_factory()
    with factory() as db:
        existing = Order(
            woo_order_id=700,
            woo_order_number="700",
            woo_status="processing",
            local_status="allocated",
            allocation_status="allocated",
            pick_status="ready_to_pick",
            completion_status="open",
        )
        existing.items.append(OrderItem(
            woo_order_item_id=7001,
            quantity_ordered=Decimal("2"),
            quantity_allocated=Decimal("2"),
            allocated_qty=Decimal("2"),
            allocation_status="allocated",
            pick_status="not_ready",
        ))
        db.add(existing)
        db.commit()

        run, _summary = commit_remote_order_records(
            db,
            [{**remote_order(700), "status": "cancelled"}],
            ["cancelled"],
            "pytest-history",
            snapshot_only=True,
        )

        db.refresh(existing)
        assert run.updated_count == 1
        assert existing.woo_status == "processing"
        assert existing.local_status == "allocated"
        assert existing.allocation_status == "allocated"
        assert existing.pick_status == "ready_to_pick"
        assert existing.items[0].quantity_allocated == Decimal("2")


def test_historical_order_seen_as_operational_is_promoted():
    factory = session_factory()
    with factory() as db:
        commit_remote_order_records(
            db,
            [
                {**remote_order(701), "status": "completed"},
                {**remote_order(702), "status": "completed"},
            ],
            ["completed"],
            "pytest-history",
            snapshot_only=True,
        )
        commit_remote_order_records(
            db,
            [
                remote_order(701),
                {**remote_order(702), "status": "completed", "payment_method": "foosales_pos"},
            ],
            ["processing", "completed"],
            "pytest-order-sync",
        )

        orders = list(db.scalars(select(Order).where(Order.woo_order_id.in_([701, 702]))).all())
        assert all(order.is_historical_snapshot is False for order in orders)
        assert {order.woo_status for order in orders} == {"processing", "completed"}


def test_normal_sync_restores_a_returned_terminal_snapshot_to_reporting():
    factory = session_factory()
    record = {**remote_order(703), "status": "completed", "total": "15.00"}
    with factory() as db:
        commit_remote_order_records(db, [record], ["completed"], "pytest-history", snapshot_only=True)
        order = db.scalars(select(Order).where(Order.woo_order_id == 703)).one()
        order.historical_source_present = False
        db.commit()

        commit_remote_order_records(db, [record], ["completed"], "pytest-order-sync")

        db.refresh(order)
        assert order.is_historical_snapshot is True
        assert order.historical_source_present is True
        assert build_today(db, datetime(2026, 7, 26).date())["summary"]["today_orders_count"] == 1


def test_historical_snapshots_feed_sales_and_lifetime_customer_metrics():
    factory = session_factory()
    older = {
        **remote_order(710),
        "status": "completed",
        "total": "10.00",
        "date_created_gmt": "2026-06-26T12:00:00",
        "date_modified_gmt": "2026-06-26T12:00:00",
        "billing": {"email": "returning@example.invalid"},
    }
    recent = {
        **remote_order(711),
        "status": "completed",
        "total": "20.00",
        "billing": {"email": "returning@example.invalid"},
        "line_items": [{"id": 7110, "name": "Historical Item", "quantity": 2, "total": "20.00"}],
    }
    anonymous = {
        **remote_order(712),
        "status": "completed",
        "total": "10.00",
        "billing": {},
        "line_items": [{"id": 7120, "name": "POS Item", "quantity": 1, "total": "10.00"}],
    }

    with factory() as db:
        commit_remote_order_records(
            db,
            [older, recent, anonymous],
            ["completed"],
            "pytest-history",
            snapshot_only=True,
        )

        summary = build_today(db, datetime(2026, 7, 26).date())["summary"]
        assert summary["today_orders_count"] == 2
        assert summary["today_revenue"] == 30
        assert summary["today_units_sold"] == 3
        assert summary["today_new_customers"] == 0
        assert summary["today_returning_customers"] == 1


def test_historical_import_retries_the_same_checkpoint_without_double_counting():
    factory = session_factory()
    settings = reconciliation_settings()
    orders = [{**remote_order(order_id), "status": "completed"} for order_id in range(1, HISTORY_BATCH_SIZE + 2)]

    class FlakyClient:
        def __init__(self):
            self.calls = []
            self.fail_page_two_once = True
            self.last_response_headers = {}

        def list_orders(self, **kwargs):
            self.calls.append((kwargs["status"], kwargs["page"]))
            rows = orders if kwargs["status"] == "any" else []
            self.last_response_headers = {
                "x-wp-total": str(len(rows)),
                "x-wp-totalpages": str((len(rows) + kwargs["per_page"] - 1) // kwargs["per_page"]),
            }
            if kwargs["status"] == "any" and kwargs["page"] == 2 and self.fail_page_two_once:
                self.fail_page_two_once = False
                raise WooCommerceClientError("Temporary WooCommerce failure.")
            start = (kwargs["page"] - 1) * kwargs["per_page"]
            return rows[start:start + kwargs["per_page"]]

    remote = FlakyClient()
    with factory() as db:
        enqueue_order_history_import(db, "pytest", settings)

    first = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)
    failed_page = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)
    assert first["total_remote_records"] == HISTORY_BATCH_SIZE
    assert failed_page["status"] == "queued"
    assert failed_page["total_remote_records"] == HISTORY_BATCH_SIZE
    assert failed_page["progress"]["next_page"] == 2

    result = failed_page
    while result["status"] == "queued":
        result = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)

    assert result["status"] == "completed"
    assert result["total_remote_records"] == HISTORY_BATCH_SIZE + 1
    assert result["created_count"] == HISTORY_BATCH_SIZE + 1
    assert remote.calls[:3] == [("any", 1), ("any", 2), ("any", 2)]


def test_verified_history_rerun_excludes_snapshots_no_longer_returned_by_woo():
    factory = session_factory()
    settings = reconciliation_settings()

    class Client:
        def __init__(self):
            self.rows = [
                {**remote_order(801), "status": "completed", "total": "10.00"},
                {**remote_order(802), "status": "completed", "total": "20.00"},
            ]
            self.last_response_headers = {}

        def list_orders(self, **kwargs):
            self.last_response_headers = {
                "X-WP-Total": str(len(self.rows)),
                "X-WP-TotalPages": "1",
            }
            return self.rows if kwargs["page"] == 1 else []

    remote = Client()
    with factory() as db:
        enqueue_order_history_import(db, "pytest", settings)
    first = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)
    assert first["progress"]["coverage_complete"] is True

    remote.rows = remote.rows[:1]
    with factory() as db:
        enqueue_order_history_import(db, "pytest", settings)
    second = process_next_order_history_import(settings, session_factory=factory, client_factory=lambda _settings: remote)

    assert second["progress"]["coverage_complete"] is True
    assert second["progress"]["source_absent_snapshot_count"] == 1
    with factory() as db:
        absent = db.scalars(select(Order).where(Order.woo_order_id == 802)).one()
        assert absent.is_historical_snapshot is True
        assert absent.historical_source_present is False
        assert build_today(db, datetime(2026, 7, 26).date())["summary"]["today_orders_count"] == 1
        coverage = order_history_coverage(db, settings)
        assert coverage["local_order_count"] == 1
        assert coverage["historical_snapshot_count"] == 1
        assert coverage["source_absent_snapshot_count"] == 1
