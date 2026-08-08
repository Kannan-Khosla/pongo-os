from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.db.session import get_db
from app.main import app
from app.models.allocations import Allocation
from app.models.fulfillments import Fulfillment
from app.models.orders import Order, OrderItem
from app.models.picks import Pick
from app.models.receipts import Receipt
from tests.test_items_api import client, seed_item  # noqa: F401


def seed_paginated_operational_history(client) -> None:
    items = [seed_item(client, sku=f"PAGE-ITEM-{index}", Brand="Paged Brand") for index in range(3)]
    dependency = app.dependency_overrides[get_db]()
    db = next(dependency)
    try:
        base_time = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        for index in range(len(items)):
            created_at = base_time + timedelta(minutes=index)
            db.add(
                Receipt(
                    receipt_number=f"PAGE-RECEIPT-{index}",
                    receipt_type="direct",
                    status="posted",
                    warehouse="Main Warehouse",
                    received_date=created_at.date(),
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            db.add(
                Allocation(
                    allocation_number=f"PAGE-ALLOCATION-{index}",
                    status="posted",
                    allocation_type="single_order",
                    created_by="pagination-test",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            db.add(
                Pick(
                    pick_number=f"PAGE-PICK-{index}",
                    status="posted",
                    pick_type="single_order",
                    created_by="pagination-test",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            db.add(
                Fulfillment(
                    fulfillment_number=f"PAGE-FULFILLMENT-{index}",
                    status="posted",
                    fulfillment_type="single_order",
                    created_by="pagination-test",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
            db.add(
                Order(
                    woo_order_id=97000 + index,
                    woo_order_number=f"PAGE-ORDER-{index}",
                    woo_status="completed",
                    local_status="completed",
                    completion_status="completed",
                    customer_name="Percent % Customer" if index == 0 else f"Customer {index}",
                    customer_email=f"customer-{index}@example.invalid",
                    date_created=created_at,
                    date_modified=created_at,
                    completed_at=created_at,
                    closed_at=created_at,
                    is_historical_snapshot=False,
                    historical_source_present=True,
                    items=[
                        OrderItem(
                            line_number=1,
                            sku=f"PAGE-SKU-{index}",
                            barcode=f"PAGE-BAR-{index}",
                            name=f"Paged product {index}",
                            quantity_ordered=Decimal("1"),
                            quantity_allocated=Decimal("1"),
                            quantity_picked=Decimal("1"),
                            quantity_fulfilled=Decimal("1"),
                            quantity_stock_reduced=Decimal("1"),
                        )
                    ],
                )
            )
        db.commit()
    finally:
        dependency.close()


@pytest.mark.parametrize(
    ("path", "collection_key"),
    [
        ("/api/receipts", "receipts"),
        ("/api/stock-movements", "movements"),
        ("/api/orders/completed", "orders"),
        ("/api/allocations", "allocations"),
        ("/api/picks", "picks"),
        ("/api/fulfillments", "fulfillments"),
        ("/api/inventory/locations", "rows"),
    ],
)
def test_operational_list_endpoints_return_exact_pagination_metadata(client, path, collection_key):
    seed_paginated_operational_history(client)

    response = client.get(path, params={"page": 2, "page_size": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["page"] == 2
    assert body["page_size"] == 1
    assert body["total_pages"] == 3
    assert body["returned_count"] == 1
    assert body["has_previous"] is True
    assert body["has_next"] is True
    assert len(body[collection_key]) == 1


def test_inventory_location_rows_include_product_owned_display_fields(client):
    seed_paginated_operational_history(client)

    response = client.get(
        "/api/inventory/locations",
        params={"sku": "PAGE-ITEM-1", "page": 1, "page_size": 1},
    )

    assert response.status_code == 200, response.text
    row = response.json()["rows"][0]
    assert row["brand"] == "Paged Brand"
    assert row["category"] == "Dog Food"
    assert row["unit_cost"] == 4.25
    assert row["item_active"] is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/receipts",
        "/api/stock-movements",
        "/api/orders/completed",
        "/api/orders/history",
        "/api/allocations",
        "/api/picks",
        "/api/fulfillments",
        "/api/inventory/locations",
    ],
)
def test_operational_list_endpoints_reject_unbounded_page_sizes(client, path):
    assert client.get(path, params={"page_size": 101}).status_code == 422


def test_completed_order_filters_are_applied_before_counting_and_csv_remains_unbounded(client):
    seed_paginated_operational_history(client)

    literal_percent = client.get("/api/orders/completed", params={"search": "%", "page_size": 1}).json()
    sku_match = client.get("/api/orders/completed", params={"sku": "page-sku-1", "page_size": 1}).json()
    csv_export = client.get("/api/orders/completed/export")

    assert literal_percent["total"] == 1
    assert literal_percent["returned_count"] == 1
    assert sku_match["total"] == 1
    assert sku_match["orders"][0]["woo_order_number"] == "PAGE-ORDER-1"
    assert csv_export.status_code == 200
    assert len(csv_export.text.splitlines()) == 4


def test_combined_order_history_bounds_each_section_and_reports_exact_totals(client):
    seed_paginated_operational_history(client)

    response = client.get("/api/orders/history", params={"page": 2, "page_size": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 9
    assert body["page"] == 2
    assert body["page_size"] == 1
    assert body["total_pages"] == 3
    assert body["returned_count"] == 3
    assert body["has_previous"] is True
    assert body["has_next"] is True
    for section in ("allocations", "picks", "fulfillments"):
        assert len(body[section]) == 1
        assert body["pagination"][section] == {
            "total": 3,
            "page": 2,
            "page_size": 1,
            "total_pages": 3,
            "returned_count": 1,
            "has_previous": True,
            "has_next": True,
        }

    exhausted = client.get("/api/orders/history", params={"page": 4, "page_size": 1}).json()
    assert exhausted["total"] == 9
    assert exhausted["returned_count"] == 0
    assert exhausted["has_previous"] is True
    assert exhausted["has_next"] is False
    assert all(exhausted[section] == [] for section in ("allocations", "picks", "fulfillments"))
