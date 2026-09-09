from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from math import isfinite
import re
from time import monotonic
from urllib.parse import quote

import httpx

from app.services.route_optimization import RouteOptimizationError


def geocode_route_addresses(
    addresses: list[str], *, project_id: str, access_token: str
) -> list[tuple[float, float]]:
    """Resolve unique shipping addresses once and preserve the supplied stop order."""
    deadline = monotonic() + 10.0
    if not isinstance(addresses, list) or len(addresses) > 201:
        raise RouteOptimizationError("Geocoding supports at most 200 delivery addresses plus the starting location.")
    if not addresses:
        return []
    if not isinstance(project_id, str) or re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project_id) is None:
        raise RouteOptimizationError("Configure a valid Google Cloud project ID for route geocoding.")
    if not isinstance(access_token, str) or not access_token.strip():
        raise RouteOptimizationError("Google authorization is unavailable for route geocoding.")

    unique: dict[str, tuple[int, str]] = {}
    for index, address in enumerate(addresses, start=1):
        if not isinstance(address, str) or not address.strip() or len(address) > 1000:
            raise RouteOptimizationError(f"Route address {index} must contain a shipping address of at most 1,000 characters.")
        url = f"https://geocode.googleapis.com/v4/geocode/address/{quote(address, safe='')}"
        if len(url) > 4096:
            raise RouteOptimizationError(f"Route address {index} is too long for Google geocoding.")
        unique.setdefault(address, (index, url))

    def resolve(index: int, url: str) -> tuple[float, float]:
        if monotonic() >= deadline:
            raise RouteOptimizationError(f"Route address {index} lookup timed out. Try route optimization again.")
        try:
            response = httpx.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Goog-User-Project": project_id,
                    # Geocoding v4 has no partialMatch field; never request a nonexistent field.
                    "X-Goog-FieldMask": "results.location,results.granularity",
                },
                timeout=4.0,
            )
            response.raise_for_status()
            body = response.json()
            results = body.get("results") if isinstance(body, dict) and not body.get("error") else None
            if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
                raise ValueError
            result = results[0]
            location = result.get("location")
            if (
                result.get("granularity") not in {"ROOFTOP", "RANGE_INTERPOLATED"}
                or result.get("partialMatch")
                or not isinstance(location, dict)
            ):
                raise ValueError
            # Proto3 may omit coordinates equal to zero; a missing location is still invalid.
            latitude, longitude = location.get("latitude", 0.0), location.get("longitude", 0.0)
            if (
                type(latitude) not in (int, float)
                or type(longitude) not in (int, float)
                or not isfinite(latitude)
                or not isfinite(longitude)
                or not -90 <= latitude <= 90
                or not -180 <= longitude <= 180
            ):
                raise ValueError
            return float(latitude), float(longitude)
        except (httpx.HTTPError, ValueError, TypeError, OverflowError):
            raise RouteOptimizationError(
                f"Route address {index} could not be located precisely. Check the shipping address and geocoding configuration."
            ) from None

    executor = ThreadPoolExecutor(max_workers=min(10, len(unique)))
    futures = {}
    try:
        futures = {address: executor.submit(resolve, index, url) for address, (index, url) in unique.items()}
        done, pending = wait(futures.values(), timeout=max(0.0, deadline - monotonic()), return_when=FIRST_EXCEPTION)
        for future in done:
            future.result()
        if pending:
            index = next(unique[address][0] for address, future in futures.items() if future in pending)
            raise RouteOptimizationError(f"Route address {index} lookup timed out. Try route optimization again.")
        return [futures[address].result() for address in addresses]
    finally:
        for future in futures.values():
            future.cancel()
        # Do not let running lookups extend the planner's overall deadline.
        executor.shutdown(wait=False, cancel_futures=True)
