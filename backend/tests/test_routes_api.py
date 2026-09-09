import csv
from concurrent.futures import Future
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
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


@pytest.mark.parametrize("return_to_start", [False, True])
def test_seven_deliveries_have_one_complete_link(client, return_to_start):
    for index in range(1, 8):
        seed_open_delivery_order(client, index)

    response = client.post(
        "/api/routes/open-orders/plan",
        json={"start_address": "5855 99 Street", "driver_count": 1, "return_to_start": return_to_start},
    )

    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    assert len(driver["google_maps_links"]) == 1
    link = driver["google_maps_links"][0]
    assert link["stop_count"] == 7
    assert link["requires_google_maps_app"] is True
    assert link["returns_to_start"] is return_to_start
    query = parse_qs(urlparse(link["url"]).query)
    addresses = [stop["address"] for stop in driver["stops"]]
    assert query["origin"] == ["5855 99 Street"]
    assert query["waypoints"][0].split("|") == (addresses if return_to_start else addresses[:-1])
    assert query["destination"] == ["5855 99 Street" if return_to_start else addresses[-1]]


@pytest.mark.parametrize("driver_count", [1, 2, 3, 7, 10])
def test_one_complete_link_per_nonempty_driver_covers_all_selected_orders(client, driver_count):
    selected = [seed_open_delivery_order(client, index) for index in range(1, 8)]
    seed_open_delivery_order(client, 10)
    response = client.post("/api/routes/open-orders/plan", json={"driver_count": driver_count, "order_ids": selected})
    assert response.status_code == 200, response.text
    drivers = response.json()["drivers"]
    ids = [stop["order_id"] for driver in drivers for stop in driver["stops"]]
    assert sorted(ids) == sorted(selected)
    for driver in drivers:
        assert len(driver["google_maps_links"]) == 1
        query = parse_qs(urlparse(driver["google_maps_links"][0]["url"]).query)
        addresses = query.get("waypoints", [""])[0].split("|") if query.get("waypoints") else []
        assert addresses + query["destination"] == [stop["address"] for stop in driver["stops"]]


@pytest.mark.parametrize("return_to_start, count, supported", [(False, 9, True), (False, 10, False), (True, 8, True), (True, 9, False)])
def test_route_link_capacity_never_drops_or_splits_stops(client, return_to_start, count, supported):
    selected = [seed_open_delivery_order(client, index) for index in range(1, count + 1)]
    response = client.post("/api/routes/open-orders/plan", json={"driver_count": 1, "return_to_start": return_to_start})
    assert response.status_code == 200, response.text
    body = response.json()
    driver = body["drivers"][0]
    assert sorted(stop["order_id"] for stop in driver["stops"]) == selected
    assert body["assigned_order_count"] == count
    assert len(driver["google_maps_links"]) == int(supported)
    assert (driver["google_maps_error"] is None) is supported
    if not supported:
        assert "No stops have been removed" in driver["google_maps_error"]


def test_long_route_url_is_not_shared_incomplete(client):
    order_ids = [seed_open_delivery_order(client, index) for index in range(1, 8)]
    with Session(client.test_engine) as db:
        for order_id in order_ids:
            db.get(Order, order_id).shipping_address_2 = "Suite A & B " * 20
        db.commit()
    response = client.post("/api/routes/open-orders/plan", json={"driver_count": 1})
    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    assert driver["stop_count"] == 7
    assert driver["google_maps_links"] == []
    assert "length limit" in driver["google_maps_error"]


def test_routes_use_shipping_only_and_reject_blank_shipping(client):
    valid = seed_open_delivery_order(client, 1)
    absent = seed_open_delivery_order(client, 2, address=False)
    whitespace = seed_open_delivery_order(client, 3)
    blank_city = seed_open_delivery_order(client, 4)
    with Session(client.test_engine) as db:
        for order_id in [valid, absent, whitespace, blank_city]:
            order = db.get(Order, order_id)
            order.billing_address_1 = "999 Billing Only Road"
            order.billing_city = "Calgary"
            order.billing_zip = "T2A 1A1"
        db.get(Order, whitespace).shipping_address_1 = " \t "
        db.get(Order, blank_city).shipping_city = " "
        db.get(Order, blank_city).shipping_zip = " "
        db.commit()
    response = client.post("/api/routes/open-orders/plan", json={"order_ids": [valid, absent, whitespace, blank_city]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [stop["order_id"] for driver in body["drivers"] for stop in driver["stops"]] == [valid]
    assert {order["order_id"] for order in body["unassigned_orders"]} == {absent, whitespace, blank_city}
    assert "Billing+Only" not in body["drivers"][0]["google_maps_links"][0]["url"]
    assert "101 Delivery Street" in body["drivers"][0]["stops"][0]["address"]


def mock_fleet_provider(monkeypatch):
    from app.services import routes
    provider = SimpleNamespace(
        settings=SimpleNamespace(
            route_optimization_provider="google_route_optimization", route_map_provider="disabled",
            google_routes_project_id="pongo-route-tests",
            google_routes_credentials_file="/not-read/test-route-credentials.json",
            google_routes_credentials_json="",
        ),
        token=Mock(return_value="test-oauth-token"),
        geocode=Mock(side_effect=lambda addresses, **kwargs: [(53 + index / 1000, -113.0) for index in range(len(addresses))]),
        fleet=Mock(),
    )
    monkeypatch.setattr(routes, "get_settings", lambda: provider.settings)
    monkeypatch.setattr(routes, "service_account_access_token", provider.token)
    monkeypatch.setattr(routes, "geocode_route_addresses", provider.geocode)
    monkeypatch.setattr(routes, "optimize_fleet_routes", provider.fleet)
    return provider


def test_route_plan_uses_google_sequence_and_time_only_when_requested(client, monkeypatch):
    provider = mock_fleet_provider(monkeypatch)
    provider.fleet.return_value = [([2, 1, 0], 1801)]
    for index in range(1, 4):
        seed_open_delivery_order(client, index)
    initial = client.post("/api/routes/open-orders/plan", json={"optimize": False}).json()
    for stage in [provider.token, provider.geocode, provider.fleet]:
        stage.assert_not_called()
    assert initial["drivers"][0]["optimization_status"] == "not_requested"
    response = client.post("/api/routes/open-orders/plan", json={"optimize": True})
    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    addresses = [stop["address"] for stop in initial["drivers"][0]["stops"]]
    assert driver["optimization_status"] == "optimized"
    assert driver["estimated_duration_minutes"] == 31
    assert [stop["address"] for stop in driver["stops"]] == list(reversed(addresses))
    assert [stop["stop_sequence"] for stop in driver["stops"]] == [1, 2, 3]
    assert [stop["latitude"] for stop in driver["stops"]] == [53.003, 53.002, 53.001]
    assert all(stop["coordinate_source"] == "google" for stop in driver["stops"])
    provider.token.assert_called_once_with("pongo-route-tests", "/not-read/test-route-credentials.json", "")
    provider.geocode.assert_called_once_with(
        [initial["start_address"], *addresses], project_id="pongo-route-tests", access_token="test-oauth-token",
    )
    provider.fleet.assert_called_once_with(
        (53.0, -113.0), [(53.001, -113.0), (53.002, -113.0), (53.003, -113.0)], 1, False,
        project_id="pongo-route-tests", access_token="test-oauth-token", allowed_vehicle_indices=None, service_minutes=5,
    )
    query = parse_qs(urlparse(driver["google_maps_links"][0]["url"]).query)
    assert query["waypoints"][0].split("|") + query["destination"] == list(reversed(addresses))
    assert "test-oauth-token" not in response.text
    assert "test-route-credentials" not in response.text


def test_forty_stops_use_one_fleet_call_and_allow_reassignment_across_four_drivers(client, monkeypatch):
    provider = mock_fleet_provider(monkeypatch)
    selected = [seed_open_delivery_order(client, index, postal_code="T6B 1A1") for index in range(1, 41)]
    seed_open_delivery_order(client, 50)
    payload = {"driver_count": 4, "order_ids": selected, "return_to_start": True, "service_minutes": 7}
    initial = client.post("/api/routes/open-orders/plan", json=payload).json()
    source_stops = [stop for driver in initial["drivers"] for stop in driver["stops"]]
    assignments = [list(reversed(range(index, 40, 4))) for index in range(4)]
    provider.fleet.return_value = [(indexes, 6001 + 600 * index) for index, indexes in enumerate(assignments)]

    response = client.post("/api/routes/open-orders/plan", json={**payload, "optimize": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assigned_order_count"] == 40
    assert body["unassigned_orders"] == []
    assert sorted(stop["order_id"] for driver in body["drivers"] for stop in driver["stops"]) == selected
    for index, driver in enumerate(body["drivers"]):
        assert [stop["order_id"] for stop in driver["stops"]] == [source_stops[row]["order_id"] for row in assignments[index]]
        assert driver["optimization_status"] == "optimized"
        assert driver["estimated_duration_minutes"] == 101 + 10 * index
        # All ten deliveries stay visible even though one Maps link cannot hold them.
        assert driver["google_maps_links"] == []
        assert "No stops have been removed" in driver["google_maps_error"]
    assert body["total_estimated_duration_minutes"] == 464
    assert body["estimated_completion_minutes"] == 131
    assert body["map"]["coordinate_count"] == 40
    provider.token.assert_called_once()
    provider.geocode.assert_called_once_with(
        [initial["start_address"], *(stop["address"] for stop in source_stops)],
        project_id="pongo-route-tests", access_token="test-oauth-token",
    )
    provider.fleet.assert_called_once()
    assert len(provider.fleet.call_args.args[1]) == 40
    assert provider.fleet.call_args.args[2:] == (4, True)
    assert provider.fleet.call_args.kwargs["allowed_vehicle_indices"] is None
    assert provider.fleet.call_args.kwargs["service_minutes"] == 7
    assert client.get("/api/routes").json()["total"] == 0


def test_fleet_optimizer_receives_hard_direction_eligibility_and_excludes_unassigned_zones(client, monkeypatch):
    provider = mock_fleet_provider(monkeypatch)
    east = [seed_open_delivery_order(client, index, postal_code="T6B 1A1") for index in [1, 2]]
    west = seed_open_delivery_order(client, 3, postal_code="T5P 1A1")
    north = seed_open_delivery_order(client, 4, postal_code="T5Z 1A1")
    payload = {
        "driver_count": 2, "order_ids": [*east, west, north], "assignment_method": "directions",
        "direction_assignments": [
            {"driver_number": 1, "directions": ["E"]},
            {"driver_number": 2, "directions": ["E", "W"]},
        ],
    }
    initial = client.post("/api/routes/open-orders/plan", json=payload).json()
    source_stops = [stop for driver in initial["drivers"] for stop in driver["stops"]]
    expected_eligibility = [[0, 1] if stop["direction"] == "E" else [1] for stop in source_stops]
    provider.fleet.return_value = [
        ([index for index, stop in enumerate(source_stops) if stop["direction"] == "E"], 1200),
        ([index for index, stop in enumerate(source_stops) if stop["direction"] == "W"], 600),
    ]
    response = client.post("/api/routes/open-orders/plan", json={**payload, "optimize": True})
    assert response.status_code == 200, response.text
    body = response.json()
    provider.fleet.assert_called_once()
    assert provider.fleet.call_args.kwargs["allowed_vehicle_indices"] == expected_eligibility
    assert len(provider.geocode.call_args.args[0]) == 4  # Warehouse plus three covered deliveries.
    assert {stop["order_id"] for stop in body["drivers"][0]["stops"]} == set(east)
    assert [stop["order_id"] for stop in body["drivers"][1]["stops"]] == [west]
    assert body["drivers"][0]["directions"] == ["E"]
    assert body["drivers"][1]["directions"] == ["E", "W"]
    assert [(order["order_id"], order["reason_code"]) for order in body["unassigned_orders"]] == [(north, "zone_not_assigned")]
    assert body["assigned_order_count"] == 3


@pytest.mark.parametrize("failed_stage, message", [
    ("token", "Google authorization is unavailable."),
    ("geocode", "Route address 2 lookup timed out."),
    ("fleet", "Google could not produce a complete route plan."),
])
def test_optimization_failure_preserves_all_stops_with_truthful_status(client, monkeypatch, failed_stage, message):
    from app.services.routes import RouteOptimizationError
    provider = mock_fleet_provider(monkeypatch)
    getattr(provider, failed_stage).side_effect = RouteOptimizationError(message)
    selected = [seed_open_delivery_order(client, index) for index in range(1, 7)]
    payload = {"driver_count": 2, "order_ids": selected}
    initial = client.post("/api/routes/open-orders/plan", json=payload).json()
    response = client.post("/api/routes/open-orders/plan", json={**payload, "optimize": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assigned_order_count"] == 6
    assert body["unassigned_orders"] == []
    for driver, original in zip(body["drivers"], initial["drivers"], strict=True):
        assert driver["stops"] == original["stops"]
        assert driver["optimization_status"] == "unavailable"
        assert message in driver["optimization_message"]
        assert "Google optimization was not applied" in driver["optimization_message"]
        assert driver["estimated_duration_minutes"] == original["estimated_duration_minutes"]
        assert len(driver["google_maps_links"]) == 1
    stages = ["token", "geocode", "fleet"]
    for index, stage in enumerate(stages):
        assert getattr(provider, stage).call_count == int(index <= stages.index(failed_stage))
    assert "test-oauth-token" not in response.text


def test_unconfigured_optimizer_does_not_call_google(client, monkeypatch):
    provider = mock_fleet_provider(monkeypatch)
    provider.settings.route_optimization_provider = "disabled"
    order_id = seed_open_delivery_order(client, 1)
    response = client.post("/api/routes/open-orders/plan", json={"optimize": True})
    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    assert driver["optimization_status"] == "not_configured"
    assert [stop["order_id"] for stop in driver["stops"]] == [order_id]
    for stage in [provider.token, provider.geocode, provider.fleet]:
        stage.assert_not_called()


def test_outer_optimization_deadline_cancels_work_and_preserves_every_stop(client, monkeypatch):
    from app.services import routes
    provider = mock_fleet_provider(monkeypatch)
    selected = [seed_open_delivery_order(client, index) for index in range(1, 5)]
    payload = {"driver_count": 2, "order_ids": selected}
    initial = client.post("/api/routes/open-orders/plan", json=payload).json()
    future = Mock()
    future.result.side_effect = TimeoutError
    executor = Mock()
    executor.submit.return_value = future
    pool = Mock(return_value=executor)
    monkeypatch.setattr(routes, "ThreadPoolExecutor", pool)
    monkeypatch.setattr(routes, "monotonic", lambda: 100.0)
    response = client.post("/api/routes/open-orders/plan", json={**payload, "optimize": True})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assigned_order_count"] == 4
    assert body["unassigned_orders"] == []
    for driver, original in zip(body["drivers"], initial["drivers"], strict=True):
        assert driver["stops"] == original["stops"]
        assert driver["optimization_status"] == "unavailable"
        assert "timed out" in driver["optimization_message"]
    future.result.assert_called_once_with(timeout=27.0)
    future.cancel.assert_called_once()
    pool.assert_called_once_with(max_workers=1)
    executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
    for stage in [provider.token, provider.geocode, provider.fleet]:
        stage.assert_not_called()


@pytest.mark.parametrize("expires_after", ["token", "geocode"])
def test_expired_planning_deadline_never_starts_a_later_paid_stage(client, monkeypatch, expires_after):
    from app.services import routes
    provider = mock_fleet_provider(monkeypatch)
    order_id = seed_open_delivery_order(client, 1)
    clock = [100.0]
    monkeypatch.setattr(routes, "monotonic", lambda: clock[0])

    def authenticate(*args):
        if expires_after == "token":
            clock[0] = 128.0
        return "test-oauth-token"

    def geocode(addresses, **kwargs):
        clock[0] = 128.0
        return [(53.0, -113.0) for address in addresses]

    def run_now(function):
        future = Future()
        try:
            future.set_result(function())
        except Exception as exc:
            future.set_exception(exc)
        return future

    provider.token.side_effect = authenticate
    provider.geocode.side_effect = geocode
    executor = Mock()
    executor.submit.side_effect = run_now
    monkeypatch.setattr(routes, "ThreadPoolExecutor", Mock(return_value=executor))
    response = client.post("/api/routes/open-orders/plan", json={"optimize": True})
    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    assert driver["optimization_status"] == "unavailable"
    assert "timed out" in driver["optimization_message"]
    assert [stop["order_id"] for stop in driver["stops"]] == [order_id]
    provider.token.assert_called_once()
    assert provider.geocode.call_count == int(expires_after == "geocode")
    provider.fleet.assert_not_called()


def test_address_separator_cannot_silently_add_extra_map_stops(client):
    first = seed_open_delivery_order(client, 1, postal_code="T6B 1A1")
    seed_open_delivery_order(client, 2, postal_code="T6B 1A2")
    with Session(client.test_engine) as db:
        db.get(Order, first).shipping_address_1 = "101 Road | Other address"
        db.commit()
    response = client.post("/api/routes/open-orders/plan", json={"return_to_start": True})
    assert response.status_code == 200, response.text
    driver = response.json()["drivers"][0]
    assert driver["stop_count"] == 2
    assert driver["google_maps_links"] == []
    assert "separator" in driver["google_maps_error"]


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
    pdf_preview = client.get(f"/api/routes/{route_id}/pdf", params={"preview": True})
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
    assert pdf_preview.content.startswith(b"%PDF")
    assert pdf_preview.headers["content-disposition"].startswith("inline;")
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
