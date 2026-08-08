import csv
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import get_db
from app.main import app
from app.models.inventory import InventoryItem, InventoryItemLocation
from app.models.orders import Order, OrderItem
from app.models.reporting import GoogleReportsConfiguration, ReportDelivery, ReportRun
from tests.test_fulfillments_api import picked_order
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import seed_location
from tests.test_receiving_api import direct_payload


def database_session():
    override = app.dependency_overrides[get_db]()
    return override, next(override)


def test_report_catalog_contains_requested_reports_and_safe_sharing_status(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.reports.get_settings",
        lambda: SimpleNamespace(
            google_reports_client_id="",
            google_reports_client_secret="",
            google_reports_refresh_token="",
            google_reports_folder_id="",
            smtp_host="",
            smtp_from_email="",
        ),
    )

    response = client.get("/api/reports")

    assert response.status_code == 200
    body = response.json()
    assert len(body["reports"]) == 17
    assert {"inventory-cost-category", "executive-weekly", "sales-by-sku"} <= {
        report["key"] for report in body["reports"]
    }
    assert body["google_sheets_configured"] is False
    assert body["email_configured"] is False


def test_google_sheets_configuration_is_verified_encrypted_and_used_by_reports(client, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        woocommerce_configuration_encryption_key="test-encryption-key-that-is-longer-than-32-bytes",
    )
    verified = []
    monkeypatch.setattr("app.api.routes.reports.get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.api.routes.reports.google_access_token",
        lambda candidate: verified.append(candidate.google_reports_refresh_token) or "access-token",
    )

    response = client.post(
        "/api/reports/google-sheets/configuration",
        json={
            "client_id": "private-client-id",
            "client_secret": "private-client-secret",
            "refresh_token": "private-refresh-token",
            "folder_id": "pongo-reports-folder",
        },
    )

    assert response.status_code == 200, response.text
    assert verified == ["private-refresh-token"]
    assert response.json()["configuration_source"] == "pongo_database"
    assert "private-client" not in response.text
    assert "private-refresh" not in response.text

    override, db = database_session()
    try:
        row = db.get(GoogleReportsConfiguration, 1)
        assert row is not None
        assert "private-client-id" not in row.client_id_ciphertext
        assert "private-client-secret" not in row.client_secret_ciphertext
        assert "private-refresh-token" not in row.refresh_token_ciphertext
        assert row.folder_id == "pongo-reports-folder"
    finally:
        override.close()

    status = client.get("/api/reports/google-sheets/configuration")
    catalog = client.get("/api/reports")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["client_secret_present"] is True
    assert "client_secret" not in status.json()
    assert catalog.json()["google_sheets_configured"] is True


def test_google_oauth_connects_without_exposing_a_refresh_token(client, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        woocommerce_configuration_encryption_key="test-encryption-key-that-is-longer-than-32-bytes",
    )
    exchanged = []
    monkeypatch.setattr("app.api.routes.reports.get_settings", lambda: settings)

    started = client.post(
        "/api/reports/google-sheets/oauth/start",
        json={
            "client_id": "oauth-client-id",
            "client_secret": "oauth-client-secret",
            "folder_id": "pongo-reports-folder",
        },
    )

    assert started.status_code == 200, started.text
    authorization = urlparse(started.json()["authorization_url"])
    query = parse_qs(authorization.query)
    assert authorization.netloc == "accounts.google.com"
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == ["http://testserver/api/reports/google-sheets/oauth/callback"]
    assert set(query["scope"][0].split()) == {
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    }
    assert "oauth-client-secret" not in started.text

    def fake_exchange(candidate, *, code, redirect_uri):
        exchanged.append((candidate.google_reports_client_id, code, redirect_uri))
        return "google-refresh-token"

    monkeypatch.setattr("app.api.routes.reports.exchange_google_oauth_code", fake_exchange)
    callback = client.get(
        "/api/reports/google-sheets/oauth/callback",
        params={"code": "single-use-code", "state": query["state"][0]},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "/#/settings/google-sheets?google=connected"
    assert exchanged == [("oauth-client-id", "single-use-code", "http://testserver/api/reports/google-sheets/oauth/callback")]
    status = client.get("/api/reports/google-sheets/configuration")
    assert status.json()["configured"] is True
    assert status.json()["oauth_redirect_uri"] == "http://testserver/api/reports/google-sheets/oauth/callback"
    assert "google-refresh-token" not in status.text

    override, db = database_session()
    try:
        row = db.get(GoogleReportsConfiguration, 1)
        assert row is not None
        assert "oauth-client-secret" not in row.client_secret_ciphertext
        assert "google-refresh-token" not in row.refresh_token_ciphertext
    finally:
        override.close()


def test_google_oauth_rejects_tampered_state_before_token_exchange(client, monkeypatch):
    settings = Settings(
        _env_file=None,
        app_env="production",
        woocommerce_configuration_encryption_key="test-encryption-key-that-is-longer-than-32-bytes",
    )
    monkeypatch.setattr("app.api.routes.reports.get_settings", lambda: settings)
    started = client.post(
        "/api/reports/google-sheets/oauth/start",
        json={"client_id": "oauth-client-id", "client_secret": "oauth-client-secret"},
    )
    state = parse_qs(urlparse(started.json()["authorization_url"]).query)["state"][0]
    exchanged = []
    monkeypatch.setattr(
        "app.api.routes.reports.exchange_google_oauth_code",
        lambda *args, **kwargs: exchanged.append(True) or "should-not-be-used",
    )

    callback = client.get(
        "/api/reports/google-sheets/oauth/callback",
        params={"code": "single-use-code", "state": f"x{state[1:]}"},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    assert callback.headers["location"] == "/#/settings/google-sheets?google=failed"
    assert exchanged == []


def test_inventory_cost_run_is_frozen_and_all_exports_share_its_hash(client):
    seed_item(
        client,
        sku="LEGAL-COST",
        Description="Legal &amp; <Cost> item",
        Brand="Acana",
        Category="Dog Food",
        **{"In Stock": 5, "Allocated": 1, "Unit Cost": 4},
    )
    seed_item(
        client,
        sku="LEGAL-MISSING-COST",
        Description="Missing cost item",
        Category="Dog Food",
        **{"In Stock": 2, "Allocated": 0, "Unit Cost": None},
    )

    created = client.post(
        "/api/reports/runs/inventory-cost-sku",
        json={"filters": {"category": "Dog Food"}, "generated_by": "test"},
    )

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["row_count"] == 2
    assert len(body["data_hash"]) == 64
    legal_row = next(row for row in body["rows"] if row["sku"] == "LEGAL-COST")
    assert legal_row["inventory_cost"] == "20.00"
    assert legal_row["name"] == "Legal & <Cost> item"
    assert next(row for row in body["rows"] if row["sku"] == "LEGAL-MISSING-COST")["inventory_cost"] is None
    assert {warning["code"] for warning in body["data_quality"]} == {"missing_cost"}

    frozen = client.get(f"/api/reports/runs/{body['run_id']}")
    csv_export = client.get(f"/api/reports/runs/{body['run_id']}/csv")
    pdf_export = client.get(f"/api/reports/runs/{body['run_id']}/pdf")

    assert frozen.status_code == 200
    assert frozen.json()["data_hash"] == body["data_hash"]
    assert csv_export.status_code == 200
    assert body["data_hash"] in csv_export.text
    assert pdf_export.status_code == 200
    assert pdf_export.content.startswith(b"%PDF")


def test_large_report_preview_is_paginated_while_frozen_payload_and_exports_remain_complete(client):
    override, db = database_session()
    try:
        db.add_all(
            [
                InventoryItem(
                    sku=f"PREVIEW-{index:03d}",
                    description=f"Preview item {index:03d}",
                    brand="Preview Pagination",
                    category="Preview Test",
                    unit_cost=Decimal("1.00"),
                    in_stock=Decimal("0"),
                    allocated=Decimal("0"),
                    sellable=Decimal("0"),
                    on_order=Decimal("0"),
                    active=True,
                    non_inventory=False,
                )
                for index in range(1, 126)
            ]
        )
        db.commit()
    finally:
        override.close()

    filters = {"brand": "Preview Pagination"}
    created = client.post(
        "/api/reports/runs/inventory-cost-sku",
        params={"row_page": 1, "row_page_size": 40},
        json={"filters": filters},
    )

    assert created.status_code == 200, created.text
    first = created.json()
    assert first["row_count"] == 125
    assert len(first["rows"]) == 40
    assert first["row_pagination"] == {
        "page": 1,
        "page_size": 40,
        "total": 125,
        "total_pages": 4,
        "returned_count": 40,
        "has_previous": False,
        "has_next": True,
    }

    final_page = client.get(
        f"/api/reports/runs/{first['run_id']}",
        params={"row_page": 4, "row_page_size": 40},
    )
    latest_page = client.post(
        "/api/reports/jobs/latest/inventory-cost-sku",
        params={"row_page": 3, "row_page_size": 50},
        json={"filters": filters},
    )
    oversized = client.get(
        f"/api/reports/runs/{first['run_id']}",
        params={"row_page_size": 101},
    )

    assert final_page.status_code == 200
    assert final_page.json()["data_hash"] == first["data_hash"]
    assert final_page.json()["row_pagination"]["returned_count"] == 5
    assert final_page.json()["rows"][-1]["sku"] == "PREVIEW-125"
    assert latest_page.status_code == 200
    assert latest_page.json()["row_pagination"]["page"] == 3
    assert latest_page.json()["row_pagination"]["returned_count"] == 25
    assert latest_page.json()["rows"][0]["sku"] == "PREVIEW-101"
    assert oversized.status_code == 422

    override, db = database_session()
    try:
        stored = db.get(ReportRun, first["run_id"])
        assert len(stored.payload["rows"]) == 125
        assert stored.csv_artifact is not None
        assert stored.pdf_artifact is not None
    finally:
        override.close()

    csv_export = client.get(f"/api/reports/runs/{first['run_id']}/csv")
    pdf_export = client.get(f"/api/reports/runs/{first['run_id']}/pdf")
    exported_rows = list(csv.DictReader(StringIO(csv_export.content.decode("utf-8-sig"))))
    assert len(exported_rows) == 125
    assert exported_rows[0]["sku"] == "PREVIEW-001"
    assert exported_rows[-1]["sku"] == "PREVIEW-125"
    assert pdf_export.status_code == 200
    assert pdf_export.content.startswith(b"%PDF")


def test_report_integrity_failure_blocks_read_and_exports(client):
    seed_item(client, sku="TAMPER-EVIDENCE", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 2})
    run = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    override, db = database_session()
    try:
        stored = db.get(ReportRun, run["run_id"])
        stored.payload["rows"][0]["inventory_cost"] = "999999.00"
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(stored, "payload")
        db.commit()
    finally:
        override.close()

    assert client.get(f"/api/reports/runs/{run['run_id']}").status_code == 409
    assert client.get(f"/api/reports/runs/{run['run_id']}/csv").status_code == 409
    assert client.get(f"/api/reports/runs/{run['run_id']}/pdf").status_code == 409


def test_report_artifact_tampering_and_legacy_missing_artifacts_fail_closed(client):
    seed_item(client, sku="ARTIFACT-EVIDENCE", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 2})
    tampered = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    missing = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    override, db = database_session()
    try:
        db.get(ReportRun, tampered["run_id"]).csv_artifact = b"tampered"
        legacy = db.get(ReportRun, missing["run_id"])
        legacy.pdf_artifact = None
        legacy.pdf_artifact_hash = None
        db.commit()
    finally:
        override.close()

    assert client.get(f"/api/reports/runs/{tampered['run_id']}/csv").status_code == 409
    missing_export = client.get(f"/api/reports/runs/{missing['run_id']}/pdf")
    assert missing_export.status_code == 409
    assert "Refresh the report" in missing_export.text


def test_identical_report_runs_get_distinct_ids_with_the_same_evidence_hash(client):
    seed_item(client, sku="SAME-RUN", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 2})

    first = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    second = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()

    assert first["run_id"] != second["run_id"]
    assert first["data_hash"] == second["data_hash"]


def test_sales_report_excludes_cancelled_orders_and_joins_current_stock(client):
    item_payload = seed_item(
        client,
        sku="SALES-LEGAL",
        Description="Sales item",
        Brand="Pongo",
        Category="Food",
        **{"In Stock": 8, "Allocated": 2, "Unit Cost": 3},
    )
    override, db = database_session()
    try:
        item = db.get(InventoryItem, item_payload["id"])
        successful = Order(
            order_number="SALE-1",
            local_status="processing",
            placed_on=datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
        )
        cancelled = Order(
            order_number="SALE-2",
            local_status="cancelled",
            placed_on=datetime(2026, 7, 20, 13, tzinfo=timezone.utc),
        )
        db.add_all([successful, cancelled])
        db.flush()
        db.add_all(
            [
                OrderItem(
                    order_id=successful.id,
                    inventory_item_id=item.id,
                    sku=item.sku,
                    quantity_ordered=Decimal("3"),
                    line_total=Decimal("15"),
                ),
                OrderItem(
                    order_id=cancelled.id,
                    inventory_item_id=item.id,
                    sku=item.sku,
                    quantity_ordered=Decimal("9"),
                    line_total=Decimal("45"),
                ),
            ]
        )
        db.commit()
    finally:
        override.close()

    response = client.post(
        "/api/reports/runs/sales-by-sku",
        json={"filters": {"start_date": "2026-07-01", "end_date": "2026-07-31"}},
    )

    assert response.status_code == 200, response.text
    row = response.json()["rows"][0]
    assert row["quantity_sold"] == "3.000"
    assert row["net_sales"] == "15.00"
    assert row["current_in_stock"] == "8.000"
    assert row["current_allocated"] == "2.000"


def test_sales_report_excludes_pending_woo_orders_and_keeps_blank_sku_lines_separate(client):
    override, db = database_session()
    try:
        processing = Order(order_number="BLANK-SALES", woo_status="processing", local_status="processing", placed_on=datetime(2026, 7, 20, tzinfo=timezone.utc))
        pending = Order(order_number="PENDING-SALES", woo_status="pending", local_status="processing", placed_on=datetime(2026, 7, 20, tzinfo=timezone.utc))
        db.add_all([processing, pending])
        db.flush()
        db.add_all([
            OrderItem(order_id=processing.id, sku="", name="Blank A", quantity_ordered=1, line_total=5),
            OrderItem(order_id=processing.id, sku="", name="Blank B", quantity_ordered=2, line_total=8),
            OrderItem(order_id=pending.id, sku="PENDING", name="Pending", quantity_ordered=99, line_total=99),
        ])
        db.commit()
    finally:
        override.close()

    response = client.post("/api/reports/runs/sales-by-sku", json={"filters": {"start_date": "2026-07-01", "end_date": "2026-07-31"}})

    assert response.status_code == 200
    assert {(row["name"], row["quantity_sold"]) for row in response.json()["rows"]} == {("Blank A", "1.000"), ("Blank B", "2.000")}


def test_operational_reports_do_not_treat_historical_snapshots_as_open_demand(client):
    override, db = database_session()
    try:
        snapshot = Order(
            order_number="HISTORICAL-SNAPSHOT",
            woo_status="processing",
            local_status="processing",
            is_historical_snapshot=True,
            placed_on=datetime(2026, 7, 20, tzinfo=timezone.utc),
        )
        db.add(snapshot)
        db.flush()
        db.add(OrderItem(
            order_id=snapshot.id,
            sku="HISTORY-ONLY",
            quantity_ordered=Decimal("5"),
            quantity_allocated=Decimal("2"),
            quantity_picked=Decimal("1"),
        ))
        db.commit()
    finally:
        override.close()

    unallocated = client.post("/api/reports/runs/unallocated-order-items", json={"filters": {}}).json()
    incomplete = client.post("/api/reports/runs/incomplete-orders", json={"filters": {}}).json()
    summary = client.post("/api/reports/runs/order-summary", json={"filters": {}}).json()

    assert unallocated["rows"] == []
    assert incomplete["rows"] == []
    summary_row = next(row for row in summary["rows"] if row["order_number"] == "HISTORICAL-SNAPSHOT")
    assert summary_row["units_unallocated"] == "0.000"


def test_unconfigured_external_report_sharing_fails_closed(client, monkeypatch):
    seed_item(client, sku="NO-SHARE", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 2})
    run = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    settings = SimpleNamespace(
        google_reports_client_id="",
        google_reports_client_secret="",
        google_reports_refresh_token="",
        google_reports_folder_id="",
        smtp_host="",
        smtp_from_email="",
    )
    monkeypatch.setattr("app.api.routes.reports.get_settings", lambda: settings)

    google = client.post(
        f"/api/reports/runs/{run['run_id']}/google-sheets",
        json={"share_with": ["owner@example.com"]},
    )
    email = client.post(
        f"/api/reports/runs/{run['run_id']}/email",
        json={"recipients": ["owner@example.com"], "formats": ["csv"]},
    )

    assert google.status_code == 503
    assert email.status_code == 503


def test_usage_report_reconciles_opening_movements_and_closing_stock(client):
    report_date = datetime.now(ZoneInfo("America/Edmonton")).date().isoformat()
    item_payload = seed_item(client, sku="USAGE-LEGAL", **{"In Stock": 10, "Unit Cost": 2})
    override, db = database_session()
    try:
        item = db.get(InventoryItem, item_payload["id"])
        location = db.scalar(
            select(InventoryItemLocation).where(
                InventoryItemLocation.inventory_item_id == item.id
            )
        )
        assert location.in_stock == Decimal("10")
    finally:
        override.close()

    response = client.post(
        "/api/reports/runs/inventory-usage",
        json={"filters": {"start_date": report_date, "end_date": report_date, "sku": "USAGE-LEGAL"}},
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["closing_stock"] == "10.000"


def test_usage_report_applies_location_scope_to_balances_and_movements(client):
    seed_item(client, sku="SCOPED-USAGE", **{"Inventory Location": "USAGE-A", "Default Location": "USAGE-A", "In Stock": 10, "Allocated": 0})
    seed_location(client, code="USAGE-B", name="USAGE-B")
    receipt = direct_payload(
        idempotency_key="scoped-usage-receipt",
        lines=[{"sku": "SCOPED-USAGE", "inventory_location": "USAGE-B", "quantity_received": 3, "unit_cost": 2}],
    )
    assert client.post("/api/receipts/direct/commit", json=receipt).status_code == 200
    today = datetime.now(ZoneInfo("America/Edmonton")).date().isoformat()

    first = client.post("/api/reports/runs/inventory-usage", json={"filters": {"start_date": today, "end_date": today, "inventory_location": "USAGE-A"}}).json()["rows"][0]
    second = client.post("/api/reports/runs/inventory-usage", json={"filters": {"start_date": today, "end_date": today, "inventory_location": "USAGE-B"}}).json()["rows"][0]

    assert first["closing_stock"] == "10.000"
    assert first["received"] == "0.000"
    assert second["closing_stock"] == "3.000"
    assert second["received"] == "3.000"


def test_locationless_and_zero_cost_items_are_visible_with_quality_warnings(client):
    override, db = database_session()
    try:
        db.add(InventoryItem(sku="LOCATIONLESS-ZERO-COST", in_stock=7, allocated=0, sellable=7, unit_cost=0, active=True, non_inventory=False))
        db.commit()
    finally:
        override.close()

    report = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()

    row = next(row for row in report["rows"] if row["sku"] == "LOCATIONLESS-ZERO-COST")
    assert row["in_stock"] == "0.000"
    assert row["inventory_cost"] is None
    assert {warning["code"] for warning in report["data_quality"]} == {"locationless_inventory", "missing_cost"}


def test_received_and_delivered_reports_keep_transaction_time_cost(client, monkeypatch):
    seed_location(client, code="COST-RCV", name="COST-RCV")
    received_item = seed_item(client, sku="FROZEN-RECEIPT", **{"Inventory Location": "COST-RCV", "Default Location": "COST-RCV", "In Stock": 0, "Allocated": 0, "Unit Cost": 4})
    receipt = client.post(
        "/api/receipts/direct/commit",
        json=direct_payload(idempotency_key="frozen-receipt", lines=[{"sku": "FROZEN-RECEIPT", "inventory_location": "COST-RCV", "quantity_received": 2, "unit_cost": 3}]),
    )
    assert receipt.status_code == 200
    order, _ = picked_order(client, monkeypatch, sku="FROZEN-DELIVERY", barcode="FROZEN-DELIVERY-BAR", woo_id=9901, product_id=9901)
    fulfillment = client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    assert fulfillment.status_code == 200
    delivered_item = client.get("/api/items", params={"sku": "FROZEN-DELIVERY"}).json()["items"][0]
    assert client.patch(f"/api/items/{received_item['id']}", json={"Unit Cost": 99}).status_code == 200
    assert client.patch(f"/api/items/{delivered_item['id']}", json={"Unit Cost": 88}).status_code == 200

    received = client.post("/api/reports/runs/received-inventory", json={"filters": {"sku": "FROZEN-RECEIPT"}}).json()["rows"][0]
    delivered = client.post("/api/reports/runs/delivered-inventory", json={"filters": {"sku": "FROZEN-DELIVERY"}}).json()["rows"][0]

    assert received["unit_cost"] == "3.00"
    assert received["total_cost"] == "6.00"
    assert delivered["unit_cost"] == "4.25"
    assert delivered["delivered_cost"] == "8.50"


def test_email_rejects_google_sheet_link_from_a_different_report_run(client, monkeypatch):
    seed_item(client, sku="SHEET-OWNERSHIP", **{"In Stock": 1, "Allocated": 0, "Unit Cost": 2})
    first = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    second = client.post("/api/reports/runs/inventory-cost-sku", json={"filters": {}}).json()
    sheet_url = "https://docs.google.com/spreadsheets/d/first-run"
    override, db = database_session()
    try:
        db.add(ReportDelivery(report_run_id=first["run_id"], channel="google_sheets", status="created", external_url=sheet_url))
        db.commit()
    finally:
        override.close()
    monkeypatch.setattr(
        "app.api.routes.reports.get_settings",
        lambda: SimpleNamespace(smtp_host="smtp.example.invalid", smtp_from_email="reports@example.invalid"),
    )

    response = client.post(
        f"/api/reports/runs/{second['run_id']}/email",
        json={"recipients": ["owner@example.com"], "formats": [], "google_sheet_url": sheet_url},
    )

    assert response.status_code == 422
    assert "does not belong" in response.text


@pytest.mark.parametrize(
    "report_key",
    [
        "inventory-cost-category",
        "inventory-cost-sku",
        "inventory-in-stock",
        "inventory-usage",
        "unallocated-order-items",
        "delivered-inventory",
        "received-inventory",
        "inventory-export",
        "inventory-forecast",
        "incomplete-orders",
        "order-summary",
        "daily-item-orders",
        "detailed-customer-orders",
        "executive-weekly",
        "reorder-intelligence",
        "po-received",
        "sales-by-sku",
    ],
)
def test_every_catalog_report_generates_from_an_empty_ledger(client, report_key):
    response = client.post(
        f"/api/reports/runs/{report_key}",
        json={"filters": {"start_date": "2026-07-01", "end_date": "2026-07-31"}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["report"]["key"] == report_key
