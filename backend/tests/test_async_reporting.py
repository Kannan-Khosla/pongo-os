import hashlib

from app.db.session import get_db
from app.main import app
from app.services.report_jobs import _process_next_report_job
from app.services.reporting import BUILDERS
from tests.test_items_api import client, seed_item  # noqa: F401


def process_one_job():
    override = app.dependency_overrides[get_db]()
    db = next(override)
    try:
        return _process_next_report_job(db)
    finally:
        override.close()


def test_report_job_enqueues_without_building_deduplicates_and_keeps_latest_run(client, monkeypatch):
    seed_item(client, sku="ASYNC-REPORT", **{"In Stock": 3, "Allocated": 0, "Unit Cost": 2})
    original_builder = BUILDERS["inventory-cost-sku"]
    called = False

    def tracked_builder(db, filters):
        nonlocal called
        called = True
        return original_builder(db, filters)

    monkeypatch.setitem(BUILDERS, "inventory-cost-sku", tracked_builder)
    payload = {"filters": {"category": "Dog Food"}}

    first = client.post("/api/reports/jobs/inventory-cost-sku", json=payload)
    duplicate = client.post(
        "/api/reports/jobs/inventory-cost-sku",
        json={"filters": {"category": " Dog Food "}},
    )

    assert first.status_code == 202
    assert called is False
    assert duplicate.status_code == 202
    assert duplicate.json()["job_id"] == first.json()["job_id"]
    assert duplicate.json()["deduplicated"] is True
    assert first.json()["status"] == "queued"
    assert first.json()["progress"] == 0

    processed = process_one_job()
    status = client.get(f"/api/reports/jobs/{first.json()['job_id']}")

    assert processed.status == "completed"
    assert called is True
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["progress"] == 100
    run_id = status.json()["run_id"]
    completed = client.get(f"/api/reports/runs/{run_id}")
    latest = client.post("/api/reports/jobs/latest/inventory-cost-sku", json=payload)
    csv_export = client.get(f"/api/reports/runs/{run_id}/csv")

    assert completed.status_code == 200
    assert latest.status_code == 200
    assert latest.json()["data_hash"] == completed.json()["data_hash"]
    assert completed.json()["data_hash"] in csv_export.text

    refreshed = client.post("/api/reports/jobs/inventory-cost-sku", json=payload)
    assert refreshed.status_code == 202
    assert refreshed.json()["job_id"] != first.json()["job_id"]
    assert refreshed.json()["previous_run_id"] == run_id


def test_worker_persists_verified_downloads_and_web_never_renders_them(client, monkeypatch):
    seed_item(client, sku="PERSISTED-ARTIFACT", **{"In Stock": 2, "Allocated": 0, "Unit Cost": 3})
    job = client.post("/api/reports/jobs/inventory-cost-sku", json={"filters": {}}).json()

    processed = process_one_job()
    run_id = processed.run_id

    def fail_if_rendered(*args, **kwargs):
        raise AssertionError("download request rendered a report")

    monkeypatch.setattr("app.services.reporting.report_csv_bytes", fail_if_rendered)
    monkeypatch.setattr("app.services.reporting.report_pdf_bytes", fail_if_rendered)
    csv_export = client.get(f"/api/reports/runs/{run_id}/csv")
    pdf_export = client.get(f"/api/reports/runs/{run_id}/pdf")

    assert processed.id == job["job_id"]
    assert csv_export.status_code == 200
    assert pdf_export.status_code == 200
    assert csv_export.headers["x-artifact-sha256"] == hashlib.sha256(csv_export.content).hexdigest()
    assert pdf_export.headers["x-artifact-sha256"] == hashlib.sha256(pdf_export.content).hexdigest()
    assert csv_export.headers["x-report-data-sha256"] in csv_export.text
    assert pdf_export.content.startswith(b"%PDF")


def test_report_job_failure_is_pollable_and_does_not_create_a_run(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.report_jobs.create_report_run_record",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("report builder failed")),
    )
    created = client.post("/api/reports/jobs/inventory-cost-sku", json={"filters": {}})

    process_one_job()
    status = client.get(f"/api/reports/jobs/{created.json()['job_id']}")

    assert status.status_code == 200
    assert status.json()["status"] == "failed"
    assert status.json()["progress"] == 10
    assert status.json()["run_id"] is None
    assert status.json()["error"] == "report builder failed"


def test_report_job_validates_before_enqueue(client):
    assert client.post("/api/reports/jobs/not-a-report", json={"filters": {}}).status_code == 404
    invalid = client.post(
        "/api/reports/jobs/order-summary",
        json={"filters": {"start_date": "2026-08-02", "end_date": "2026-08-01"}},
    )
    assert invalid.status_code == 422


def test_latest_endpoint_finds_runs_created_before_the_async_queue(client):
    synchronous = client.post(
        "/api/reports/runs/inventory-cost-sku",
        json={"filters": {"brand": "Legacy Brand"}},
    )

    latest = client.post(
        "/api/reports/jobs/latest/inventory-cost-sku",
        json={"filters": {"brand": "Legacy Brand"}},
    )

    assert synchronous.status_code == 200
    assert latest.status_code == 200
    assert latest.json()["run_id"] == synchronous.json()["run_id"]
