from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import sessionmaker

from app.db.session import make_engine
from app.api.routes.auth import login as login_user
from app.core.config import Settings
from app.models.auth import User
from app.models.allocations import Allocation, AllocationLine
from app.models.inventory import InventoryItem, InventoryItemLocation, InventoryLocation, StockMovement
from app.models.orders import Order, OrderItem
from app.models.performance import MetricVersion
from app.models.receipts import Receipt
from app.models.woocommerce import WooCommerceSyncError, WooCommerceSyncRun, WooStockSyncJob
from app.schemas.picks import PickRequest
from app.schemas.receipts import DirectReceiptRequest
from app.schemas.auth import LoginRequest
from app.services.auth import hash_password
from app.services.location_inventory import create_committed_adjustment
from app.services.metric_cache import current_metric_version, invalidate_metrics
from app.api.routes.locations import ensure_location_has_no_stock
from app.services.order_workflow import complete_picked_order
from app.services.picks import commit_pick, unpick_orders
from app.services.receiving import commit_direct_receipt
from app.services.woocommerce_stock_sync_jobs import POSTGRES_STOCK_JOB_WORKER_LOCK_KEY, process_next_stock_sync_job
from app.services.woocommerce_sync_errors import store_sync_error_once


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for migration index verification")
def test_postgres_reporting_indexes_keep_intended_expressions_and_predicates():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT index_class.relname AS name, "
                "pg_get_expr(index_row.indexprs, index_row.indrelid) AS expressions, "
                "pg_get_expr(index_row.indpred, index_row.indrelid) AS predicate "
                "FROM pg_index AS index_row "
                "JOIN pg_class AS index_class ON index_class.oid = index_row.indexrelid "
                "JOIN pg_class AS table_class ON table_class.oid = index_row.indrelid "
                "JOIN pg_namespace AS namespace ON namespace.oid = table_class.relnamespace "
                "WHERE namespace.nspname = 'public' AND table_class.relname = 'orders' "
                "AND index_class.relname IN "
                "('ix_orders_reporting_date', 'ix_orders_reporting_customer_date')"
            )
        ).mappings().all()

    definitions = {row["name"]: row for row in rows}
    assert set(definitions) == {"ix_orders_reporting_date", "ix_orders_reporting_customer_date"}
    expected_date = "coalesce(placed_on, date_created, completed_on, created_at)"
    expected_predicate_parts = {"is_historical_snapshot = false", "historical_source_present = true"}

    for definition in definitions.values():
        expressions = " ".join((definition["expressions"] or "").lower().split())
        predicate = " ".join((definition["predicate"] or "").lower().split())
        assert expected_date in expressions
        assert all(part in predicate for part in expected_predicate_parts)

    customer_expressions = " ".join(definitions["ix_orders_reporting_customer_date"]["expressions"].lower().split())
    assert "lower(trim(both from customer_email))" in customer_expressions


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_metric_version_initialization_is_atomic():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with sessions() as db:
        db.execute(delete(MetricVersion).where(MetricVersion.id == 1))
        db.commit()

    barrier = Barrier(4)

    def read_version() -> int:
        with sessions() as db:
            barrier.wait()
            version = current_metric_version(db)
            db.commit()
            return version

    def invalidate() -> None:
        with sessions() as db:
            barrier.wait()
            invalidate_metrics(db)
            db.commit()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(read_version) for _ in range(2)]
        futures.extend(pool.submit(invalidate) for _ in range(2))
        results = [future.result() for future in futures]

    assert all(version in {0, 1, 2} for version in results[:2])
    with sessions() as db:
        assert db.scalar(select(func.count(MetricVersion.id)).where(MetricVersion.id == 1)) == 1
        assert current_metric_version(db) == 2


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_sync_error_deduplication_is_atomic():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    with sessions() as db:
        run = WooCommerceSyncRun(sync_type="products", status="completed")
        db.add(run)
        db.commit()
        run_id = run.id

    barrier = Barrier(2)

    def store() -> bool:
        with sessions() as db:
            barrier.wait()
            created = store_sync_error_once(
                db,
                sync_run_id=run_id,
                remote_product_id=991,
                sku=f"PG-SYNC-ERROR-{suffix}",
                error_message="same concurrent failure",
                raw_payload={"test": suffix},
            )
            db.commit()
            return created

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: store(), range(2)))

    assert sorted(outcomes) == [False, True]
    with sessions() as db:
        assert db.scalar(select(func.count(WooCommerceSyncError.id)).where(WooCommerceSyncError.sync_run_id == run_id)) == 1


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_stock_decrements_serialize():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    assert engine.dialect.name == "postgresql"
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    with sessions() as db:
        location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code=f"PG-{suffix}", location_name=f"PG {suffix}", active=True)
        item = InventoryItem(sku=f"PG-CONCURRENT-{suffix}", in_stock=5, allocated=0, sellable=5, active=True, non_inventory=False)
        db.add_all([location, item])
        db.flush()
        row = InventoryItemLocation(inventory_item_id=item.id, location_id=location.id, warehouse=location.warehouse, inventory_location=location.location_name, in_stock=5, allocated=0, sellable=5, active=True)
        db.add(row)
        db.commit()
        item_id, row_id = item.id, row.id

    barrier = Barrier(2)

    def decrement(key: str) -> str:
        with sessions() as db:
            item = db.get(InventoryItem, item_id)
            row = db.get(InventoryItemLocation, row_id)
            barrier.wait()
            try:
                create_committed_adjustment(db, item=item, row=row, quantity_change=Decimal("-4"), adjustment_type="manual_decrease", reason="PostgreSQL concurrency test", idempotency_key=key)
                db.commit()
                return "committed"
            except ValueError:
                db.rollback()
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decrement, [f"pg-a-{suffix}", f"pg-b-{suffix}"]))

    assert sorted(outcomes) == ["committed", "rejected"]
    with sessions() as db:
        assert db.get(InventoryItem, item_id).in_stock == Decimal("1.000")
        assert db.get(InventoryItemLocation, row_id).in_stock == Decimal("1.000")
        assert db.scalar(select(func.count(StockMovement.id)).where(StockMovement.inventory_item_id == item_id)) == 1


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_receipt_retries_apply_once():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    with sessions() as db:
        location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code=f"RCV-{suffix}", location_name=f"RCV {suffix}", active=True)
        item = InventoryItem(sku=f"PG-RECEIPT-{suffix}", in_stock=0, allocated=0, sellable=0, active=True, non_inventory=False)
        db.add_all([location, item])
        db.flush()
        db.add(InventoryItemLocation(inventory_item_id=item.id, location_id=location.id, warehouse=location.warehouse, inventory_location=location.location_name, in_stock=0, allocated=0, sellable=0, active=True))
        db.commit()
        item_id = item.id

    payload = DirectReceiptRequest(
        idempotency_key=f"pg-receipt-{suffix}",
        warehouse="Main Warehouse",
        lines=[{"sku": f"PG-RECEIPT-{suffix}", "inventory_location": f"RCV-{suffix}", "quantity_received": 2, "unit_cost": 3}],
    )
    barrier = Barrier(2)

    def receive() -> int:
        with sessions() as db:
            barrier.wait()
            return commit_direct_receipt(payload, db)[0].id

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipt_ids = list(pool.map(lambda _: receive(), range(2)))

    assert receipt_ids[0] == receipt_ids[1]
    with sessions() as db:
        assert db.get(InventoryItem, item_id).in_stock == Decimal("2.000")
        assert db.scalar(select(func.count(Receipt.id)).where(Receipt.id == receipt_ids[0])) == 1
        assert db.scalar(select(func.count(StockMovement.id)).where(StockMovement.inventory_item_id == item_id)) == 1


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_completion_and_unpick_cannot_both_commit():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    with sessions() as db:
        location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code=f"ORD-{suffix}", location_name=f"ORD {suffix}", active=True)
        item = InventoryItem(sku=f"PG-ORDER-{suffix}", in_stock=5, allocated=1, sellable=4, active=True, non_inventory=False)
        db.add_all([location, item])
        db.flush()
        stock = InventoryItemLocation(inventory_item_id=item.id, location_id=location.id, warehouse=location.warehouse, inventory_location=location.location_name, in_stock=5, allocated=1, sellable=4, active=True, is_default_location=True)
        order = Order(order_number=f"PG-ORDER-{suffix}", woo_status="processing", local_status="allocated", allocation_status="allocated", pick_status="ready_to_pick")
        db.add_all([stock, order])
        db.flush()
        line = OrderItem(order_id=order.id, inventory_item_id=item.id, sku=item.sku, quantity_ordered=1, quantity_allocated=1, quantity_picked=0, quantity_fulfilled=0, quantity_stock_reduced=0, ordered_qty=1, allocated_qty=1, picked_qty=0, fulfilled_qty=0, matched_status="matched", allocation_status="allocated", pick_status="ready_to_pick", sellable_snapshot=4, shortage_quantity=0)
        allocation = Allocation(allocation_number=f"PG-ALLOC-{suffix}", status="posted", allocation_type="single_order", order_id=order.id, allocation_source="manual")
        db.add_all([line, allocation])
        db.flush()
        db.add(AllocationLine(allocation_id=allocation.id, order_id=order.id, order_line_id=line.id, item_id=item.id, inventory_item_location_id=stock.id, sku=item.sku, warehouse=stock.warehouse, inventory_location=stock.inventory_location, quantity_ordered=1, quantity_previously_allocated=0, quantity_to_allocate=1, quantity_allocated_after=1, in_stock_before=5, allocated_before=0, sellable_before=5, allocated_after=1, sellable_after=4, shortage_quantity=0, status="allocated", allocation_source="manual"))
        db.commit()
        order_id, item_id = order.id, item.id
        picked = commit_pick(db, PickRequest(idempotency_key=f"pg-pick-{suffix}", order_ids=[order_id], allow_partial=False))
        assert picked.status == "posted"

    barrier = Barrier(2)

    def complete() -> str:
        with sessions() as db:
            barrier.wait()
            try:
                return complete_picked_order(db, order_id)["status"]
            except ValueError:
                db.rollback()
                return "rejected"

    def unpick() -> str:
        with sessions() as db:
            barrier.wait()
            return unpick_orders(db, [order_id], idempotency_key=f"pg-unpick-{suffix}")["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        complete_result = pool.submit(complete)
        unpick_result = pool.submit(unpick)
        outcomes = {"complete": complete_result.result(), "unpick": unpick_result.result()}

    assert sorted(outcomes.values()) == ["completed", "rejected"]
    with sessions() as db:
        item = db.get(InventoryItem, item_id)
        order = db.get(Order, order_id)
        line = db.scalar(select(OrderItem).where(OrderItem.order_id == order_id))
        if outcomes["complete"] == "completed":
            assert item.in_stock == Decimal("4.000")
            assert line.quantity_picked == Decimal("1.000")
            assert order.local_status == "completed"
        else:
            assert item.in_stock == Decimal("5.000")
            assert line.quantity_picked == Decimal("0.000")
            assert order.local_status != "completed"


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_location_deactivation_and_receipt_cannot_both_commit():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    with sessions() as db:
        location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code=f"LOC-{suffix}", location_name=f"LOC {suffix}", active=True)
        item = InventoryItem(sku=f"PG-LOCATION-{suffix}", in_stock=0, allocated=0, sellable=0, active=True, non_inventory=False)
        db.add_all([location, item])
        db.flush()
        db.add(InventoryItemLocation(inventory_item_id=item.id, location_id=location.id, warehouse=location.warehouse, inventory_location=location.location_name, in_stock=0, allocated=0, sellable=0, active=True))
        db.commit()
        location_id, item_id = location.id, item.id

    payload = DirectReceiptRequest(
        idempotency_key=f"pg-location-receipt-{suffix}",
        warehouse="Main Warehouse",
        lines=[{"sku": f"PG-LOCATION-{suffix}", "inventory_location": f"LOC {suffix}", "quantity_received": 2, "unit_cost": 3}],
    )
    barrier = Barrier(2)

    def deactivate() -> str:
        with sessions() as db:
            location = db.get(InventoryLocation, location_id)
            barrier.wait()
            try:
                ensure_location_has_no_stock(db, location)
                location.active = False
                db.commit()
                return "committed"
            except Exception:
                db.rollback()
                return "rejected"

    def receive() -> str:
        with sessions() as db:
            barrier.wait()
            try:
                commit_direct_receipt(payload, db)
                return "committed"
            except Exception:
                db.rollback()
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        deactivate_result = pool.submit(deactivate)
        receive_result = pool.submit(receive)
        outcomes = [deactivate_result.result(), receive_result.result()]

    assert sorted(outcomes) == ["committed", "rejected"]
    with sessions() as db:
        location = db.get(InventoryLocation, location_id)
        item = db.get(InventoryItem, item_id)
        assert (location.active, item.in_stock) in {(False, Decimal("0.000")), (True, Decimal("2.000"))}


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_location_deactivation_and_adjustment_cannot_both_commit():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    with sessions() as db:
        location = InventoryLocation(client="Pongo", warehouse="Main Warehouse", location_code=f"ADJ-{suffix}", location_name=f"ADJ {suffix}", active=True)
        item = InventoryItem(sku=f"PG-ADJUST-{suffix}", in_stock=0, allocated=0, sellable=0, active=True, non_inventory=False)
        db.add_all([location, item])
        db.flush()
        row = InventoryItemLocation(inventory_item_id=item.id, location_id=location.id, warehouse=location.warehouse, inventory_location=location.location_name, in_stock=0, allocated=0, sellable=0, active=True)
        db.add(row)
        db.commit()
        location_id, item_id, row_id = location.id, item.id, row.id

    barrier = Barrier(2)

    def deactivate() -> str:
        with sessions() as db:
            location = db.get(InventoryLocation, location_id)
            barrier.wait()
            try:
                ensure_location_has_no_stock(db, location)
                location.active = False
                db.commit()
                return "committed"
            except Exception:
                db.rollback()
                return "rejected"

    def adjust() -> str:
        with sessions() as db:
            item = db.get(InventoryItem, item_id)
            row = db.get(InventoryItemLocation, row_id)
            barrier.wait()
            try:
                create_committed_adjustment(db, item=item, row=row, quantity_change=Decimal("1"), adjustment_type="found", reason="PostgreSQL location race", idempotency_key=f"pg-location-adjust-{suffix}")
                db.commit()
                return "committed"
            except Exception:
                db.rollback()
                return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        deactivate_result = pool.submit(deactivate)
        adjustment_result = pool.submit(adjust)
        outcomes = [deactivate_result.result(), adjustment_result.result()]

    assert sorted(outcomes) == ["committed", "rejected"]
    with sessions() as db:
        location = db.get(InventoryLocation, location_id)
        item = db.get(InventoryItem, item_id)
        assert (location.active, item.in_stock) in {(False, Decimal("0.000")), (True, Decimal("1.000"))}


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for real transaction locking")
def test_concurrent_postgres_login_failures_enforce_lockout():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    suffix = uuid4().hex[:10]
    email = f"pg-login-{suffix}@example.com"
    with sessions() as db:
        db.add(User(email=email, display_name="PostgreSQL Login", password_hash=hash_password("correct-horse-battery-staple"), active=True, failed_login_count=0))
        db.commit()

    settings = Settings(_env_file=None, app_env="test", auth_max_failed_logins=3)
    barrier = Barrier(3)

    def fail_login() -> int:
        with sessions() as db:
            barrier.wait()
            try:
                login_user(LoginRequest(email=email, password="wrong-password"), Response(), db, settings)
            except HTTPException as error:
                return error.status_code
            raise AssertionError("Wrong password unexpectedly succeeded")

    with ThreadPoolExecutor(max_workers=3) as pool:
        statuses = list(pool.map(lambda _index: fail_login(), range(3)))

    assert statuses == [401, 401, 401]
    with sessions() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user.locked_until is not None
        with pytest.raises(HTTPException) as locked:
            login_user(LoginRequest(email=email, password="correct-horse-battery-staple"), Response(), db, settings)
        assert locked.value.status_code == 429


@pytest.mark.skipif(not os.environ.get("PONGO_TEST_POSTGRES_URL"), reason="PONGO_TEST_POSTGRES_URL is required for PostgreSQL advisory locks")
def test_postgres_stock_job_worker_releases_advisory_lock():
    engine = make_engine(os.environ["PONGO_TEST_POSTGRES_URL"])
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with sessions() as db:
        db.execute(delete(WooStockSyncJob))
        db.commit()
    process_next_stock_sync_job(Settings(_env_file=None, app_env="test"), db_factory=sessions)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": POSTGRES_STOCK_JOB_WORKER_LOCK_KEY}) is True
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": POSTGRES_STOCK_JOB_WORKER_LOCK_KEY})
