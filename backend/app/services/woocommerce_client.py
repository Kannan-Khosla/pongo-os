from dataclasses import dataclass
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)
ALLOWED_WRITE_OPERATIONS = {"update_product_stock", "update_variation_stock", "update_order_status"}
ALLOWED_WRITE_METHODS = {"PUT", "PATCH"}
ALLOWED_STOCK_PAYLOAD_FIELDS = {"stock_quantity", "stock_status", "manage_stock"}
ALLOWED_ORDER_STATUS_PAYLOAD_FIELDS = {"status"}


@dataclass
class WooCommerceClientError(Exception):
    message: str
    status_code: int | None = None


class WooCommerceClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.woocommerce_base_url.rstrip("/")
        self.consumer_key = settings.woocommerce_consumer_key
        self.consumer_secret = settings.woocommerce_consumer_secret
        self.app_environment = getattr(settings, "app_env", "development").strip().casefold()
        self.environment = getattr(settings, "woocommerce_environment", "development")
        self.read_only = getattr(settings, "woocommerce_read_only", True)
        self.read_enabled = getattr(settings, "woocommerce_read_enabled", True)
        self.writeback_enabled = getattr(settings, "woocommerce_writeback_enabled", False)
        self.writeback_dry_run = getattr(settings, "woocommerce_writeback_dry_run", True)
        self.staging_live_test_mode = getattr(settings, "woocommerce_staging_live_test_mode", False)
        self.allow_stock_write = getattr(settings, "woocommerce_allow_stock_write", False)
        self.production_stock_authority = getattr(settings, "woocommerce_production_stock_authority", "disabled").strip().casefold()
        self.allow_order_status_write = getattr(settings, "woocommerce_allow_order_status_write", False)
        self.allow_delete = getattr(settings, "woocommerce_allow_delete", False)
        self.allowed_host = getattr(settings, "woocommerce_allowed_host", "").strip().lower()
        self.timeout_seconds = settings.woocommerce_timeout_seconds
        self.page_size = settings.woocommerce_page_size
        self.order_page_size = settings.woocommerce_order_sync_page_size
        self.last_response_headers: dict[str, str] = {}

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.consumer_key and self.consumer_secret)

    @property
    def base_url_host(self) -> str | None:
        return urlparse(self.base_url).hostname

    def validate_host(self, require_allowed_host: bool = False) -> None:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        local_http = parsed.scheme == "http" and host in {"localhost", "127.0.0.1"} and self.app_environment in {"development", "test", "e2e"}
        if parsed.scheme != "https" and not local_http:
            raise WooCommerceClientError("WooCommerce connections must use HTTPS.")
        if not host or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise WooCommerceClientError("WooCommerce base URL must be a canonical store origin without credentials, a path, query, or fragment.")
        if require_allowed_host and not self.allowed_host:
            raise WooCommerceClientError("WooCommerce allowed host is not configured.")
        if self.allowed_host and host != self.allowed_host:
            raise WooCommerceClientError("WooCommerce base URL host does not match the allowed host.")

    def list_products(self, page: int = 1, per_page: int | None = None, statuses: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "per_page": per_page or self.page_size}
        if statuses:
            params["status"] = ",".join(statuses)
        return self._get("/wp-json/wc/v3/products", params)

    def list_product_variations(self, product_id: int, page: int = 1, per_page: int | None = None) -> list[dict[str, Any]]:
        return self._get(f"/wp-json/wc/v3/products/{product_id}/variations", {"page": page, "per_page": per_page or self.page_size})

    def fetch_sellable_product_batch(self, page: int, per_page: int, statuses: list[str] | None = None) -> tuple[list[dict[str, Any]], bool]:
        products = self.list_products(page=page, per_page=per_page, statuses=statuses)
        records: list[dict[str, Any]] = []
        for product in products:
            if product.get("type") != "variable":
                records.append({"product": product, "variation": None})
                continue
            records.append({"product": product, "variation": None, "parent_container": True})
            variation_page = 1
            while True:
                variations = self.list_product_variations(product["id"], page=variation_page, per_page=self.page_size)
                records.extend({"product": product, "variation": variation} for variation in variations)
                if len(variations) < self.page_size:
                    break
                variation_page += 1
        return records, len(products) == per_page

    def fetch_all_sellable_products_and_variations(self, statuses: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 1
        per_page = self.page_size
        while True:
            batch, has_more = self.fetch_sellable_product_batch(page, per_page, statuses)
            records.extend(batch[: max(limit - len(records), 0)] if limit else batch)
            if limit and len(records) >= limit:
                return records
            if not has_more:
                break
            page += 1
        return records

    def list_orders(
        self,
        page: int = 1,
        per_page: int | None = None,
        status: str | None = None,
        after: str | None = None,
        before: str | None = None,
        modified_after: str | None = None,
        modified_before: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "per_page": per_page or self.order_page_size, "orderby": "date", "order": "desc"}
        if status:
            params["status"] = status
        if after:
            params["after"] = after
        if before:
            params["before"] = before
        if modified_after:
            params["modified_after"] = modified_after
        if modified_before:
            params["modified_before"] = modified_before
        return self._get("/wp-json/wc/v3/orders", params)

    def list_subscriptions(
        self,
        page: int = 1,
        per_page: int | None = None,
        status: str = "active",
    ) -> list[dict[str, Any]]:
        return self._get(
            "/wp-json/wc/v3/subscriptions",
            {"page": page, "per_page": min(per_page or self.page_size, 100), "status": status},
        )

    def fetch_all_orders(
        self,
        statuses: list[str] | None = None,
        limit: int | None = None,
        after: str | None = None,
        before: str | None = None,
        modified_after: str | None = None,
        modified_before: str | None = None,
    ) -> list[dict[str, Any]]:
        orders: list[dict[str, Any]] = []
        per_page = self.order_page_size
        for status in statuses or ["processing", "on-hold"]:
            page = 1
            while True:
                page_orders = self.list_orders(page=page, per_page=per_page, status=status, after=after, before=before, modified_after=modified_after, modified_before=modified_before)
                if not page_orders:
                    break
                orders.extend(page_orders)
                if limit and len(orders) >= limit:
                    return orders[:limit]
                if len(page_orders) < per_page:
                    break
                page += 1
        return orders

    def analytics_stats(self, report: str, *, after: str, before: str, interval: str = "day") -> dict[str, Any]:
        if report not in {"orders", "revenue"} or interval not in {"day", "week"}:
            raise ValueError("Unsupported WooCommerce analytics report.")
        result: dict[str, Any] | None = None
        intervals: dict[str, dict[str, Any]] = {}
        page = 1
        while True:
            data = self._request(
                "GET",
                f"/wp-json/wc-analytics/reports/{report}/stats",
                params={
                    "after": f"{after}T00:00:00",
                    "before": f"{before}T23:59:59",
                    "interval": interval,
                    "order": "asc",
                    "page": page,
                    "per_page": 100,
                },
            )
            if not isinstance(data, dict) or not isinstance(data.get("totals"), dict):
                raise WooCommerceClientError("WooCommerce Analytics returned an unexpected response shape.")
            result = result or {**data, "intervals": []}
            batch = data.get("intervals") or []
            if not isinstance(batch, list):
                raise WooCommerceClientError("WooCommerce Analytics returned an unexpected response shape.")
            before_count = len(intervals)
            for row in batch:
                if isinstance(row, dict):
                    intervals[str(row.get("interval") or row.get("date_start") or len(intervals))] = row
            if len(batch) < 100 or len(intervals) == before_count:
                break
            page += 1
        if result is None:
            raise WooCommerceClientError("WooCommerce Analytics returned no data.")
        result["intervals"] = list(intervals.values())
        return result

    def check_connection(self) -> None:
        self.list_products(page=1, per_page=1)
        self.list_orders(page=1, per_page=1, status="processing")

    def guarded_write(self, operation_type: str, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        method = method.upper()
        self.assert_woo_write_allowed(operation_type, method, path, payload, validate_payload=False)
        payload = sanitized_write_payload(operation_type, payload)
        self.assert_woo_write_allowed(operation_type, method, path, payload)
        data = self._request(method, path, payload=payload)
        if not isinstance(data, dict):
            raise WooCommerceClientError("WooCommerce write returned an unexpected response shape.")
        return data

    def validate_write_guard(self, operation_type: str, method: str, path: str) -> None:
        self.assert_woo_write_allowed(operation_type, method, path, {}, validate_payload=False)

    def assert_woo_write_allowed(self, operation_type: str, method: str, path: str, payload: dict[str, Any], validate_payload: bool = True) -> None:
        if method == "DELETE":
            raise WooCommerceClientError("WooCommerce DELETE is blocked.")
        if self.allow_delete:
            raise WooCommerceClientError("WooCommerce DELETE remains blocked even if allow-delete is configured.")
        if method not in ALLOWED_WRITE_METHODS:
            raise WooCommerceClientError("WooCommerce write method is not allowlisted.")
        if operation_type not in ALLOWED_WRITE_OPERATIONS:
            raise WooCommerceClientError("WooCommerce write operation is not allowlisted.")
        if self.environment not in {"staging", "production"}:
            raise WooCommerceClientError("WooCommerce writeback is blocked outside staging and production.")
        if self.app_environment == "production" and self.environment != "production":
            raise WooCommerceClientError("APP_ENV=production requires WOOCOMMERCE_ENVIRONMENT=production before any WooCommerce write.")
        production_write = self.app_environment == "production" or self.environment == "production"
        if production_write:
            stock_write = operation_type in {"update_product_stock", "update_variation_stock"}
            order_completion = operation_type == "update_order_status" and method == "PUT"
            if stock_write and self.production_stock_authority != "pongo":
                raise WooCommerceClientError("Production stock writeback requires WOOCOMMERCE_PRODUCTION_STOCK_AUTHORITY=pongo.")
            if not stock_write and not order_completion:
                raise WooCommerceClientError("Production WooCommerce writes are limited to explicit Pongo stock authority and completed order status updates.")
        if not production_write and self.environment == "staging" and not self.staging_live_test_mode:
            raise WooCommerceClientError("WooCommerce live staging test mode is disabled.")
        if self.read_only:
            raise WooCommerceClientError("WooCommerce read-only mode is enabled; writeback is blocked.")
        if not self.writeback_enabled:
            raise WooCommerceClientError("WooCommerce writeback is disabled.")
        if self.writeback_dry_run:
            raise WooCommerceClientError("WooCommerce writeback dry-run is enabled; live send is blocked.")
        self.validate_host(require_allowed_host=True)
        if operation_type == "update_product_stock" and (not self.allow_stock_write or not is_simple_product_stock_write_path(path)):
            raise WooCommerceClientError("WooCommerce product stock write path is not allowlisted.")
        if operation_type == "update_variation_stock" and (not self.allow_stock_write or not is_variation_stock_write_path(path)):
            raise WooCommerceClientError("WooCommerce variation stock write path is not allowlisted.")
        if operation_type == "update_order_status" and (not self.allow_order_status_write or not is_order_status_write_path(path)):
            raise WooCommerceClientError("WooCommerce order status write path is not allowlisted.")
        if validate_payload:
            validate_payload_fields(operation_type, payload)
            if production_write and operation_type == "update_order_status" and payload.get("status") not in {"completed", "cancelled"}:
                raise WooCommerceClientError("Production WooCommerce order writeback may only set status to completed or cancelled.")

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        data = self._request("GET", path, params=params)
        if not isinstance(data, list):
            raise WooCommerceClientError("WooCommerce API returned an unexpected response shape.")
        return data

    def _get_one(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._request("GET", path, params=params or {})
        if not isinstance(data, dict):
            raise WooCommerceClientError("WooCommerce API returned an unexpected response shape.")
        return data

    def get_product(self, product_id: int) -> dict[str, Any]:
        return self._get_one(f"/wp-json/wc/v3/products/{product_id}")

    def get_product_variation(self, product_id: int, variation_id: int) -> dict[str, Any]:
        return self._get_one(f"/wp-json/wc/v3/products/{product_id}/variations/{variation_id}")

    def get_order(self, order_id: int) -> dict[str, Any]:
        return self._get_one(f"/wp-json/wc/v3/orders/{order_id}")

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
        if not self.configured:
            raise WooCommerceClientError("WooCommerce credentials are not configured.")
        method = method.upper()
        if method == "DELETE":
            raise WooCommerceClientError("WooCommerce DELETE is blocked.")
        if method == "GET" and not self.read_enabled:
            raise WooCommerceClientError("WooCommerce read access is disabled.")
        self.validate_host()
        url = f"{self.base_url}{path}"
        safe_params = dict(params or {})
        auth = httpx.BasicAuth(self.consumer_key, self.consumer_secret)
        retry_statuses = {429, 500, 502, 503, 504}
        last_status_code = None
        for attempt in range(1, 4):
            started_at = time.perf_counter()
            response = None
            try:
                response = httpx.request(method, url, params=safe_params, json=payload, auth=auth, timeout=self.timeout_seconds)
                last_status_code = response.status_code
                if response.status_code in retry_statuses and attempt < 3:
                    time.sleep(0.2 * attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                self.last_response_headers = dict(response.headers)
                return data
            except httpx.TimeoutException as exc:
                if attempt < 3:
                    time.sleep(0.2 * attempt)
                    continue
                raise WooCommerceClientError("WooCommerce request timed out.") from exc
            except httpx.HTTPStatusError as exc:
                raise WooCommerceClientError(safe_woocommerce_error_message(exc.response), status_code=exc.response.status_code) from exc
            except httpx.HTTPError as exc:
                if attempt < 3:
                    time.sleep(0.2 * attempt)
                    continue
                raise WooCommerceClientError("WooCommerce API request failed.") from exc
            except ValueError as exc:
                raise WooCommerceClientError("WooCommerce API returned invalid JSON.") from exc
            finally:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                status_code = response.status_code if response is not None else last_status_code
                record_count = None
                if response is not None and response.headers.get("content-type", "").startswith("application/json"):
                    try:
                        response_data = response.json()
                        record_count = len(response_data) if isinstance(response_data, list) else None
                    except ValueError:
                        record_count = None
                logger.info("WooCommerce API %s %s status=%s duration_ms=%s record_count=%s", method, path, status_code, duration_ms, record_count)
        raise WooCommerceClientError("WooCommerce API request failed.")


def safe_woocommerce_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "WooCommerce API returned an error."
    code = str(payload.get("code") or "").strip()
    message = str(payload.get("message") or "").strip()
    if code == "woocommerce_rest_authentication_error" and "write permissions" in message.lower():
        return "WooCommerce API key does not have write permissions. Change the key permission to Read/Write in WooCommerce."
    if message:
        return f"WooCommerce API error: {message[:300]}"
    return "WooCommerce API returned an error."


def is_simple_product_stock_write_path(path: str) -> bool:
    parts = [part for part in path.strip("/").split("/") if part]
    return len(parts) == 5 and parts[:4] == ["wp-json", "wc", "v3", "products"] and parts[4].isdigit()


def is_variation_stock_write_path(path: str) -> bool:
    parts = [part for part in path.strip("/").split("/") if part]
    return len(parts) == 7 and parts[:4] == ["wp-json", "wc", "v3", "products"] and parts[4].isdigit() and parts[5] == "variations" and parts[6].isdigit()


def is_order_status_write_path(path: str) -> bool:
    parts = [part for part in path.strip("/").split("/") if part]
    return len(parts) == 5 and parts[:4] == ["wp-json", "wc", "v3", "orders"] and parts[4].isdigit()


def sanitized_write_payload(operation_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload_fields(operation_type, payload)
    if operation_type in {"update_product_stock", "update_variation_stock"}:
        return {key: payload[key] for key in ALLOWED_STOCK_PAYLOAD_FIELDS if key in payload}
    if operation_type == "update_order_status":
        return {"status": payload["status"]}
    return {}


def validate_payload_fields(operation_type: str, payload: dict[str, Any]) -> None:
    fields = set(payload)
    if operation_type in {"update_product_stock", "update_variation_stock"}:
        if not fields or not fields.issubset(ALLOWED_STOCK_PAYLOAD_FIELDS):
            raise WooCommerceClientError("WooCommerce stock write payload contains non-allowlisted fields.")
        return
    if operation_type == "update_order_status":
        if fields != ALLOWED_ORDER_STATUS_PAYLOAD_FIELDS:
            raise WooCommerceClientError("WooCommerce order status payload must contain only status.")
        return
    raise WooCommerceClientError("WooCommerce write operation is not allowlisted.")
