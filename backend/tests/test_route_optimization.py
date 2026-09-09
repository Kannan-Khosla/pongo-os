from base64 import urlsafe_b64decode
from copy import deepcopy
import json
from unittest.mock import mock_open, patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
import httpx
import pytest

from app.services.route_optimization import GOOGLE_TOKEN_URL, RouteOptimizationError, service_account_access_token, optimize_fleet_routes


def response(body, status=200):
    return httpx.Response(status, content=json.dumps(body), request=httpx.Request("POST", "https://example.test"))


def fleet_response(groups):
    return {"routes": [
        {
            "vehicleIndex": driver,
            "visits": [{"shipmentIndex": index} for index in indexes],
            "metrics": {"totalDuration": f"{len(indexes) * 600 + (0.1 if indexes else 0)}s"},
        }
        for driver, indexes in enumerate(groups)
    ]}


def optimize(locations=None, **kwargs):
    return optimize_fleet_routes(
        (53.5, -113.5), locations if locations is not None else [(53.6, -113.6)],
        kwargs.pop("driver_count", 1), kwargs.pop("return_to_start", False),
        project_id=kwargs.pop("project_id", "pongo-test"), **kwargs,
    )


@pytest.mark.parametrize("return_to_start", [False, True])
def test_one_fleet_request_handles_40_stops_and_4_drivers_with_required_deliveries(return_to_start):
    locations = [(53.5 + index / 1000, -113.5) for index in range(40)]
    groups = [list(range(driver, 40, 4))[::-1] for driver in range(4)]
    allowed = [[index % 4] for index in range(40)]
    original = deepcopy((locations, allowed))
    body = fleet_response(groups)
    # Zero-valued protobuf fields may be omitted; never use response order for source identity.
    del body["routes"][0]["vehicleIndex"]
    del body["routes"][0]["visits"][-1]["shipmentIndex"]
    body["routes"].reverse()
    with patch("app.services.route_optimization.service_account_access_token", return_value="test-token") as token:
        with patch("app.services.route_optimization.httpx.post", return_value=response(body)) as post:
            actual = optimize(locations, driver_count=4, return_to_start=return_to_start, allowed_vehicle_indices=allowed, credentials_json="backend-secret")
    assert actual == [(group, 6001) for group in groups]
    assert (locations, allowed) == original
    token.assert_called_once_with("pongo-test", "", "backend-secret")
    post.assert_called_once()
    assert post.call_args.args == ("https://routeoptimization.googleapis.com/v1/projects/pongo-test:optimizeTours",)
    request = post.call_args.kwargs
    assert request["timeout"] == 12.0
    assert request["headers"] == {"Authorization": "Bearer test-token"}
    assert request["json"]["timeout"] == "8s"
    assert request["json"]["searchMode"] == "CONSUME_ALL_AVAILABLE_TIME"
    assert request["json"]["considerRoadTraffic"] is True
    model = request["json"]["model"]
    assert model["globalDurationCostPerHour"] == 4
    assert len(model["vehicles"]) == 4
    assert len(model["shipments"]) == 40
    for index, shipment in enumerate(model["shipments"]):
        assert shipment == {
            "label": f"stop-{index}",
            "deliveries": [{"arrivalLocation": {"latitude": locations[index][0], "longitude": locations[index][1]}, "duration": "300s"}],
            "allowedVehicleIndices": [index % 4],
        }
    for index, vehicle in enumerate(model["vehicles"]):
        assert vehicle["label"] == f"driver-{index}"
        assert vehicle["startLocation"] == {"latitude": 53.5, "longitude": -113.5}
        assert vehicle.get("endLocation") == (vehicle["startLocation"] if return_to_start else None)
        assert vehicle["startTimeWindows"] == [{"startTime": model["globalStartTime"], "endTime": model["globalStartTime"]}]
        assert vehicle["costPerHour"] == 1
    assert "backend-secret" not in json.dumps(model)


def test_duplicate_coordinates_keep_separate_shipments_and_unused_drivers_are_empty():
    body = fleet_response([[1, 0], [], []])
    del body["routes"][1]["visits"]
    del body["routes"][1]["metrics"]
    body["routes"].pop()
    with patch("app.services.route_optimization.service_account_access_token") as token:
        with patch("app.services.route_optimization.httpx.post", return_value=response(body)):
            assert optimize([(53.6, -113.6)] * 2, driver_count=3, access_token="shared-token") == [([1, 0], 1201), ([], 0), ([], 0)]
        token.assert_not_called()


def test_optimizer_rejects_partial_duplicate_malformed_and_disallowed_routes():
    valid = fleet_response([[0], [1]])
    invalid = [None, {}, {"routes": []}, {"routes": None}, {"routes": [None]}, {"routes": valid["routes"][:1]}]
    for route_field, value in [
        ("vehicleIndex", -1), ("vehicleIndex", True), ("vehicleIndex", 2), ("vehicleLabel", "driver-1"),
        ("visits", None), ("visits", []), ("metrics", None), ("metrics", {}),
        ("hasTrafficInfeasibilities", True), ("hasTrafficInfeasibilities", 0),
    ]:
        malformed = deepcopy(valid)
        malformed["routes"][0][route_field] = value
        invalid.append(malformed)
    for field, value in [
        ("shipmentIndex", -1), ("shipmentIndex", True), ("shipmentIndex", 2), ("shipmentIndex", 1),
        ("visitRequestIndex", 1), ("visitRequestIndex", False), ("isPickup", True), ("isPickup", 0),
        ("shipmentLabel", "stop-1"),
    ]:
        malformed = deepcopy(valid)
        malformed["routes"][0]["visits"][0][field] = value
        invalid.append(malformed)
    for duration in [None, "NaNs", "Infinitys", "-1s", "1e3s", "1.1234567890s", "0s", "299s", "86401s"]:
        malformed = deepcopy(valid)
        malformed["routes"][0]["metrics"]["totalDuration"] = duration
        invalid.append(malformed)
    for field, value in [
        ("skippedShipments", [{"index": 0, "message": "private shipping"}]),
        ("validationErrors", [{"errorMessage": "private shipping"}]),
        ("metrics", {"skippedMandatoryShipmentCount": 1}),
        ("metrics", {"skippedMandatoryShipmentCount": False}), ("metrics", None),
    ]:
        invalid.append({**deepcopy(valid), field: value})
    invalid.append({"routes": [valid["routes"][0], valid["routes"][0]]})
    invalid.append({"routes": [{**valid["routes"][0], "visits": [{"shipmentIndex": 0}, {"shipmentIndex": 0}]}]})
    invalid.append({"routes": [{**valid["routes"][0], "visits": [None]}]})
    for body in invalid:
        with patch("app.services.route_optimization.httpx.post", return_value=response(body)):
            with pytest.raises(RouteOptimizationError, match="complete, valid fleet plan") as error:
                optimize([(53.6, -113.6), (53.7, -113.7)], driver_count=2, access_token="secret-token")
        assert "private" not in str(error.value)
        assert "secret-token" not in str(error.value)
    with patch("app.services.route_optimization.httpx.post", return_value=response(valid)):
        with pytest.raises(RouteOptimizationError, match="complete, valid fleet plan"):
            optimize([(53.6, -113.6), (53.7, -113.7)], driver_count=2, allowed_vehicle_indices=[[1], [0]], access_token="test-token")


@pytest.mark.parametrize("failure", [
    response({"message": "secret-token private shipping"}, 403),
    httpx.Response(200, text="private shipping", request=httpx.Request("POST", "https://example.test")),
    httpx.TimeoutException("secret-token private shipping"),
])
def test_optimizer_sanitizes_provider_errors_without_retry(failure):
    with patch("app.services.route_optimization.httpx.post", side_effect=[failure]) as post:
        with pytest.raises(RouteOptimizationError, match="unavailable") as error:
            optimize(access_token="secret-token")
    post.assert_called_once()
    assert "secret-token" not in str(error.value)
    assert "private shipping" not in str(error.value)
    assert error.value.__suppress_context__


def test_invalid_or_empty_inputs_never_call_google():
    cases = [
        {"locations": [(53.5, -113.5)] * 201}, {"locations": "secret"}, {"locations": [(float("nan"), 0)]},
        {"locations": [(91, 0)]}, {"locations": [(0, 181)]}, {"locations": [(True, 0)]},
        {"locations": [(10**1000, 0)]}, {"locations": [(0, float("inf"))]},
        {"locations": [(1,)]}, {"driver_count": 0}, {"driver_count": True}, {"service_minutes": -1},
        {"service_minutes": 61}, {"return_to_start": 1}, {"project_id": "x/../../secret"},
        {"allowed_vehicle_indices": [[]]}, {"allowed_vehicle_indices": [[True]]},
        {"allowed_vehicle_indices": [[1]]}, {"allowed_vehicle_indices": [[0, 0]]},
        {"allowed_vehicle_indices": []}, {"allowed_vehicle_indices": "secret"}, {"access_token": "secret\r\nvalue"},
    ]
    with patch("app.services.route_optimization.httpx.post") as post:
        assert optimize([], driver_count=3) == [([], 0), ([], 0), ([], 0)]
        for case in cases:
            with pytest.raises(RouteOptimizationError):
                optimize(**case)
        post.assert_not_called()


def service_account():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    credentials = {
        "type": "service_account", "project_id": "pongo-test", "client_email": "routes@pongo-test.iam.gserviceaccount.com",
        "private_key": key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
        "token_uri": GOOGLE_TOKEN_URL,
    }
    return key, credentials


@pytest.mark.parametrize("from_file", [False, True])
def test_service_account_jwt_signature_scope_fixed_destination_and_file_support(from_file):
    key, credentials = service_account()
    kwargs = {"credentials_file": "/test/service-account.json"} if from_file else {"credentials_json": json.dumps(credentials)}
    with patch("builtins.open", mock_open(read_data=json.dumps(credentials))):
        with patch("app.services.route_optimization.time.time", return_value=1700000000):
            with patch("app.services.route_optimization.httpx.post", return_value=response({"access_token": "test-token", "token_type": "Bearer"})) as post:
                assert service_account_access_token("pongo-test", **kwargs) == "test-token"
    post.assert_called_once()
    assert post.call_args.args == (GOOGLE_TOKEN_URL,)
    assert post.call_args.kwargs["timeout"] == 4.0
    data = post.call_args.kwargs["data"]
    assert data["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    header, claims, signature = data["assertion"].split(".")
    assert json.loads(urlsafe_b64decode(header + "==")) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(urlsafe_b64decode(claims + "==")) == {
        "iss": credentials["client_email"], "scope": "https://www.googleapis.com/auth/cloud-platform",
        "aud": GOOGLE_TOKEN_URL, "iat": 1700000000, "exp": 1700003600,
    }
    key.public_key().verify(urlsafe_b64decode(signature + "=="), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    assert credentials["private_key"] not in json.dumps(data)


def test_invalid_credentials_fail_before_any_http_call_and_hide_secret():
    _, valid = service_account()
    invalid = ["", "private-secret", "{}", "[]", "x" * 65537]
    for field, value in [
        ("type", "external_account"), ("project_id", "../private-secret"), ("client_email", "private-secret"),
        ("private_key", "private-secret"), ("private_key", None), ("token_uri", "https://private-secret.test/token"),
    ]:
        invalid.append(json.dumps({**valid, field: value}))
    for key in [ec.generate_private_key(ec.SECP256R1()), rsa.generate_private_key(public_exponent=65537, key_size=1024)]:
        private_key = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        invalid.append(json.dumps({**valid, "private_key": private_key}))
    with patch("app.services.route_optimization.httpx.post") as post:
        for credentials in invalid:
            with pytest.raises(RouteOptimizationError, match="service-account credentials") as error:
                service_account_access_token("pongo-test", credentials_json=credentials)
            assert "private-secret" not in str(error.value)
            assert error.value.__suppress_context__
        with pytest.raises(RouteOptimizationError):
            service_account_access_token("pongo-test", credentials_file="/test/key.json", credentials_json=json.dumps(valid))
        with patch("builtins.open", side_effect=OSError("private-secret")):
            with pytest.raises(RouteOptimizationError) as error:
                service_account_access_token("pongo-test", credentials_file="/test/private-secret.json")
            assert "private-secret" not in str(error.value)
        post.assert_not_called()


def test_auth_errors_are_sanitized_and_never_call_optimizer():
    _, credentials = service_account()
    for failure in [
        response({"error": "private-secret"}, 401), response([]), response({}),
        response({"access_token": "secret\r\ninjected"}), response({"access_token": "token", "token_type": "Other"}),
        httpx.TimeoutException("private-secret"),
    ]:
        with patch("app.services.route_optimization.httpx.post", side_effect=[failure]) as post:
            with pytest.raises(RouteOptimizationError, match="authentication is unavailable") as error:
                optimize(credentials_json=json.dumps(credentials))
        post.assert_called_once()
        assert "private-secret" not in str(error.value)
        assert credentials["private_key"] not in str(error.value)
