from concurrent.futures import FIRST_EXCEPTION, Future
from unittest.mock import Mock, patch
from urllib.parse import quote

import httpx
import pytest

from app.services.route_geocoding import geocode_route_addresses
from app.services.route_optimization import RouteOptimizationError


PROJECT_ID = "pongo-route-tests"
TOKEN = "private-access-token"


def geocode_result(latitude=53.5, longitude=-113.5, granularity="ROOFTOP"):
    return {"results": [{"location": {"latitude": latitude, "longitude": longitude}, "granularity": granularity}]}


def response(body):
    return httpx.Response(200, json=body, request=httpx.Request("GET", "https://example.test"))


def test_geocoding_deduplicates_addresses_preserves_order_and_encodes_path():
    address_a = "7/1 Shipping St #2?unit=A+B% & Edmonton"
    address_b = "Other shipping address"
    urls = {
        f"https://geocode.googleapis.com/v4/geocode/address/{quote(address_a, safe='')}": geocode_result(),
        f"https://geocode.googleapis.com/v4/geocode/address/{quote(address_b, safe='')}": geocode_result(54, -114, "RANGE_INTERPOLATED"),
    }
    with patch("app.services.route_geocoding.httpx.get", side_effect=lambda url, **kwargs: response(urls[url])) as get:
        assert geocode_route_addresses([address_a, address_b, address_a], project_id=PROJECT_ID, access_token=TOKEN) == [
            (53.5, -113.5), (54.0, -114.0), (53.5, -113.5),
        ]
    assert get.call_count == 2
    for call in get.call_args_list:
        assert "?" not in call.args[0]
        assert TOKEN not in call.args[0]
        assert call.kwargs == {
            "headers": {
                "Authorization": f"Bearer {TOKEN}",
                "X-Goog-User-Project": PROJECT_ID,
                "X-Goog-FieldMask": "results.location,results.granularity",
            },
            "timeout": 4.0,
        }


@pytest.mark.parametrize("location, expected", [
    ({"longitude": 180}, (0.0, 180.0)),
    ({"latitude": -90}, (-90.0, 0.0)),
    ({}, (0.0, 0.0)),
    ({"latitude": 90, "longitude": -180}, (90.0, -180.0)),
])
def test_geocoding_accepts_valid_bounds_and_proto_zero_coordinates(location, expected):
    body = geocode_result()
    body["results"][0]["location"] = location
    with patch("app.services.route_geocoding.httpx.get", return_value=response(body)):
        assert geocode_route_addresses(["Shipping"], project_id=PROJECT_ID, access_token=TOKEN) == [expected]


def test_geocoding_rejects_ambiguous_imprecise_partial_and_malformed_results():
    invalid = [None, [], {}, {"error": {"message": TOKEN}}, {"results": []}, {"results": [None]}, {"results": [*geocode_result()["results"]] * 2}]
    for field, value in [
        ("granularity", "APPROXIMATE"), ("granularity", "GEOMETRIC_CENTER"),
        ("granularity", "GRANULARITY_UNSPECIFIED"), ("granularity", None),
        ("partialMatch", True), ("location", None), ("location", []),
    ]:
        body = geocode_result()
        body["results"][0][field] = value
        invalid.append(body)
    missing_location = geocode_result()
    del missing_location["results"][0]["location"]
    invalid.append(missing_location)
    for field, values in {"latitude": [90.1, -90.1, True, None, "53.5"], "longitude": [180.1, -180.1]}.items():
        for value in values:
            body = geocode_result()
            body["results"][0]["location"][field] = value
            invalid.append(body)
    for body in invalid:
        with patch("app.services.route_geocoding.httpx.get", return_value=response(body)):
            with pytest.raises(RouteOptimizationError, match="Route address 1 could not be located precisely") as error:
                geocode_route_addresses(["Private shipping address"], project_id=PROJECT_ID, access_token=TOKEN)
        assert TOKEN not in str(error.value)
        assert "Private shipping" not in str(error.value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10 ** 1000])
def test_geocoding_rejects_nonfinite_and_overflow_coordinates(value):
    mocked_response = Mock()
    mocked_response.json.return_value = geocode_result(value)
    with patch("app.services.route_geocoding.httpx.get", return_value=mocked_response):
        with pytest.raises(RouteOptimizationError, match="could not be located precisely"):
            geocode_route_addresses(["Shipping"], project_id=PROJECT_ID, access_token=TOKEN)


@pytest.mark.parametrize("failure", [
    httpx.TimeoutException(f"timeout {TOKEN}"),
    httpx.Response(403, json={"error": TOKEN}, request=httpx.Request("GET", "https://example.test/Private-shipping")),
    httpx.Response(200, text=f"invalid json {TOKEN}", request=httpx.Request("GET", "https://example.test")),
])
def test_geocoding_sanitizes_provider_failures(failure):
    kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
    with patch("app.services.route_geocoding.httpx.get", **kwargs):
        with pytest.raises(RouteOptimizationError) as error:
            geocode_route_addresses(["Private shipping"], project_id=PROJECT_ID, access_token=TOKEN)
    assert TOKEN not in str(error.value)
    assert "Private shipping" not in str(error.value)


def test_geocoding_validates_inputs_without_provider_requests():
    with patch("app.services.route_geocoding.httpx.get") as get:
        assert geocode_route_addresses([], project_id=PROJECT_ID, access_token=TOKEN) == []
        for addresses in [["Shipping"] * 202, [" "], [None], ["x" * 1001], ["é" * 1000]]:
            with pytest.raises(RouteOptimizationError):
                geocode_route_addresses(addresses, project_id=PROJECT_ID, access_token=TOKEN)
        for project in ["", "short", "Uppercase-project", "pongo\nX-Injected: value", "1invalid", "invalid-", "a" * 31]:
            with pytest.raises(RouteOptimizationError, match="valid Google Cloud project ID") as error:
                geocode_route_addresses(["Shipping"], project_id=project, access_token=TOKEN)
            assert project not in str(error.value) or not project
        with pytest.raises(RouteOptimizationError, match="authorization"):
            geocode_route_addresses(["Shipping"], project_id=PROJECT_ID, access_token=" ")
        get.assert_not_called()


def test_geocoding_reports_original_stop_index_and_accepts_201_entries():
    with patch("app.services.route_geocoding.httpx.get", return_value=response(geocode_result())) as get:
        assert len(geocode_route_addresses(["Shipping"] * 201, project_id=PROJECT_ID, access_token=TOKEN)) == 201
        get.assert_called_once()
    with patch("app.services.route_geocoding.httpx.get") as get:
        with pytest.raises(RouteOptimizationError, match="Route address 3"):
            geocode_route_addresses(["Shipping", "Shipping", " "], project_id=PROJECT_ID, access_token=TOKEN)
        get.assert_not_called()


def test_geocoding_deadline_cancels_pending_work_without_waiting_for_workers():
    futures = [Future() for _ in range(12)]
    executor = Mock()
    executor.submit.side_effect = futures
    with patch("app.services.route_geocoding.ThreadPoolExecutor", return_value=executor) as pool:
        with patch("app.services.route_geocoding.wait", return_value=(set(), set(futures))) as wait:
            with pytest.raises(RouteOptimizationError, match="Route address 1 lookup timed out"):
                geocode_route_addresses([f"Shipping {index}" for index in range(12)], project_id=PROJECT_ID, access_token=TOKEN)
    pool.assert_called_once_with(max_workers=10)
    assert 0 <= wait.call_args.kwargs["timeout"] <= 10.0
    assert wait.call_args.kwargs["return_when"] == FIRST_EXCEPTION
    assert all(future.cancelled() for future in futures)
    executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


def test_geocoding_does_not_start_provider_calls_after_the_deadline():
    with patch("app.services.route_geocoding.monotonic", side_effect=[0, 11, 11]):
        with patch("app.services.route_geocoding.httpx.get") as get:
            with pytest.raises(RouteOptimizationError, match="timed out"):
                geocode_route_addresses(["Shipping"], project_id=PROJECT_ID, access_token=TOKEN)
            get.assert_not_called()
