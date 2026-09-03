from hashlib import sha256
from io import BytesIO
import json

from reportlab.pdfgen import canvas

from app.services.invoice_receiving import parse_invoice_text
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_locations_api import seed_location


def invoice_pdf(*, invoice_number: str = "IN20187152", quantity: int = 1, net_price: float = 38.46) -> bytes:
    buffer = BytesIO()
    document = canvas.Canvas(buffer)
    rows = [
        "Pan Pacific Pet Limited            Invoice                    Date    Page",
        "Aug 27, 2026",
        "Invoice Number",
        invoice_number,
        "Quantity Qty Shipped B/O Item Number UPC Description UOM Sale Net Price Extended Price",
        f"{quantity}.00 649-71444 064992714444 ACANA Cat Bountiful Catch 4.5 kg EA {net_price:.2f} {net_price:.2f} {quantity * net_price:.2f}",
    ]
    y = 760
    for row in rows:
        document.drawString(40, y, row)
        y -= 18
    document.save()
    return buffer.getvalue()


def post_invoice_commit(client, payload: dict, document: bytes):
    return client.post(
        "/api/receipts/invoice/commit",
        data={"payload": json.dumps(payload)},
        files={"file": ("invoice.pdf", document, "application/pdf")},
    )


def test_invoice_parser_keeps_upc_net_price_case_pack_and_zero_shipped_rows():
    parsed = parse_invoice_text(
        """
        Pan Pacific Pet Limited            Invoice                    Date    Page
                                                               Aug 27, 2026 1
                                                                 Invoice Number
                                                                  IN20187152
        Quantity Qty                                          Whole
        Shipped B/O Item Number UPC        Description   UOM  Sale Net Price Extended Price
           1.00 888-13134 888641131341 Zignature Dog LID Kangaroo 12/13 oz CS 59.60 59.60 59.60
           1.00 649-71444 064992714444 ACANA Cat Bountiful Catch 4.5 kg EA 38.46 38.46 38.46
           0.00 527-08073 052742080734 Hill's Science Diet Dog Adult Perfect Weight EA 95.44 95.44 0.00
                                  Chicken 25 lb
           2 123456789012 Generic Product Without UOM 7.25
        """
    )

    assert parsed["supplier"] == "Pan Pacific Pet Limited"
    assert parsed["invoice_number"] == "IN20187152"
    assert parsed["invoice_date"] == "2026-08-27"
    assert [(line["upc"], line["shipped_quantity"], line["net_price"]) for line in parsed["lines"]] == [
        ("888641131341", 1.0, 59.6),
        ("064992714444", 1.0, 38.46),
        ("052742080734", 0.0, 95.44),
        ("123456789012", 2.0, 7.25),
    ]
    assert parsed["lines"][2]["invoice_description"].endswith("Chicken 25 lb")
    assert parsed["lines"][3]["uom_inferred"] is True


def test_invoice_parser_handles_description_first_rows_and_generic_metadata():
    parsed = parse_invoice_text(
        """
        Supplier: Example Pet Supply
        Invoice #: 12345
        Date: 09/01/2026
        Description UPC Qty UOM Unit Price Total
        ACANA Bountiful Catch 4.5 kg 064992714444 2 EA 38.46 76.92
        """
    )

    assert parsed["supplier"] == "Example Pet Supply"
    assert parsed["invoice_number"] == "12345"
    assert parsed["invoice_date"] == "2026-09-01"
    assert parsed["lines"][0] == {
        "line_number": 1,
        "shipped_quantity": 2.0,
        "backordered_quantity": 0.0,
        "supplier_item_number": "",
        "upc": "064992714444",
        "invoice_description": "ACANA Bountiful Catch 4.5 kg",
        "uom": "EA",
        "uom_inferred": False,
        "wholesale_price": 38.46,
        "net_price": 38.46,
        "extended_price": 76.92,
        "extraction_warnings": ["A nonstandard invoice row layout was detected; verify the extracted quantity and price."],
    }


def test_invoice_receiving_adds_to_current_stock_blocks_duplicate_and_reverts(client):
    seed_location(client, code="001", name="Store", isDefault=True)
    item = seed_item(
        client,
        sku="ACANA-71444",
        Barcode="064992714444",
        Description="ACANA Cat Bountiful Catch 4.5 kg",
        **{"Inventory Location": "001", "Default Location": "001", "In Stock": 4, "Allocated": 0, "Unit Cost": 11},
    )
    document = invoice_pdf()
    payload = {
        "idempotency_key": "invoice-receive-1",
        "supplier": "Pan Pacific Pet Limited",
        "invoice_number": "IN20187152",
        "invoice_date": "2026-08-27",
        "document_sha256": sha256(document).hexdigest(),
        "warehouse": "Main Warehouse",
        "sync_woocommerce": False,
        "lines": [
            {
                "source_line_number": 1,
                "item_id": item["id"],
                "upc": "064992714444",
                "invoice_description": "ACANA Cat Bountiful Catch 4.5 kg",
                "uom": "EA",
                "shipped_quantity": 1,
                "pack_multiplier": 1,
                "quantity_pieces": 1,
                "net_price": 38.46,
                "unit_cost": 38.46,
                "inventory_location": "001",
            }
        ],
    }

    unverified_adjustment = post_invoice_commit(client, {**payload, "lines": [{**payload["lines"][0], "unit_cost": 30}]}, document)
    assert unverified_adjustment.status_code == 400

    committed = post_invoice_commit(client, payload, document)
    assert committed.status_code == 200, committed.text
    receipt = committed.json()
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 5
    assert client.get(f"/api/items/{item['id']}").json()["Unit Cost"] == 38.46

    retry = post_invoice_commit(client, payload, document)
    assert retry.status_code == 200
    assert retry.json()["receipt_id"] == receipt["receipt_id"]
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 5

    duplicate = post_invoice_commit(client, {**payload, "idempotency_key": "invoice-receive-2"}, document)
    assert duplicate.status_code == 409

    reversal_preview = client.post(f"/api/receipts/invoice/{receipt['receipt_id']}/reversal/preview", json={})
    assert reversal_preview.status_code == 200
    assert reversal_preview.json()["lines"][0]["stock_after_reversal"] == 4

    reverted = client.post(
        f"/api/receipts/invoice/{receipt['receipt_id']}/reversal/commit",
        json={"idempotency_key": "invoice-reversal-1", "reason": "Invoice was received in error", "sync_woocommerce": False},
    )
    assert reverted.status_code == 200, reverted.text
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 4
    assert client.get(f"/api/items/{item['id']}").json()["Unit Cost"] == 11
    assert reverted.json()["restored_unit_costs"] == 1
    assert client.post(f"/api/receipts/invoice/{receipt['receipt_id']}/reversal/preview", json={}).status_code == 409


def test_invoice_commit_rejects_a_pdf_that_does_not_match_the_reviewed_document(client):
    seed_location(client, code="001", name="Store", isDefault=True)
    item = seed_item(client, sku="PDF-BOUNDARY", Barcode="064992714444", Description="ACANA Cat Bountiful Catch 4.5 kg", **{"Inventory Location": "001", "In Stock": 4, "Unit Cost": 11})
    reviewed = invoice_pdf()
    payload = {
        "idempotency_key": "invoice-pdf-boundary",
        "supplier": "Pan Pacific Pet Limited",
        "invoice_number": "IN20187152",
        "invoice_date": "2026-08-27",
        "document_sha256": sha256(reviewed).hexdigest(),
        "warehouse": "Main Warehouse",
        "sync_woocommerce": False,
        "lines": [{"source_line_number": 1, "item_id": item["id"], "upc": "064992714444", "invoice_description": "ACANA Cat Bountiful Catch 4.5 kg", "uom": "EA", "shipped_quantity": 1, "pack_multiplier": 1, "quantity_pieces": 1, "net_price": 38.46, "unit_cost": 38.46, "inventory_location": "001"}],
    }

    response = post_invoice_commit(client, payload, invoice_pdf(invoice_number="IN99999999"))

    assert response.status_code == 409
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 4


def test_invoice_reversal_retry_repairs_a_failed_woocommerce_queue_without_removing_stock_twice(client, monkeypatch):
    seed_location(client, code="001", name="Store", isDefault=True)
    item = seed_item(client, sku="REV-RETRY", Barcode="064992714444", Description="ACANA Cat Bountiful Catch 4.5 kg", **{"Inventory Location": "001", "In Stock": 0, "Allocated": 0, "Unit Cost": 11})
    document = invoice_pdf()
    payload = {
        "idempotency_key": "invoice-reversal-retry-receive",
        "supplier": "Pan Pacific Pet Limited",
        "invoice_number": "IN20187152",
        "invoice_date": "2026-08-27",
        "document_sha256": sha256(document).hexdigest(),
        "warehouse": "Main Warehouse",
        "sync_woocommerce": False,
        "lines": [{"source_line_number": 1, "item_id": item["id"], "upc": "064992714444", "invoice_description": "ACANA Cat Bountiful Catch 4.5 kg", "uom": "EA", "shipped_quantity": 1, "pack_multiplier": 1, "quantity_pieces": 1, "net_price": 38.46, "unit_cost": 38.46, "inventory_location": "001"}],
    }
    receipt = post_invoice_commit(client, payload, document).json()
    attempts = 0

    def queue_once_recovered(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("queue unavailable")
        return {"id": 99, "status": "queued"}

    monkeypatch.setattr("app.services.invoice_receiving._queue_stock_sync", queue_once_recovered)
    reversal = {"idempotency_key": "invoice-reversal-retry", "reason": "Receipt was posted in error", "sync_woocommerce": True}

    first = client.post(f"/api/receipts/invoice/{receipt['receipt_id']}/reversal/commit", json=reversal)
    retry = client.post(f"/api/receipts/invoice/{receipt['receipt_id']}/reversal/commit", json=reversal)

    assert first.status_code == retry.status_code == 200
    assert "queue unavailable" in first.json()["warnings"][0]
    assert retry.json()["woocommerce_sync"] == {"id": 99, "status": "queued"}
    assert attempts == 2
    assert client.get(f"/api/items/{item['id']}").json()["In Stock"] == 0
