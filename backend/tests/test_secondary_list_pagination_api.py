from datetime import date, datetime, timezone

from sqlalchemy import event

from app.db.session import get_db
from app.main import app
from app.models.cycle_counts import CycleCount
from app.models.inventory import InventoryTransfer, StockAdjustment
from app.models.routes import Route
from app.models.woocommerce import (
    WooCommerceSyncError,
    WooCommerceSyncRun,
    WooItemMapping,
    WooStockSyncJob,
    WooWritebackQueue,
)
from app.services.woocommerce_order_reconciliation import ORDER_JOB_SYNC_TYPE
from app.services.woocommerce_remap import list_remap_candidates
from tests.test_items_api import client, seed_item  # noqa: F401


FIXED_TIME = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def write_rows(rows) -> None:
    dependency = app.dependency_overrides[get_db]()
    db = next(dependency)
    try:
        db.add_all(rows)
        db.commit()
    finally:
        dependency.close()


def assert_second_page(body: dict, collection_key: str, expected_total: int = 3) -> None:
    assert body["total"] == expected_total
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert body["total_pages"] == 2
    assert body["returned_count"] == 1
    assert body["has_previous"] is True
    assert body["has_next"] is False
    assert len(body[collection_key]) == 1


def test_route_history_is_sql_filtered_paginated_and_clamps_out_of_range(client):
    write_rows(
        [
            Route(route_number="RT-1", status="draft", route_date=None, total_stops=0, created_at=FIXED_TIME),
            Route(route_number="RT-2", status="draft", route_date=date(2026, 8, 7), total_stops=0, created_at=FIXED_TIME),
            Route(route_number="RT-3", status="draft", route_date=date(2026, 8, 9), total_stops=0, created_at=FIXED_TIME),
            Route(route_number="RT-4", status="cancelled", route_date=date(2026, 8, 10), total_stops=0, created_at=FIXED_TIME),
        ]
    )

    response = client.get(
        "/api/routes",
        params={"status": "draft", "date_from": "2026-08-08", "page": 999, "page_size": 1},
    )

    assert response.status_code == 200
    body = response.json()
    # The legacy date filter intentionally keeps routes without a route date.
    assert body["total"] == 2
    assert body["page"] == 2
    assert body["total_pages"] == 2
    assert body["returned_count"] == 1
    assert body["has_previous"] is True
    assert body["has_next"] is False
    assert body["routes"][0]["route_number"] == "RT-1"


def test_cycle_count_history_returns_exact_total_and_standard_metadata(client):
    write_rows(
        [
            CycleCount(count_number=f"CC-{index}", status="posted", warehouse="Main", count_type="selected_items", created_at=FIXED_TIME)
            for index in range(1, 4)
        ]
    )

    response = client.get("/api/cycle-counts", params={"page": 2, "page_size": 2})

    assert response.status_code == 200
    assert_second_page(response.json(), "cycle_counts")
    assert response.json()["cycle_counts"][0]["count_number"] == "CC-1"


def test_transfer_and_adjustment_histories_are_paginated_with_filtered_totals(client):
    write_rows(
        [
            InventoryTransfer(transfer_number=f"TR-{index}", status="posted", created_at=FIXED_TIME)
            for index in range(1, 4)
        ]
        + [InventoryTransfer(transfer_number="TR-DRAFT", status="draft", created_at=FIXED_TIME)]
        + [
            StockAdjustment(
                adjustment_number=f"ADJ-{index}",
                status="posted",
                adjustment_type="correction",
                reason="Pagination test",
                created_at=FIXED_TIME,
            )
            for index in range(1, 4)
        ]
        + [
            StockAdjustment(
                adjustment_number="ADJ-DAMAGE",
                status="posted",
                adjustment_type="damage",
                reason="Pagination test",
                created_at=FIXED_TIME,
            )
        ]
    )

    transfers = client.get(
        "/api/inventory/transfers",
        params={"status": "posted", "page": 2, "page_size": 2},
    )
    adjustments = client.get(
        "/api/inventory/adjustments",
        params={"adjustment_type": "correction", "page": 2, "page_size": 2},
    )

    assert transfers.status_code == 200
    assert adjustments.status_code == 200
    assert_second_page(transfers.json(), "transfers")
    assert_second_page(adjustments.json(), "adjustments")
    assert transfers.json()["transfers"][0]["transfer_number"] == "TR-1"
    assert adjustments.json()["adjustments"][0]["adjustment_number"] == "ADJ-1"


def test_woo_writeback_histories_return_exact_totals_and_paginated_results(client):
    queue_rows = [
        WooWritebackQueue(
            operation_type="update_product_stock",
            entity_type="inventory_item",
            entity_id=index,
            payload_json={"stock_quantity": index},
            status=status,
            environment="staging",
            dry_run=True,
            preview_json={"item_id": index},
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
        for index, status in enumerate(["sent", "failed", "cancelled", "pending"], start=1)
    ]
    stock_jobs = [
        WooStockSyncJob(
            idempotency_key=f"stock-job-{index}",
            status="completed",
            force=False,
            requested_by="pytest",
            chunk_size=25,
            created_at=FIXED_TIME,
            updated_at=FIXED_TIME,
        )
        for index in range(1, 4)
    ]
    write_rows(queue_rows + stock_jobs)

    queue = client.get(
        "/api/integrations/woocommerce/writeback/queue",
        params={"page": 2, "page_size": 2},
    )
    logs = client.get(
        "/api/integrations/woocommerce/writeback/logs",
        params={"page": 2, "page_size": 2},
    )
    jobs = client.get(
        "/api/integrations/woocommerce/writeback/stock/jobs",
        params={"page": 2, "page_size": 2},
    )
    searched_queue = client.get(
        "/api/integrations/woocommerce/writeback/queue",
        params={"status": "sent", "search": "INVENTORY_ITEM"},
    )

    assert queue.status_code == 200
    assert logs.status_code == 200
    assert jobs.status_code == 200
    assert searched_queue.status_code == 200
    assert queue.json()["total"] == 4
    assert queue.json()["returned_count"] == 2
    assert_second_page(logs.json(), "queue")
    assert_second_page(jobs.json(), "jobs")
    assert [row["status"] for row in logs.json()["queue"]] == ["sent"]
    assert searched_queue.json()["total"] == 1
    assert searched_queue.json()["queue"][0]["entity_id"] == 1


def test_secondary_history_page_size_is_capped_at_one_hundred(client):
    endpoints = [
        "/api/routes",
        "/api/cycle-counts",
        "/api/inventory/transfers",
        "/api/inventory/adjustments",
        "/api/integrations/woocommerce/writeback/queue",
        "/api/integrations/woocommerce/writeback/logs",
        "/api/integrations/woocommerce/writeback/stock/jobs",
        "/api/integrations/woocommerce/orders/fetch-jobs",
        "/api/integrations/woocommerce/remap/candidates",
        "/api/integrations/woocommerce/remap/mappings",
    ]

    for endpoint in endpoints:
        assert client.get(endpoint, params={"page_size": 101}).status_code == 422

    assert client.get(
        "/api/integrations/woocommerce/sync-runs/1",
        params={"error_page_size": 101},
    ).status_code == 422


def test_remap_mappings_use_sql_filters_exact_total_and_pagination(client):
    items = [seed_item(client, sku=f"MAP-{index}", wooProductId=7000 + index) for index in range(1, 4)]
    write_rows(
        [
            WooItemMapping(
                item_id=item["id"],
                woo_product_id=7000 + index,
                woo_sku=f"map-{index}",
                mapping_source="manual",
                confidence=100,
                active=True,
                created_at=FIXED_TIME,
                updated_at=FIXED_TIME,
            )
            for index, item in enumerate(items, start=1)
        ]
    )

    response = client.get(
        "/api/integrations/woocommerce/remap/mappings",
        params={"sku": "MAP-", "page": 999, "page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert_second_page(body, "mappings")
    assert body["mappings"][0]["woo_sku"] == "map-1"


def test_remap_candidates_page_catalog_then_recent_unmapped_errors(client):
    for index in range(1, 4):
        seed_item(client, sku=f"CAND-{index}", wooProductId=8000 + index)
    run = WooCommerceSyncRun(sync_type="products", status="completed", started_at=FIXED_TIME)
    write_rows(
        [
            run,
            WooCommerceSyncError(
                sync_run=run,
                remote_product_id=8001,
                sku="DUPLICATE-ITEM-REMOTE",
                error_message="Existing item wins candidate deduplication",
                fingerprint="candidate-duplicate",
                created_at=FIXED_TIME,
            ),
            WooCommerceSyncError(
                sync_run=run,
                remote_product_id=8999,
                sku="ERR-ONLY",
                error_message="Error-only remote",
                fingerprint="candidate-error-only",
                created_at=FIXED_TIME,
            ),
        ]
    )

    response = client.get(
        "/api/integrations/woocommerce/remap/candidates",
        params={"page": 2, "page_size": 2},
    )
    searched = client.get(
        "/api/integrations/woocommerce/remap/candidates",
        params={"search": "err-only", "page_size": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["page"] == 2
    assert body["returned_count"] == 2
    assert [row["remote"]["woo_product_id"] for row in body["candidates"]] == [8001, 8999]
    assert searched.json()["total"] == 1
    assert searched.json()["candidates"][0]["remote"]["woo_product_id"] == 8999


def test_remap_candidates_include_error_only_remotes_beyond_two_hundred(client):
    for index in range(1, 4):
        seed_item(client, sku=f"CATALOG-{index}", wooProductId=8000 + index)
    run = WooCommerceSyncRun(sync_type="products", status="completed_with_errors", started_at=FIXED_TIME)
    errors = [
        WooCommerceSyncError(
            sync_run=run,
            remote_product_id=9000 + index,
            sku=f"ERR-{index:03d}",
            error_message=f"Unresolved remote {index:03d}",
            fingerprint=f"candidate-completeness-{index}",
            created_at=FIXED_TIME,
        )
        for index in range(225)
    ]
    # A newer error for an existing remote must replace its older metadata,
    # without increasing the exact unique-remote total.
    errors.append(
        WooCommerceSyncError(
            sync_run=run,
            remote_product_id=9000,
            sku="ERR-000-LATEST",
            error_message="Latest unresolved remote metadata",
            fingerprint="candidate-completeness-0-latest",
            created_at=FIXED_TIME,
        )
    )
    write_rows([run, *errors])

    first_page = client.get(
        "/api/integrations/woocommerce/remap/candidates",
        params={"page": 1, "page_size": 100},
    )
    last_page = client.get(
        "/api/integrations/woocommerce/remap/candidates",
        params={"page": 3, "page_size": 100},
    )
    oldest_search = client.get(
        "/api/integrations/woocommerce/remap/candidates",
        params={"search": "ERR-000-LATEST", "page_size": 1},
    )

    assert first_page.status_code == 200
    assert first_page.json()["returned_count"] == 100
    assert last_page.status_code == 200
    body = last_page.json()
    assert body["total"] == 228
    assert body["total_pages"] == 3
    assert body["returned_count"] == 28
    assert body["candidates"][-1]["remote"]["woo_product_id"] == 9001
    assert oldest_search.status_code == 200
    assert oldest_search.json()["total"] == 1
    assert oldest_search.json()["candidates"][0]["remote"]["woo_product_id"] == 9000
    assert oldest_search.json()["candidates"][0]["remote"]["woo_name"] == "Latest unresolved remote metadata"


def test_remap_candidate_query_count_does_not_grow_with_page_size(client):
    items = [seed_item(client, sku=f"QUERY-{index}", wooProductId=10000 + index) for index in range(20)]
    write_rows(
        [
            WooItemMapping(
                item_id=item["id"],
                woo_product_id=10000 + index,
                woo_sku=f"QUERY-{index}",
                woo_name="API Test Item",
                mapping_source="manual",
                confidence=100,
                active=True,
                created_at=FIXED_TIME,
                updated_at=FIXED_TIME,
            )
            for index, item in enumerate(items)
        ]
    )

    def query_count(page_size: int) -> tuple[int, object]:
        statements: list[str] = []

        def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
            normalized = " ".join(statement.casefold().split())
            if normalized.startswith("select") and any(
                table in normalized
                for table in ("inventory_items", "woocommerce_sync_errors", "woo_item_mappings")
            ):
                statements.append(normalized)

        dependency = app.dependency_overrides[get_db]()
        db = next(dependency)
        event.listen(client.test_engine, "before_cursor_execute", capture_statement)
        try:
            response = list_remap_candidates(db, page=1, page_size=page_size)
        finally:
            event.remove(client.test_engine, "before_cursor_execute", capture_statement)
            dependency.close()
        return len(statements), response

    one_count, one_candidate = query_count(1)
    full_count, full_page = query_count(20)

    assert one_candidate.returned_count == 1
    assert full_page.returned_count == 20
    assert all(candidate.current_mapping is not None for candidate in full_page.candidates)
    assert full_count == one_count
    assert full_count <= 6


def test_order_fetch_jobs_have_exact_filtered_total_and_pages(client):
    write_rows(
        [
            WooCommerceSyncRun(
                sync_type=ORDER_JOB_SYNC_TYPE,
                status="completed",
                started_at=FIXED_TIME,
                created_by="pytest",
            )
            for _ in range(3)
        ]
        + [WooCommerceSyncRun(sync_type="products", status="completed", started_at=FIXED_TIME)]
    )

    response = client.get(
        "/api/integrations/woocommerce/orders/fetch-jobs",
        params={"page": 999, "page_size": 2},
    )

    assert response.status_code == 200
    assert_second_page(response.json(), "sync_runs")


def test_sync_run_detail_pages_errors_and_reports_exact_error_total(client):
    run_id = 91001
    run = WooCommerceSyncRun(
        id=run_id,
        sync_type="products",
        status="completed_with_errors",
        started_at=FIXED_TIME,
        error_count=3,
    )
    write_rows(
        [run]
        + [
            WooCommerceSyncError(
                sync_run=run,
                remote_product_id=9000 + index,
                sku=f"ERR-{index}",
                error_message=f"Error {index}",
                fingerprint=f"sync-error-{index}",
                created_at=FIXED_TIME,
            )
            for index in range(1, 4)
        ]
    )

    response = client.get(
        f"/api/integrations/woocommerce/sync-runs/{run_id}",
        params={"error_page": 999, "error_page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["errors_total"] == 3
    assert body["errors_page"] == 2
    assert body["errors_page_size"] == 2
    assert body["errors_total_pages"] == 2
    assert body["errors_returned_count"] == 1
    assert body["errors_has_previous"] is True
    assert body["errors_has_next"] is False
    assert body["errors"][0]["sku"] == "ERR-1"
