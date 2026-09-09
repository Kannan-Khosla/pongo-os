from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from math import ceil
import re
import time

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import httpx


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
MAX_OPTIMIZATION_STOPS = 200
PROJECT_ID_PATTERN = r"[a-z][a-z0-9-]{4,28}[a-z0-9]"


class RouteOptimizationError(ValueError):
    """Safe to show to staff; never includes provider payloads or credentials."""


def service_account_access_token(project_id: str, credentials_file: str = "", credentials_json: str = "") -> str:
    """Exchange a backend service-account key for a short-lived Google OAuth token."""
    if not isinstance(project_id, str) or re.fullmatch(PROJECT_ID_PATTERN, project_id) is None:
        raise RouteOptimizationError("Configure the backend Google Route Optimization project ID.")
    invalid = "Configure valid backend Google service-account credentials for route optimization."
    try:
        if not isinstance(credentials_file, str) or not isinstance(credentials_json, str):
            raise ValueError
        if bool(credentials_file.strip()) == bool(credentials_json.strip()):
            raise ValueError
        if credentials_file.strip():
            with open(credentials_file, encoding="utf-8") as credential_file:
                credentials_json = credential_file.read(65537)
        if len(credentials_json) > 65536:
            raise ValueError
        credentials = json.loads(credentials_json)
        if (
            not isinstance(credentials, dict)
            or credentials.get("type") != "service_account"
            or not isinstance(credentials.get("project_id"), str)
            or re.fullmatch(PROJECT_ID_PATTERN, credentials["project_id"]) is None
            or not isinstance(credentials.get("client_email"), str)
            or re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.gserviceaccount\.com", credentials["client_email"]) is None
            or credentials.get("token_uri", GOOGLE_TOKEN_URL) != GOOGLE_TOKEN_URL
            or not isinstance(credentials.get("private_key"), str)
        ):
            raise ValueError
        private_key = serialization.load_pem_private_key(credentials["private_key"].encode(), password=None)
        if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 2048:
            raise ValueError
        issued_at = int(time.time())
        claims = {
            "iss": credentials["client_email"],
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "aud": GOOGLE_TOKEN_URL,
            "iat": issued_at,
            "exp": issued_at + 3600,
        }
        encoded = [
            urlsafe_b64encode(json.dumps(part, separators=(",", ":")).encode()).rstrip(b"=")
            for part in ({"alg": "RS256", "typ": "JWT"}, claims)
        ]
        signing_input = b".".join(encoded)
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        assertion = (signing_input + b"." + urlsafe_b64encode(signature).rstrip(b"=")).decode("ascii")
    except (OSError, ValueError, TypeError, RecursionError, UnsupportedAlgorithm):
        raise RouteOptimizationError(invalid) from None

    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            timeout=4.0,
        )
        response.raise_for_status()
        result = response.json()
        token = result.get("access_token") if isinstance(result, dict) else None
        if (
            not isinstance(token, str)
            or re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token) is None
            or result.get("token_type", "Bearer") != "Bearer"
        ):
            raise ValueError
    except (httpx.HTTPError, ValueError):
        raise RouteOptimizationError("Google route optimization authentication is unavailable. Check the backend service-account configuration.") from None
    return token


def optimize_fleet_routes(
    start_location: tuple[float, float],
    locations: list[tuple[float, float]],
    driver_count: int,
    return_to_start: bool,
    *,
    project_id: str,
    credentials_file: str = "",
    credentials_json: str = "",
    allowed_vehicle_indices: list[list[int]] | None = None,
    service_minutes: int = 5,
    access_token: str | None = None,
) -> list[tuple[list[int], int]]:
    """Return each driver's source stop indexes and total seconds, including service time."""
    if type(driver_count) is not int or not 1 <= driver_count <= MAX_OPTIMIZATION_STOPS:
        raise RouteOptimizationError("Choose between 1 and 200 drivers for route optimization.")
    if not isinstance(locations, list) or len(locations) > MAX_OPTIMIZATION_STOPS:
        raise RouteOptimizationError("Google fleet optimization supports at most 200 delivery stops per request.")
    if type(return_to_start) is not bool or type(service_minutes) is not int or not 0 <= service_minutes <= 60:
        raise RouteOptimizationError("Route optimization needs a valid return setting and service time between 0 and 60 minutes.")
    if not locations:
        return [([], 0) for _ in range(driver_count)]
    for point in [start_location, *locations]:
        if (
            not isinstance(point, (tuple, list))
            or len(point) != 2
            or any(type(value) not in (int, float) for value in point)
            or not -90 <= point[0] <= 90
            or not -180 <= point[1] <= 180
        ):
            raise RouteOptimizationError("Valid shipping and start-location coordinates are required for Google route optimization.")
    if allowed_vehicle_indices is not None and (
        not isinstance(allowed_vehicle_indices, list)
        or len(allowed_vehicle_indices) != len(locations)
        or any(
            not isinstance(indices, list)
            or not indices
            or any(type(index) is not int or not 0 <= index < driver_count for index in indices)
            or len(set(indices)) != len(indices)
            for indices in allowed_vehicle_indices
        )
    ):
        raise RouteOptimizationError("Every delivery needs valid allowed drivers for Google route optimization.")
    if not isinstance(project_id, str) or re.fullmatch(PROJECT_ID_PATTERN, project_id) is None:
        raise RouteOptimizationError("Configure the backend Google Route Optimization project ID.")
    if access_token is not None and (not isinstance(access_token, str) or re.fullmatch(r"[A-Za-z0-9._~+/=-]+", access_token) is None):
        raise RouteOptimizationError("Google route optimization requires a valid backend access token.")
    if allowed_vehicle_indices is not None:
        allowed_vehicle_indices = [indices[:] for indices in allowed_vehicle_indices]

    started_at = datetime.now(timezone.utc).replace(microsecond=0)
    start_time = started_at.isoformat().replace("+00:00", "Z")
    end_time = (started_at + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    depot = {"latitude": start_location[0], "longitude": start_location[1]}
    shipments = [
        {
            "label": f"stop-{index}",
            "deliveries": [{"arrivalLocation": {"latitude": point[0], "longitude": point[1]}, "duration": f"{service_minutes * 60}s"}],
            **({"allowedVehicleIndices": allowed_vehicle_indices[index][:]} if allowed_vehicle_indices is not None else {}),
        }
        for index, point in enumerate(locations)
    ]
    vehicles = [
        {
            "label": f"driver-{index}",
            "travelMode": "DRIVING",
            "startLocation": depot.copy(),
            **({"endLocation": depot.copy()} if return_to_start else {}),
            "startTimeWindows": [{"startTime": start_time, "endTime": start_time}],
            "costPerHour": 1,
        }
        for index in range(driver_count)
    ]
    token = access_token or service_account_access_token(project_id, credentials_file, credentials_json)
    try:
        # ponytail: one synchronous 200-stop solve; use background jobs for larger fleets.
        response = httpx.post(
            f"https://routeoptimization.googleapis.com/v1/projects/{project_id}:optimizeTours",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "timeout": "8s",
                "searchMode": "CONSUME_ALL_AVAILABLE_TIME",
                "considerRoadTraffic": True,
                "model": {
                    "shipments": shipments,
                    "vehicles": vehicles,
                    "globalStartTime": start_time,
                    "globalEndTime": end_time,
                    # Favor earlier fleet completion; this does not guarantee equal route times.
                    "globalDurationCostPerHour": driver_count,
                },
            },
            timeout=12.0,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError):
        raise RouteOptimizationError("Google fleet optimization is unavailable. Check the provider configuration and try again.") from None
    return _parse_routes(result, len(locations), driver_count, allowed_vehicle_indices, service_minutes)


def _parse_routes(result, stop_count, driver_count, allowed_vehicle_indices, service_minutes):
    invalid = "Google did not return a complete, valid fleet plan for every selected shipping address."
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("routes"), list)
        or not result["routes"]
        or len(result["routes"]) > driver_count
        or result.get("skippedShipments", []) != []
        or result.get("validationErrors", []) != []
        or not isinstance(result.get("metrics", {}), dict)
        or type(result.get("metrics", {}).get("skippedMandatoryShipmentCount", 0)) is not int
        or result.get("metrics", {}).get("skippedMandatoryShipmentCount", 0) != 0
    ):
        raise RouteOptimizationError(invalid)
    routes = [([], 0) for _ in range(driver_count)]
    seen_drivers, seen_stops = set(), set()
    for route in result["routes"]:
        if not isinstance(route, dict):
            raise RouteOptimizationError(invalid)
        # Proto3 omits numeric zero indexes and false flags.
        driver = route.get("vehicleIndex", 0)
        visits = route.get("visits", [])
        if (
            type(driver) is not int
            or not 0 <= driver < driver_count
            or driver in seen_drivers
            or route.get("vehicleLabel", f"driver-{driver}") != f"driver-{driver}"
            or route.get("hasTrafficInfeasibilities", False) is not False
            or not isinstance(visits, list)
        ):
            raise RouteOptimizationError(invalid)
        seen_drivers.add(driver)
        indexes = []
        for visit in visits:
            if not isinstance(visit, dict):
                raise RouteOptimizationError(invalid)
            index = visit.get("shipmentIndex", 0)
            if (
                type(index) is not int
                or not 0 <= index < stop_count
                or index in seen_stops
                or visit.get("isPickup", False) is not False
                or type(visit.get("visitRequestIndex", 0)) is not int
                or visit.get("visitRequestIndex", 0) != 0
                or visit.get("shipmentLabel", f"stop-{index}") != f"stop-{index}"
                or (allowed_vehicle_indices is not None and driver not in allowed_vehicle_indices[index])
            ):
                raise RouteOptimizationError(invalid)
            indexes.append(index)
            seen_stops.add(index)
        metrics = route.get("metrics", {})
        duration = metrics.get("totalDuration", "0s" if not indexes else None) if isinstance(metrics, dict) else None
        if not isinstance(duration, str) or re.fullmatch(r"[0-9]{1,5}(?:\.[0-9]{1,9})?s", duration) is None:
            raise RouteOptimizationError(invalid)
        seconds = Decimal(duration[:-1])
        if (indexes and not 0 < seconds <= 86400) or seconds < len(indexes) * service_minutes * 60 or (not indexes and seconds != 0):
            raise RouteOptimizationError(invalid)
        routes[driver] = (indexes, ceil(seconds))
    if len(seen_stops) != stop_count:
        raise RouteOptimizationError(invalid)
    return routes
