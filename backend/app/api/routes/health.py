from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.auth import User
from app.models.inventory import InventoryItem, InventoryItemLocation
from app.models.orders import Order, OrderItem
from app.schemas.health import HealthResponse, ReadinessCheck, ReadinessResponse
from app.services.woocommerce_client import WooCommerceClient, WooCommerceClientError
from app.services.woocommerce_access import effective_woocommerce_settings
from app.services.woocommerce_order_reconciliation import order_worker_is_recent, reconciliation_health
from app.services.woocommerce_webhooks import webhook_is_configured
from app.services.woocommerce_stock_sync_jobs import stock_sync_worker_health, unresolved_stock_sync_job_count
from app.services.order_workflow import operational_order_clause

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="pongo-inventory-os")


@router.get("/ready", response_model=ReadinessResponse)
def readiness_check(db: Session = Depends(get_db)) -> ReadinessResponse | JSONResponse:
    settings = get_settings()
    checks: list[ReadinessCheck] = []
    db.scalar(select(1))
    checks.append(ReadinessCheck(name="database", ready=True, message=f"Connected to {db.get_bind().dialect.name}."))

    try:
        revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        db.rollback()
        revision = None
    checks.append(ReadinessCheck(name="migrations", ready=revision == "20260805_0033", message=f"Schema revision: {revision or 'missing'}; expected 20260805_0033."))

    user_count = int(db.scalar(select(func.count(User.id)).where(User.active.is_(True))) or 0)
    checks.append(ReadinessCheck(name="login", ready=not settings.auth_required or user_count > 0, count=user_count, message="At least one login exists." if user_count else "Create the first production login."))

    active_items = InventoryItem.active.is_(True) & InventoryItem.non_inventory.is_not(True)
    missing_costs = int(db.scalar(select(func.count(InventoryItem.id)).where(active_items, (InventoryItem.unit_cost.is_(None)) | (InventoryItem.unit_cost <= 0))) or 0)
    duplicate_skus = duplicate_value_count(db, InventoryItem.sku)
    duplicate_barcodes = duplicate_value_count(db, InventoryItem.barcode)
    locationless_items = int(
        db.scalar(
            select(func.count(InventoryItem.id)).where(
                active_items,
                ~InventoryItem.locations.any(InventoryItemLocation.active.is_(True)),
            )
        )
        or 0
    )
    unmatched_lines = int(db.scalar(
        select(func.count(OrderItem.id)).join(Order, Order.id == OrderItem.order_id).where(
            OrderItem.inventory_item_id.is_(None),
            OrderItem.quantity_ordered > 0,
            operational_order_clause(),
        )
    ) or 0)
    checks.extend([
        ReadinessCheck(name="inventory_costs", ready=missing_costs == 0, count=missing_costs, message="Active stock items missing a positive unit cost."),
        ReadinessCheck(name="duplicate_skus", ready=duplicate_skus == 0, count=duplicate_skus, message="Duplicate non-empty SKU groups."),
        ReadinessCheck(name="duplicate_barcodes", ready=duplicate_barcodes == 0, count=duplicate_barcodes, message="Duplicate non-empty barcode groups."),
        ReadinessCheck(name="inventory_locations", ready=locationless_items == 0, count=locationless_items, message="Active inventory items without an active location row."),
        ReadinessCheck(name="unmatched_order_lines", ready=unmatched_lines == 0, count=unmatched_lines, message="Active Woo order lines without an inventory match."),
    ])

    if settings.app_env.casefold() == "production":
        worker_running = order_worker_is_recent(db, settings)
        checks.extend(production_checks(settings, db.get_bind().dialect.name, db, worker_running, worker_running))

    response = ReadinessResponse(
        status="ready" if all(check.ready for check in checks) else "not_ready",
        service="pongo-inventory-os",
        environment=settings.app_env,
        checks=checks,
    )
    return response if response.status == "ready" else JSONResponse(status_code=503, content=response.model_dump(mode="json"))


def duplicate_value_count(db: Session, column) -> int:
    normalized = func.lower(func.trim(column))
    groups = select(normalized).where(column.is_not(None), func.trim(column) != "").group_by(normalized).having(func.count(InventoryItem.id) > 1).subquery()
    return int(db.scalar(select(func.count()).select_from(groups)) or 0)


def production_checks(settings, dialect: str, db: Session, reconciliation_running: bool, stock_worker_running: bool) -> list[ReadinessCheck]:
    settings = effective_woocommerce_settings(db, settings)
    woo_client = WooCommerceClient(settings)
    woo_host_matches = bool(woo_client.allowed_host and woo_client.base_url_host and woo_client.allowed_host == woo_client.base_url_host.lower())
    woo_url_is_https = urlparse(woo_client.base_url).scheme == "https"
    cors_safe = bool(settings.cors_origins) and all(production_origin_is_safe(origin) for origin in settings.cors_origins)
    stock_guard_error = write_guard_error(woo_client, "update_product_stock", "PATCH", "/wp-json/wc/v3/products/1")
    order_guard_error = write_guard_error(woo_client, "update_order_status", "PUT", "/wp-json/wc/v3/orders/1")
    reconciliation = reconciliation_health(db, settings, running=reconciliation_running)
    alert_url = urlparse(settings.operations_alert_webhook_url)
    alerts_ready = alert_url.scheme == "https" and bool(alert_url.netloc)
    stock_worker = stock_sync_worker_health(settings, running=stock_worker_running, external_heartbeat=stock_worker_running)
    unresolved_stock_jobs = unresolved_stock_sync_job_count(db)
    return [
        ReadinessCheck(name="postgresql", ready=dialect == "postgresql", message="Production must use PostgreSQL."),
        ReadinessCheck(name="authentication", ready=settings.auth_required, message="Authentication must remain enabled in production."),
        ReadinessCheck(name="registration", ready=not settings.registration_enabled or len(settings.registration_access_code.encode()) >= 32, message="Disable registration or configure an access code of at least 32 bytes after bootstrap."),
        ReadinessCheck(name="cors", ready=cors_safe, message="Production CORS origins must be explicit HTTPS origins without wildcards or localhost."),
        ReadinessCheck(name="alerts", ready=alerts_ready, message="Configure an HTTPS operations alert webhook."),
        ReadinessCheck(name="woo_credentials", ready=woo_client.configured and woo_url_is_https and woo_host_matches and settings.woocommerce_environment == "production", message="WooCommerce needs HTTPS credentials, an exact allowed-host match, and production environment mode."),
        ReadinessCheck(name="woo_webhook", ready=webhook_is_configured(settings), message="Signed WooCommerce order webhooks need an allowed host and a secret of at least 32 bytes."),
        ReadinessCheck(name="woo_reconciliation", ready=reconciliation["healthy"], message=reconciliation["message"]),
        ReadinessCheck(name="woo_stock_worker", ready=stock_worker["healthy"] and unresolved_stock_jobs == 0, count=unresolved_stock_jobs, message=stock_worker["message"] if unresolved_stock_jobs == 0 else f"{unresolved_stock_jobs} Woo stock-sync job(s) have unresolved failures and need review."),
        ReadinessCheck(name="woo_stock_authority", ready=settings.woocommerce_production_stock_authority == "pongo", message="Pongo OS is the selected production stock authority."),
        ReadinessCheck(name="woo_writeback", ready=not stock_guard_error and not order_guard_error, message=stock_guard_error or order_guard_error or "Effective production stock and order write guards passed."),
    ]


def production_origin_is_safe(origin: str) -> bool:
    parsed = urlparse(origin)
    return bool(
        parsed.scheme == "https"
        and parsed.netloc
        and "*" not in parsed.netloc
        and parsed.hostname not in {"localhost", "127.0.0.1"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    )


def write_guard_error(client: WooCommerceClient, operation: str, method: str, path: str) -> str | None:
    try:
        client.validate_write_guard(operation, method, path)
    except WooCommerceClientError as error:
        return error.message
    return None
