import csv
from io import BytesIO, StringIO
import socket

import pdfplumber
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.auth import User
from tests.test_items_api import client  # noqa: F401


def draft_payload():
    return {
        "po_number": "SB-20260909-PACIFIC",
        "supplier_id": "pacific",
        "as_of": "2026-09-09",
        "expected_delivery": "2026-09-13",
        "lines": [{
            "product_id": "acana-pacifica", "cases": 2, "units": 4,
            "unit_cost": 69.5, "discount": 0.12, "effective_cost": 61.16,
            "line_total": 244.64, "retail_value": 419.96,
        }],
        "freight": 95,
        "tax": 16.98,
    }


def test_smart_buying_demo_and_exports_are_authenticated_local_drafts(client, monkeypatch):
    def forbid_connection(*_args, **_kwargs):
        raise AssertionError("Smart Buying must not make external connections")

    monkeypatch.setattr(socket.socket, "connect", forbid_connection)
    writes = []

    def record_write(_conn, _cursor, statement, _params, _context, _executemany):
        if statement.lstrip().split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"}:
            writes.append(statement)

    event.listen(client.test_engine, "before_cursor_execute", record_write)
    try:
        demo = client.get("/api/smart-buying/demo")
        assert demo.status_code == 200
        assert demo.json()["mode"] == "demo"
        assert len(demo.json()["products"]) == 20

        response = client.post("/api/smart-buying/export/csv", json=draft_payload())
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("text/csv")
        assert 'attachment; filename="pongo-SB-20260909-PACIFIC.csv"' == response.headers["content-disposition"]
        rows = list(csv.reader(StringIO(response.text)))
        totals = {row[0]: row[8] for row in rows[1:]}
        assert totals["Final purchase cost"] == "356.62"
        assert totals["Discounts / potential supplier savings"] == "33.36"
        assert totals["Projected gross profit after freight, before GST"] == "80.32"
        assert "not sent to supplier" in response.text
        assert "471421" in response.text

        pdf = client.post("/api/smart-buying/export/pdf", json=draft_payload())
        assert pdf.status_code == 200, pdf.text
        assert pdf.content.startswith(b"%PDF")
        assert pdf.headers["content-type"] == "application/pdf"
        with pdfplumber.open(BytesIO(pdf.content)) as document:
            text = "\n".join(page.extract_text() for page in document.pages)
        assert "356.62" in text and "Local draft - not sent" in text
        assert not writes
    finally:
        event.remove(client.test_engine, "before_cursor_execute", record_write)

    client.post("/api/auth/logout")
    assert client.get("/api/smart-buying/demo").status_code == 401
    assert client.post("/api/smart-buying/export/csv", json=draft_payload()).status_code == 401


def test_demo_account_can_export_but_cannot_transmit_purchase_orders(client):
    with Session(client.test_engine) as db:
        db.scalar(select(User).where(User.email == "pytest@example.com")).access_level = "demo"
        db.commit()

    assert client.get("/api/smart-buying/demo").status_code == 200
    for format in ("csv", "pdf"):
        response = client.post(f"/api/smart-buying/export/{format}", json=draft_payload())
        assert response.status_code == 200, response.text
    assert client.post("/api/items", json={"SKU": "NO-DEMO-WRITE"}).status_code == 403
    assert client.post("/api/smart-buying/send", json=draft_payload()).status_code in {404, 405}


@pytest.mark.parametrize("field,value", [
    ("cases", 3), ("cases", 0), ("cases", True), ("units", 3), ("unit_cost", 1),
    ("discount", 0.2), ("discount", "NaN"), ("effective_cost", 0),
    ("line_total", 244.63), ("retail_value", 10), ("product_id", "unknown"),
])
def test_smart_buying_rejects_unverified_line_math(client, field, value):
    payload = draft_payload()
    payload["lines"][0][field] = value
    assert client.post("/api/smart-buying/export/csv", json=payload).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("supplier_id", "royal"), ("freight", 0), ("tax", 0), ("po_number", "=CMD()"),
    ("as_of", "2026-09-15"), ("expected_delivery", "2026-09-01"), ("lines", []),
])
def test_smart_buying_rejects_invalid_drafts(client, field, value):
    payload = draft_payload()
    payload[field] = value
    assert client.post("/api/smart-buying/export/pdf", json=payload).status_code == 422


def test_smart_buying_rejects_duplicate_lines_and_unsupported_formats(client):
    payload = draft_payload()
    payload["lines"].append(dict(payload["lines"][0]))
    assert client.post("/api/smart-buying/export/csv", json=payload).status_code == 422
    assert client.post("/api/smart-buying/export/html", json=draft_payload()).status_code == 422
