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
    woocommerce_timeout_seconds: int = Field(default=30, validation_alias=AliasChoices("WOOCOMMERCE_TIMEOUT_SECONDS", "woocommerce_timeout_seconds"))
    woocommerce_page_size: int = Field(default=100, validation_alias=AliasChoices("WOOCOMMERCE_PAGE_SIZE", "woocommerce_page_size"))
    woocommerce_order_sync_page_size: int = Field(default=100, validation_alias=AliasChoices("WOOCOMMERCE_ORDER_SYNC_PAGE_SIZE", "woocommerce_order_sync_page_size"))
    woocommerce_order_sync_default_statuses: str = Field(default="processing,on-hold", validation_alias=AliasChoices("WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES", "woocommerce_order_sync_default_statuses"))
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
