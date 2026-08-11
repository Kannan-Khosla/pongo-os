import csv
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from app.models.orders import Order
from app.models.routes import Route, RouteStop
from tests.test_fulfillments_api import picked_order
from tests.test_items_api import client, seed_item  # noqa: F401
from tests.test_woocommerce_order_sync_api import patch_woo_order_client, woo_order


def seed_open_delivery_order(client, index: int, *, postal_code: str | None = None, address: bool = True, local_status: str = "open") -> int:
    with Session(client.test_engine) as db:
        order = Order(
            woo_order_id=20_000 + index,
            woo_order_number=f"DEL-{index:03d}",
            woo_status="processing",
            local_status=local_status,
            completion_status="open" if local_status == "open" else local_status,
            is_historical_snapshot=False,
            customer_name=f"Delivery Customer {index}",
            customer_phone=f"780-555-{index:04d}",
            shipping_address_1=f"{100 + index} Delivery Street" if address else None,
            shipping_city="Edmonton" if address else None,
            shipping_state="AB" if address else None,
            shipping_country="CA" if address else None,
            shipping_zip=(postal_code or f"T5{index % 5} 0A{index % 10}") if address else None,
            date_created=datetime(2026, 8, 8, 12, index % 60, tzinfo=timezone.utc),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order.id


def fulfilled_route_order(client, monkeypatch, sku="ROUTE-SKU", barcode="ROUTE-BAR", woo_id=901, product_id=501, partial=False):
    order, line = picked_order(client, monkeypatch, item_stock=8, item_allocated=1, quantity=2, sku=sku, barcode=barcode, woo_id=woo_id, product_id=product_id)
    if partial:
        commit = client.post("/api/fulfillments/commit", json={"lines": [{"order_line_id": line["id"], "quantity_to_fulfill": 1}], "allow_partial": True})
    else:
        commit = client.post("/api/fulfillments/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    assert commit.status_code == 200, commit.text
    assert commit.json()["status"] == "posted"
    detail = client.get(f"/api/orders/{order['id']}").json()
    return detail


def synced_unfulfilled_order(client, monkeypatch, status_step="open"):
    woo_id, product_id = {
        "open": (977, 777),
        "allocated": (978, 778),
        "picked": (979, 779),
    }[status_step]
    sku = f"{status_step.upper()}-ROUTE-SKU"
    barcode = f"{status_step.upper()}-ROUTE-BAR"
    seed_item(client, sku=sku, Barcode=barcode, wooProductId=product_id, **{"In Stock": 8, "Allocated": 0})
    patch_woo_order_client(monkeypatch, [woo_order(id=woo_id, number=str(woo_id), line_items=[{**woo_order()["line_items"][0], "id": 1000 + woo_id, "product_id": product_id, "sku": sku, "meta_data": [{"key": "barcode", "value": barcode}]}])])
    client.post("/api/integrations/woocommerce/orders/commit", json={})
    order = [row for row in client.get("/api/orders/open").json()["orders"] if row["woo_order_id"] == woo_id][0]
    if status_step == "allocated":
        client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True})
    if status_step == "picked":
        client.post("/api/allocations/commit", json={"order_ids": [order["id"]], "allow_partial": True})
        client.post("/api/picks/commit", json={"idempotency_key": f"route-pick-{order['id']}", "order_ids": [order["id"]], "allow_partial": True})
    return client.get(f"/api/orders/{order['id']}").json()


def route_payload(order_ids):
    return {
        "route_date": "2026-07-07",
        "route_name": "Morning Route",
        "driver_name": "Driver 1",
        "vehicle_name": "Van 1",
        "order_ids": order_ids,
        "created_by": "pytest",
        "notes": "Manual route",
    }


def test_open_order_route_planner_balances_selected_orders_by_estimated_time(client):
    order_ids = [
        seed_open_delivery_order(client, index, postal_code=postal_code)
        for index, postal_code in enumerate(
            ["T5A 0A1", "T5A 0A2", "T5A 0A3", "T5B 0B1", "T5B 0B2", "T5B 0B3", "T6C 0C1", "T6C 0C2", "T6C 0C3"],
            start=1,
        )
    ]
    excluded_id = seed_open_delivery_order(client, 20, address=False)
    seed_open_delivery_order(client, 21, local_status="completed")

    response = client.post(
        "/api/routes/open-orders/plan",
        json={"start_address": "5855 99 Street NW, Edmonton, AB", "driver_count": 3},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_open_orders"] == 10
    assert body["available_order_count"] == 9
    assert body["selected_order_count"] == 9
    assert body["routable_order_count"] == 9
    assert body["excluded_order_count"] == 1
    assert body["effective_driver_count"] == 3
    assert [driver["stop_count"] for driver in body["drivers"]] == [3, 3, 3]
    assert {stop["order_id"] for driver in body["drivers"] for stop in driver["stops"]} == set(order_ids)
    assert body["excluded_orders"][0]["order_id"] == excluded_id
    assert body["assignment_method"] == "equal_time"
    assert len({driver["estimated_duration_minutes"] for driver in body["drivers"]}) == 1
    assert {order["order_id"] for order in body["available_orders"]} == set(order_ids)
    first_link = body["drivers"][0]["google_maps_links"][0]
    query = parse_qs(urlparse(first_link["url"]).query)
    assert query["api"] == ["1"]
    assert query["origin"] == ["5855 99 Street NW, Edmonton, AB"]
    assert query["travelmode"] == ["driving"]
    assert client.get("/api/routes").json()["total"] == 0


def test_open_order_route_planner_only_routes_selected_orders(client):
    order_ids = [seed_open_delivery_order(client, index) for index in range(1, 5)]

    response = client.post(
        "/api/routes/open-orders/plan",
        json={"driver_count": 2, "order_ids": order_ids[:2]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available_order_count"] == 4
    assert body["selected_order_count"] == 2
    assert {stop["order_id"] for driver in body["drivers"] for stop in driver["stops"]} == set(order_ids[:2])


def test_open_order_route_planner_assigns_direction_zones_to_requested_drivers(client):
    north = seed_open_delivery_order(client, 1, postal_code="T5Z 1A1")
    south = seed_open_delivery_order(client, 2, postal_code="T6X 1A1")
    east = seed_open_delivery_order(client, 3, postal_code="T6B 1A1")
    west = seed_open_delivery_order(client, 4, postal_code="T5P 1A1")
    central_east = seed_open_delivery_order(client, 5, postal_code="T5J 1A1")

    response = client.post(
        "/api/routes/open-orders/plan",
        json={
            "driver_count": 2,
            "assignment_method": "directions",
            "direction_assignments": [
                {"driver_number": 1, "directions": ["N", "E"]},
                {"driver_number": 2, "directions": ["S", "W", "Central East"]},
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assignment_method"] == "directions"
    assert {stop["order_id"] for stop in body["drivers"][0]["stops"]} == {north, east}
    assert {stop["order_id"] for stop in body["drivers"][1]["stops"]} == {south, west, central_east}
    assert body["drivers"][0]["directions"] == ["N", "E"]
    assert body["drivers"][1]["directions"] == ["S", "W", "Central East"]


def test_open_order_route_planner_exposes_exact_ten_zone_partition(client):
    expected_zones = ["N", "S", "E", "W", "NE", "NW", "SE", "SW", "Central East", "Central West"]
    postal_codes = ["T5Z 1A1", "T6X 1A1", "T6B 1A1", "T5P 1A1", "T5A 1A1", "T5X 1A1", "T6K 1A1", "T6W 1A1", "T5J 1A1", "T5K 1A1"]
    expected_by_order = {
        seed_open_delivery_order(client, index, postal_code=postal_code): zone
        for index, (zone, postal_code) in enumerate(zip(expected_zones, postal_codes, strict=True), start=1)
    }

    response = client.post("/api/routes/open-orders/plan", json={"driver_count": 1})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["zones"] == expected_zones
    assert {candidate["order_id"]: candidate["direction"] for candidate in body["available_orders"]} == expected_by_order


def test_direction_assignment_never_auto_adds_an_unassigned_zone(client):
    east = seed_open_delivery_order(client, 1, postal_code="T6B 1A1")
    west = seed_open_delivery_order(client, 2, postal_code="T5P 1A1")

    response = client.post(
        "/api/routes/open-orders/plan",
        json={
            "driver_count": 1,
            "order_ids": [east, west],
            "assignment_method": "directions",
            "direction_assignments": [{"driver_number": 1, "directions": ["E"]}],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["drivers"][0]["directions"] == ["E"]
    assert [stop["order_id"] for stop in body["drivers"][0]["stops"]] == [east]
    assert body["selected_order_count"] == 2
    assert body["routable_order_count"] == 2
    assert body["assigned_order_count"] == 1
    assert body["unassigned_order_count"] == 1
    assert body["unassigned_orders"] == [
        {
            "order_id": west,
            "woo_order_number": "DEL-002",
            "customer_name": "Delivery Customer 2",
            "address": "102 Delivery Street, Edmonton, AB, T5P 1A1, CA",
            "postal_area": "T5P",
            "direction": "W",
            "reason_code": "zone_not_assigned",
            "reason": "Zone W was not assigned to a driver.",
        }
    ]
    assert body["selected_order_count"] == body["assigned_order_count"] + body["unassigned_order_count"]


def test_overlapping_zone_assignments_assign_each_order_exactly_once(client):
    order_ids = [seed_open_delivery_order(client, index, postal_code=f"T6B 1A{index}") for index in range(1, 5)]

    response = client.post(
        "/api/routes/open-orders/plan",
        json={
            "driver_count": 2,
            "order_ids": order_ids,
            "assignment_method": "directions",
            "direction_assignments": [
                {"driver_number": 1, "directions": ["E"]},
                {"driver_number": 2, "directions": ["E"]},
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assigned_ids = [stop["order_id"] for driver in body["drivers"] for stop in driver["stops"]]
    assert len(assigned_ids) == len(set(assigned_ids)) == len(order_ids)
    assert set(assigned_ids) == set(order_ids)
    assert body["assigned_order_count"] == len(order_ids)
    assert body["unassigned_orders"] == []


def test_selected_orders_are_assigned_once_or_explicitly_reported(client):
    valid = seed_open_delivery_order(client, 1, postal_code="T6B 1A1")
    incomplete = seed_open_delivery_order(client, 2, address=False)
    missing = 999_999

    response = client.post(
        "/api/routes/open-orders/plan",
        json={"driver_count": 1, "order_ids": [valid, incomplete, missing]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_order_count"] == 3
    assert body["assigned_order_count"] == 1
    assert body["unassigned_order_count"] == 2
    assert {row["order_id"]: row["reason_code"] for row in body["unassigned_orders"]} == {
        incomplete: "incomplete_address",
        missing: "not_open_or_missing",
    }
    assert body["selected_order_count"] == body["assigned_order_count"] + body["unassigned_order_count"]


def test_open_order_plan_exposes_secret_free_map_and_time_data(client):
    geocoded_order_id = seed_open_delivery_order(client, 1, postal_code="T6B 1A1")
    seed_open_delivery_order(client, 2, postal_code="T5P 1A1")
    with Session(client.test_engine) as db:
        route = Route(route_number="RT-HISTORIC", status="cancelled", total_stops=1)
        db.add(route)
        db.flush()
        db.add(
            RouteStop(
                route_id=route.id,
                order_id=geocoded_order_id,
                stop_sequence=1,
                address_1="101 Delivery Street",
                city="Edmonton",
                state="AB",
                zip="T6B 1A1",
                country="CA",
                latitude=Decimal("53.5000000"),
                longitude=Decimal("-113.5000000"),
            )
        )
        db.commit()

    response = client.post("/api/routes/open-orders/plan", json={"driver_count": 2})

    assert response.status_code == 200, response.text
    body = response.json()
    durations = [driver["estimated_duration_minutes"] for driver in body["drivers"]]
    assert body["total_estimated_duration_minutes"] == sum(durations)
    assert body["estimated_completion_minutes"] == max(durations)
    assert body["map"]["coordinate_count"] == 1
    assert body["map"]["missing_coordinate_count"] == 1
    assert set(body["map"]) == {"provider", "configured", "coordinate_count", "missing_coordinate_count"}
    assert not ({"api_key", "key", "token", "secret"} & set(body["map"]))
    geocoded_stop = next(
        stop for driver in body["drivers"] for stop in driver["stops"] if stop["order_id"] == geocoded_order_id
    )
    assert geocoded_stop["latitude"] == 53.5
    assert geocoded_stop["longitude"] == -113.5
    assert geocoded_stop["coordinate_source"] == "existing_route_stop"


def test_open_order_route_planner_segments_long_runs_for_mobile_google_maps(client):
    for index in range(1, 10):
        seed_open_delivery_order(client, index)

    response = client.post(
        "/api/routes/open-orders/plan",
        json={"start_address": "5855 99 Street", "driver_count": 1, "return_to_start": True},
    )

    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    delivery_links = [link for link in driver["google_maps_links"] if not link["returns_to_start"]]
    return_links = [link for link in driver["google_maps_links"] if link["returns_to_start"]]
    assert [link["stop_count"] for link in delivery_links] == [4, 4, 1]
    assert len(return_links) == 1
    assert parse_qs(urlparse(return_links[0]["url"]).query)["destination"] == ["5855 99 Street"]
    for link in delivery_links:
        waypoints = parse_qs(urlparse(link["url"]).query).get("waypoints", [""])[0].split("|")
        assert len([waypoint for waypoint in waypoints if waypoint]) <= 3


def test_open_order_route_planner_validates_driver_count_and_handles_no_orders(client):
    empty = client.post("/api/routes/open-orders/plan", json={"driver_count": 1})
    too_few = client.post("/api/routes/open-orders/plan", json={"driver_count": 0})
    too_many = client.post("/api/routes/open-orders/plan", json={"driver_count": 51})
    invalid_assignment = client.post(
        "/api/routes/open-orders/plan",
        json={
            "driver_count": 1,
            "assignment_method": "directions",
            "direction_assignments": [{"driver_number": 2, "directions": ["N"]}],
        },
    )

    assert empty.status_code == 200
    assert empty.json()["drivers"] == []
    assert empty.json()["effective_driver_count"] == 0
    assert too_few.status_code == 422
    assert too_many.status_code == 422
    assert invalid_assignment.status_code == 422


def test_route_candidates_include_fulfilled_and_partial_with_warning(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    partial = fulfilled_route_order(client, monkeypatch, sku="PARTIAL-ROUTE-SKU", barcode="PARTIAL-ROUTE-BAR", woo_id=902, product_id=502, partial=True)

    response = client.get("/api/routes/candidates")

    assert response.status_code == 200
    candidates = response.json()["candidates"]
    ids = {row["order_id"] for row in candidates}
    assert fulfilled["id"] in ids
    assert partial["id"] in ids
    partial_row = [row for row in candidates if row["order_id"] == partial["id"]][0]
    assert partial_row["route_warning"] == "Order is partially fulfilled."


def test_route_candidates_filter_and_page_in_postgres_order(client, monkeypatch):
    first = fulfilled_route_order(client, monkeypatch, sku="ROUTE-PAGE-1", barcode="ROUTE-PAGE-BAR-1", woo_id=911, product_id=511)
    second = fulfilled_route_order(client, monkeypatch, sku="ROUTE-PAGE-2", barcode="ROUTE-PAGE-BAR-2", woo_id=912, product_id=512)
    outside_date = fulfilled_route_order(client, monkeypatch, sku="ROUTE-PAGE-3", barcode="ROUTE-PAGE-BAR-3", woo_id=913, product_id=513)
    with Session(client.test_engine) as db:
        db.get(Order, first["id"]).date_created = datetime(2026, 7, 7, 10, tzinfo=timezone.utc)
        db.get(Order, second["id"]).date_created = datetime(2026, 7, 7, 11, tzinfo=timezone.utc)
        db.get(Order, outside_date["id"]).date_created = datetime(2026, 7, 8, 9, tzinfo=timezone.utc)
        db.commit()

    first_page = client.get("/api/routes/candidates", params={"route_date": "2026-07-07", "page": 1, "page_size": 1})
    second_page = client.get("/api/routes/candidates", params={"route_date": "2026-07-07", "page": 2, "page_size": 1})
    beyond_last_page = client.get("/api/routes/candidates", params={"route_date": "2026-07-07", "page": 99, "page_size": 1})

    assert first_page.status_code == second_page.status_code == beyond_last_page.status_code == 200
    first_body = first_page.json()
    assert first_body["total_candidates"] == 2
    assert first_body["page"] == 1
    assert first_body["page_size"] == 1
    assert first_body["total_pages"] == 2
    assert first_body["returned_count"] == 1
    assert first_body["has_previous"] is False
    assert first_body["has_next"] is True
    assert first_body["candidates"][0]["order_id"] == first["id"]
    assert second_page.json()["candidates"][0]["order_id"] == second["id"]
    assert beyond_last_page.json()["page"] == 2
    assert beyond_last_page.json()["candidates"][0]["order_id"] == second["id"]
    assert client.get("/api/routes/candidates", params={"page_size": 101}).status_code == 422


def test_route_candidates_exclude_ineligible_and_active_routed_orders(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    open_order = synced_unfulfilled_order(client, monkeypatch, "open")
    allocated_order = synced_unfulfilled_order(client, monkeypatch, "allocated")
    picked_order_detail = synced_unfulfilled_order(client, monkeypatch, "picked")
    commit = client.post("/api/routes/commit", json=route_payload([fulfilled["id"]]))
    assert commit.json()["status"] == "draft"

    candidates = client.get("/api/routes/candidates").json()["candidates"]
    ids = {row["order_id"] for row in candidates}

    assert fulfilled["id"] not in ids
    assert open_order["id"] not in ids
    assert allocated_order["id"] not in ids
    assert picked_order_detail["id"] not in ids

    client.post(f"/api/routes/{commit.json()['route_id']}/cancel")
    candidates_after_cancel = client.get("/api/routes/candidates").json()["candidates"]
    assert fulfilled["id"] in {row["order_id"] for row in candidates_after_cancel}


def test_completed_picked_order_is_route_candidate(client, monkeypatch):
    picked = synced_unfulfilled_order(client, monkeypatch, "picked")
    completed = client.post(f"/api/orders/{picked['id']}/complete/commit", json={"completion_mode": "complete_picked", "queue_woo_status_update": False})

    assert completed.status_code == 200, completed.text
    candidate = next(row for row in client.get("/api/routes/candidates").json()["candidates"] if row["order_id"] == picked["id"])
    assert candidate["local_status"] == "completed"
    assert candidate["fulfilled_line_count"] == 1


def test_route_preview_validates_without_writing_or_inventory_changes(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    before_item = client.get("/api/items", params={"sku": "ROUTE-SKU"}).json()["items"][0]

    response = client.post("/api/routes/preview", json=route_payload([fulfilled["id"], 999999]))

    assert response.status_code == 200
    body = response.json()
    assert body["total_orders"] == 2
    assert body["valid_orders"] == 1
    assert body["invalid_orders"] == 1
    assert body["preview_route"]["stops"][0]["stop_sequence"] == 1
    assert body["preview_route"]["stops"][0]["status"] == "valid"
    assert body["preview_route"]["stops"][1]["status"] == "invalid"
    assert client.get("/api/routes").json()["total"] == 0
    after_item = client.get("/api/items", params={"sku": "ROUTE-SKU"}).json()["items"][0]
    assert after_item["In Stock"] == before_item["In Stock"]
    assert after_item["Allocated"] == before_item["Allocated"]


def test_route_commit_creates_route_stops_and_rejects_invalid_atomically(client, monkeypatch):
    first = fulfilled_route_order(client, monkeypatch)
    second = fulfilled_route_order(client, monkeypatch, sku="ROUTE-SKU-2", barcode="ROUTE-BAR-2", woo_id=903, product_id=503)
    invalid = client.post("/api/routes/commit", json=route_payload([first["id"], 123456]))
    assert invalid.json()["status"] == "rejected"
    assert client.get("/api/routes").json()["total"] == 0

    response = client.post("/api/routes/commit", json=route_payload([first["id"], second["id"]]))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert body["route_number"].startswith("RT-")
    assert body["total_stops"] == 2
    detail = client.get(f"/api/routes/{body['route_id']}").json()
    assert detail["created_by"] == "pytest@example.com"
    assert [stop["stop_sequence"] for stop in detail["stops"]] == [1, 2]
    assert [stop["order_id"] for stop in detail["stops"]] == [first["id"], second["id"]]

    duplicate = client.post("/api/routes/commit", json=route_payload([first["id"]]))
    assert duplicate.json()["status"] in {"rejected", "error"}
    assert client.get("/api/routes").json()["total"] == 1


def test_route_list_detail_export_finalize_cancel(client, monkeypatch):
    fulfilled = fulfilled_route_order(client, monkeypatch)
    commit = client.post("/api/routes/commit", json=route_payload([fulfilled["id"]]))
    route_id = commit.json()["route_id"]
    with Session(client.test_engine) as db:
        route = db.get(Route, route_id)
        route.start_address = "5855 99 Street NW, Edmonton, AB"
        route.end_address = "5855 99 Street NW, Edmonton, AB"
        route.total_distance = Decimal("12.34")
        route.estimated_duration_minutes = 27
        route.map_provider = "google"
        route.optimization_status = "manual"
        db.commit()

    listing = client.get("/api/routes")
    detail = client.get(f"/api/routes/{route_id}")
    exported = client.get(f"/api/routes/{route_id}/export")
    finalized = client.post(f"/api/routes/{route_id}/finalize")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert len(detail.json()["stops"]) == 1
    assert detail.json()["start_address"] == "5855 99 Street NW, Edmonton, AB"
    assert detail.json()["end_address"] == "5855 99 Street NW, Edmonton, AB"
    assert detail.json()["total_distance"] == 12.34
    assert detail.json()["estimated_duration_minutes"] == 27
    assert detail.json()["map_provider"] == "google"
    assert detail.json()["optimization_status"] == "manual"
    assert exported.status_code == 200
    header = exported.text.splitlines()[0].split(",")
    assert header == [
        "Route Number",
        "Route Date",
        "Route Status",
        "Route Name",
        "Driver Name",
        "Vehicle Name",
        "Stop Sequence",
        "Woo Order Number",
        "Woo Order ID",
        "Local Status",
        "Customer Name",
        "Customer Email",
        "Customer Phone",
        "Shipping Summary",
        "Delivery Notes",
        "Stop Status",
        "Order Total",
        "Created At",
    ]
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert rows[0]["Route Number"] == commit.json()["route_number"]
    assert finalized.json()["status"] == "finalized"
    completed_routes = client.get("/api/routes", params={"status": "finalized"}).json()
    assert completed_routes["total"] == 1
    assert completed_routes["routes"][0]["estimated_duration_minutes"] == 27
    cancelled = client.post(f"/api/routes/{route_id}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    cancelled_detail = client.get(f"/api/routes/{route_id}").json()
    assert len(cancelled_detail["stops"]) == 1
    candidates = client.get("/api/routes/candidates").json()["candidates"]
    assert fulfilled["id"] in {row["order_id"] for row in candidates}
