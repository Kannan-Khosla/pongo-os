from types import SimpleNamespace

from app.services.operations_alerts import send_operations_alert
from tests.test_items_api import client, seed_item  # noqa: F401


def test_readiness_reports_real_database_and_data_blockers(client):
    seed_item(client, sku=" readiness-dup ", Barcode=" dup-bar ", **{"In Stock": 0, "Allocated": 0})
    seed_item(client, sku="READINESS-DUP", Barcode="DUP-BAR", **{"In Stock": 0, "Allocated": 0})

    response = client.get("/ready")

    assert response.status_code == 503
    checks = {check["name"]: check for check in response.json()["checks"]}
    assert checks["database"]["ready"] is True
    assert checks["migrations"]["ready"] is False
    assert "expected 20260803_0030" in checks["migrations"]["message"]
    assert checks["login"]["ready"] is True
    assert checks["duplicate_skus"]["count"] == 1
    assert checks["duplicate_barcodes"]["count"] == 1


def test_operations_alert_posts_structured_payload(monkeypatch):
    captured = {}

    class Response:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    def fake_urlopen(request, timeout):
        captured["body"] = request.data
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.services.operations_alerts.urlopen", fake_urlopen)
    settings = SimpleNamespace(operations_alert_webhook_url="https://alerts.example.invalid/hook")

    assert send_operations_alert(settings, "test_failure", "Something failed", count=3) is True
    assert b'"event": "test_failure"' in captured["body"]
    assert captured["timeout"] == 5
