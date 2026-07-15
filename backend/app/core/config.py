from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/pongo_inventory_os",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    app_env: str = Field(default="development", validation_alias=AliasChoices("APP_ENV", "app_env"))
    backend_cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        validation_alias=AliasChoices("BACKEND_CORS_ORIGINS", "backend_cors_origins"),
    )
    woocommerce_base_url: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_BASE_URL", "woocommerce_base_url"))
    woocommerce_consumer_key: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_CONSUMER_KEY", "woocommerce_consumer_key"))
    woocommerce_consumer_secret: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_CONSUMER_SECRET", "woocommerce_consumer_secret"))
    woocommerce_environment: str = Field(default="development", validation_alias=AliasChoices("WOOCOMMERCE_ENVIRONMENT", "woocommerce_environment"))
    woocommerce_read_enabled: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_READ_ENABLED", "woocommerce_read_enabled"))
    woocommerce_read_only: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_READ_ONLY", "woocommerce_read_only"))
    woocommerce_writeback_enabled: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_WRITEBACK_ENABLED", "woocommerce_writeback_enabled"))
    woocommerce_writeback_dry_run: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_WRITEBACK_DRY_RUN", "woocommerce_writeback_dry_run"))
    woocommerce_staging_live_test_mode: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_STAGING_LIVE_TEST_MODE", "woocommerce_staging_live_test_mode"))
    woocommerce_allow_stock_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_STOCK_WRITE", "woocommerce_allow_stock_write"))
    woocommerce_allow_order_status_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_ORDER_STATUS_WRITE", "woocommerce_allow_order_status_write"))
    woocommerce_allow_product_metadata_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_PRODUCT_METADATA_WRITE", "woocommerce_allow_product_metadata_write"))
    woocommerce_allow_customer_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_CUSTOMER_WRITE", "woocommerce_allow_customer_write"))
    woocommerce_allow_coupon_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_COUPON_WRITE", "woocommerce_allow_coupon_write"))
    woocommerce_allow_refund_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_REFUND_WRITE", "woocommerce_allow_refund_write"))
    woocommerce_allow_delete: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_DELETE", "woocommerce_allow_delete"))
    woocommerce_allowed_host: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_ALLOWED_HOST", "woocommerce_allowed_host"))
    woocommerce_timeout_seconds: int = Field(default=30, validation_alias=AliasChoices("WOOCOMMERCE_TIMEOUT_SECONDS", "woocommerce_timeout_seconds"))
    woocommerce_page_size: int = Field(default=100, validation_alias=AliasChoices("WOOCOMMERCE_PAGE_SIZE", "woocommerce_page_size"))
    woocommerce_order_sync_page_size: int = Field(default=100, validation_alias=AliasChoices("WOOCOMMERCE_ORDER_SYNC_PAGE_SIZE", "woocommerce_order_sync_page_size"))
    woocommerce_order_sync_default_statuses: str = Field(default="processing,on-hold,pending", validation_alias=AliasChoices("WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES", "woocommerce_order_sync_default_statuses"))
    woocommerce_webhook_enabled: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_WEBHOOK_ENABLED", "woocommerce_webhook_enabled"))
    woocommerce_webhook_secret: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_WEBHOOK_SECRET", "woocommerce_webhook_secret"))
    woocommerce_webhook_max_body_bytes: int = Field(default=1_048_576, validation_alias=AliasChoices("WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES", "woocommerce_webhook_max_body_bytes"))
    map_provider: str = Field(default="", validation_alias=AliasChoices("MAP_PROVIDER", "map_provider"))
    map_api_key: str = Field(default="", validation_alias=AliasChoices("MAP_API_KEY", "map_api_key"))
    route_geo_provider: str = Field(default="disabled", validation_alias=AliasChoices("ROUTE_GEO_PROVIDER", "route_geo_provider"))
    route_map_provider: str = Field(default="disabled", validation_alias=AliasChoices("ROUTE_MAP_PROVIDER", "route_map_provider"))
    route_optimization_provider: str = Field(default="disabled", validation_alias=AliasChoices("ROUTE_OPTIMIZATION_PROVIDER", "route_optimization_provider"))

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def default_order_sync_statuses(self) -> list[str]:
        return [status.strip() for status in self.woocommerce_order_sync_default_statuses.split(",") if status.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
