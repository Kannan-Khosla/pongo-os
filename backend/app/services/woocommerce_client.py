from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings


@dataclass
class WooCommerceClientError(Exception):
    message: str
    status_code: int | None = None


class WooCommerceClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.woocommerce_base_url.rstrip("/")
        self.consumer_key = settings.woocommerce_consumer_key
        self.consumer_secret = settings.woocommerce_consumer_secret
        self.timeout_seconds = settings.woocommerce_timeout_seconds
        self.page_size = settings.woocommerce_page_size

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.consumer_key and self.consumer_secret)

    def list_products(self, page: int = 1, per_page: int | None = None, statuses: list[str] | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "per_page": per_page or self.page_size}
        if statuses:
            params["status"] = ",".join(statuses)
        return self._get("/wp-json/wc/v3/products", params)

    def list_product_variations(self, product_id: int, page: int = 1, per_page: int | None = None) -> list[dict[str, Any]]:
        return self._get(f"/wp-json/wc/v3/products/{product_id}/variations", {"page": page, "per_page": per_page or self.page_size})

    def fetch_all_sellable_products_and_variations(self, statuses: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        page = 1
        per_page = self.page_size
        while True:
            products = self.list_products(page=page, per_page=per_page, statuses=statuses)
            if not products:
                break
            for product in products:
                if product.get("type") == "variable":
                    variation_page = 1
                    while True:
                        variations = self.list_product_variations(product["id"], page=variation_page, per_page=per_page)
                        if not variations:
                            break
                        for variation in variations:
                            records.append({"product": product, "variation": variation})
                            if limit and len(records) >= limit:
                                return records
                        if len(variations) < per_page:
                            break
                        variation_page += 1
                else:
                    records.append({"product": product, "variation": None})
                    if limit and len(records) >= limit:
                        return records
            if len(products) < per_page:
                break
            page += 1
        return records

    def check_connection(self) -> None:
        self.list_products(page=1, per_page=1)

    def _get(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.configured:
            raise WooCommerceClientError("WooCommerce credentials are not configured.")
        url = f"{self.base_url}{path}"
        safe_params = {**params, "consumer_key": self.consumer_key, "consumer_secret": self.consumer_secret}
        try:
            response = httpx.get(url, params=safe_params, timeout=self.timeout_seconds)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise WooCommerceClientError("WooCommerce request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise WooCommerceClientError("WooCommerce API returned an error.", status_code=exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise WooCommerceClientError("WooCommerce API request failed.") from exc
        except ValueError as exc:
            raise WooCommerceClientError("WooCommerce API returned invalid JSON.") from exc
        if not isinstance(data, list):
            raise WooCommerceClientError("WooCommerce API returned an unexpected response shape.")
        return data
