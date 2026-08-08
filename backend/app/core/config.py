from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/pongo_inventory_os",
        validation_alias=AliasChoices("DATABASE_URL", "database_url"),
    )
    app_env: Literal["development", "test", "e2e", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "app_env"),
    )
    auth_required: bool = Field(default=True, validation_alias=AliasChoices("AUTH_REQUIRED", "auth_required"))
    auth_cookie_name: str = Field(default="pongo_session", validation_alias=AliasChoices("AUTH_COOKIE_NAME", "auth_cookie_name"))
    auth_session_hours: int = Field(default=336, ge=1, le=2160, validation_alias=AliasChoices("AUTH_SESSION_HOURS", "auth_session_hours"))
    auth_max_failed_logins: int = Field(default=5, ge=3, le=20, validation_alias=AliasChoices("AUTH_MAX_FAILED_LOGINS", "auth_max_failed_logins"))
    auth_lockout_minutes: int = Field(default=15, ge=1, le=1440, validation_alias=AliasChoices("AUTH_LOCKOUT_MINUTES", "auth_lockout_minutes"))
    registration_enabled: bool = Field(default=True, validation_alias=AliasChoices("REGISTRATION_ENABLED", "registration_enabled"))
    registration_access_code: str = Field(default="", validation_alias=AliasChoices("REGISTRATION_ACCESS_CODE", "registration_access_code"))
    item_import_max_bytes: int = Field(default=10_485_760, ge=1_024, le=104_857_600, validation_alias=AliasChoices("ITEM_IMPORT_MAX_BYTES", "item_import_max_bytes"))
    item_import_preview_ttl_hours: int = Field(default=24, ge=1, le=168, validation_alias=AliasChoices("ITEM_IMPORT_PREVIEW_TTL_HOURS", "item_import_preview_ttl_hours"))
    operations_alert_webhook_url: str = Field(default="", validation_alias=AliasChoices("OPERATIONS_ALERT_WEBHOOK_URL", "operations_alert_webhook_url"))
    operations_alert_failure_threshold: int = Field(default=3, ge=1, le=100, validation_alias=AliasChoices("OPERATIONS_ALERT_FAILURE_THRESHOLD", "operations_alert_failure_threshold"))
    backend_cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        validation_alias=AliasChoices("BACKEND_CORS_ORIGINS", "backend_cors_origins"),
    )
    woocommerce_base_url: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_BASE_URL", "woocommerce_base_url"))
    woocommerce_consumer_key: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_CONSUMER_KEY", "woocommerce_consumer_key"))
    woocommerce_consumer_secret: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_CONSUMER_SECRET", "woocommerce_consumer_secret"))
    woocommerce_configuration_encryption_key: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_CONFIGURATION_ENCRYPTION_KEY", "woocommerce_configuration_encryption_key"))
    woocommerce_environment: str = Field(default="development", validation_alias=AliasChoices("WOOCOMMERCE_ENVIRONMENT", "woocommerce_environment"))
    woocommerce_read_enabled: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_READ_ENABLED", "woocommerce_read_enabled"))
    woocommerce_read_only: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_READ_ONLY", "woocommerce_read_only"))
    woocommerce_writeback_enabled: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_WRITEBACK_ENABLED", "woocommerce_writeback_enabled"))
    woocommerce_writeback_dry_run: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_WRITEBACK_DRY_RUN", "woocommerce_writeback_dry_run"))
    woocommerce_staging_live_test_mode: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_STAGING_LIVE_TEST_MODE", "woocommerce_staging_live_test_mode"))
    woocommerce_allow_stock_write: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_ALLOW_STOCK_WRITE", "woocommerce_allow_stock_write"))
    woocommerce_production_stock_authority: str = Field(default="disabled", validation_alias=AliasChoices("WOOCOMMERCE_PRODUCTION_STOCK_AUTHORITY", "woocommerce_production_stock_authority"))
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
    woocommerce_order_reconciliation_enabled: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_ORDER_RECONCILIATION_ENABLED", "woocommerce_order_reconciliation_enabled"))
    woocommerce_order_reconciliation_interval_seconds: int = Field(default=120, ge=15, le=3600, validation_alias=AliasChoices("WOOCOMMERCE_ORDER_RECONCILIATION_INTERVAL_SECONDS", "woocommerce_order_reconciliation_interval_seconds"))
    woocommerce_order_reconciliation_stale_after_seconds: int = Field(default=300, ge=60, le=86400, validation_alias=AliasChoices("WOOCOMMERCE_ORDER_RECONCILIATION_STALE_AFTER_SECONDS", "woocommerce_order_reconciliation_stale_after_seconds"))
    woocommerce_order_reconciliation_lookback_hours: int = Field(default=168, ge=1, le=2160, validation_alias=AliasChoices("WOOCOMMERCE_ORDER_RECONCILIATION_LOOKBACK_HOURS", "woocommerce_order_reconciliation_lookback_hours"))
    woocommerce_order_reconciliation_statuses: str = Field(default="processing,on-hold,pending,completed,failed,cancelled,refunded", validation_alias=AliasChoices("WOOCOMMERCE_ORDER_RECONCILIATION_STATUSES", "woocommerce_order_reconciliation_statuses"))
    woocommerce_sync_error_retention_days: int = Field(default=90, ge=7, le=3650, validation_alias=AliasChoices("WOOCOMMERCE_SYNC_ERROR_RETENTION_DAYS", "woocommerce_sync_error_retention_days"))
    woocommerce_stock_sync_jobs_enabled: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_STOCK_SYNC_JOBS_ENABLED", "woocommerce_stock_sync_jobs_enabled"))
    woocommerce_stock_sync_job_interval_seconds: int = Field(default=3, ge=1, le=300, validation_alias=AliasChoices("WOOCOMMERCE_STOCK_SYNC_JOB_INTERVAL_SECONDS", "woocommerce_stock_sync_job_interval_seconds"))
    woocommerce_stock_sync_job_stale_seconds: int = Field(default=900, ge=30, le=86400, validation_alias=AliasChoices("WOOCOMMERCE_STOCK_SYNC_JOB_STALE_SECONDS", "woocommerce_stock_sync_job_stale_seconds"))
    woocommerce_stock_sync_max_retries: int = Field(default=3, ge=0, le=10, validation_alias=AliasChoices("WOOCOMMERCE_STOCK_SYNC_MAX_RETRIES", "woocommerce_stock_sync_max_retries"))
    woocommerce_daily_full_stock_sync_enabled: bool = Field(default=True, validation_alias=AliasChoices("WOOCOMMERCE_DAILY_FULL_STOCK_SYNC_ENABLED", "woocommerce_daily_full_stock_sync_enabled"))
    admin_timezone: str = Field(default="America/Edmonton", validation_alias=AliasChoices("ADMIN_TIMEZONE", "admin_timezone"))
    woocommerce_webhook_enabled: bool = Field(default=False, validation_alias=AliasChoices("WOOCOMMERCE_WEBHOOK_ENABLED", "woocommerce_webhook_enabled"))
    woocommerce_webhook_secret: str = Field(default="", validation_alias=AliasChoices("WOOCOMMERCE_WEBHOOK_SECRET", "woocommerce_webhook_secret"))
    woocommerce_webhook_max_body_bytes: int = Field(default=1_048_576, validation_alias=AliasChoices("WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES", "woocommerce_webhook_max_body_bytes"))
    map_provider: str = Field(default="", validation_alias=AliasChoices("MAP_PROVIDER", "map_provider"))
    map_api_key: str = Field(default="", validation_alias=AliasChoices("MAP_API_KEY", "map_api_key"))
    route_geo_provider: str = Field(default="disabled", validation_alias=AliasChoices("ROUTE_GEO_PROVIDER", "route_geo_provider"))
    route_map_provider: str = Field(default="disabled", validation_alias=AliasChoices("ROUTE_MAP_PROVIDER", "route_map_provider"))
    route_optimization_provider: str = Field(default="disabled", validation_alias=AliasChoices("ROUTE_OPTIMIZATION_PROVIDER", "route_optimization_provider"))
    google_reports_client_id: str = Field(default="", validation_alias=AliasChoices("GOOGLE_REPORTS_CLIENT_ID", "google_reports_client_id"))
    google_reports_client_secret: str = Field(default="", validation_alias=AliasChoices("GOOGLE_REPORTS_CLIENT_SECRET", "google_reports_client_secret"))
    google_reports_refresh_token: str = Field(default="", validation_alias=AliasChoices("GOOGLE_REPORTS_REFRESH_TOKEN", "google_reports_refresh_token"))
    google_reports_folder_id: str = Field(default="", validation_alias=AliasChoices("GOOGLE_REPORTS_FOLDER_ID", "google_reports_folder_id"))
    smtp_host: str = Field(default="", validation_alias=AliasChoices("SMTP_HOST", "smtp_host"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT", "smtp_port"))
    smtp_username: str = Field(default="", validation_alias=AliasChoices("SMTP_USERNAME", "smtp_username"))
    smtp_password: str = Field(default="", validation_alias=AliasChoices("SMTP_PASSWORD", "smtp_password"))
    smtp_from_email: str = Field(default="", validation_alias=AliasChoices("SMTP_FROM_EMAIL", "smtp_from_email"))
    smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("SMTP_USE_TLS", "smtp_use_tls"))

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def default_order_sync_statuses(self) -> list[str]:
        return [status.strip() for status in self.woocommerce_order_sync_default_statuses.split(",") if status.strip()]

    @property
    def order_reconciliation_statuses(self) -> list[str]:
        return [status.strip() for status in self.woocommerce_order_reconciliation_statuses.split(",") if status.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
