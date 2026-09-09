"""Start an isolated local planning workspace against a fresh disposable database."""
import os
from pathlib import Path
import sys
import tempfile

repository = Path(__file__).resolve().parents[2]
runtime = Path(tempfile.mkdtemp(prefix='pongo-smart-buying-', dir='/tmp'))
os.chdir(runtime)
for key in list(os.environ):
    if key.upper().startswith(('WOOCOMMERCE_', 'GOOGLE_REPORTS_', 'SMTP_', 'MAP_', 'ROUTE_', 'OPERATIONS_ALERT_', 'REGISTRATION_', 'AUTH_', 'DATABASE_URL', 'APP_ENV', 'PONGO_TEST_POSTGRES_URL')):
        os.environ.pop(key)
os.environ.update({
    'DATABASE_URL': f'sqlite:///{runtime / "planning.db"}',
    'APP_ENV': 'development',
    'AUTH_REQUIRED': 'false',
    'REGISTRATION_ENABLED': 'false',
    'BACKEND_CORS_ORIGINS': 'http://127.0.0.1:5173,http://localhost:5173',
    'WOOCOMMERCE_READ_ENABLED': 'false',
    'WOOCOMMERCE_READ_ONLY': 'true',
    'WOOCOMMERCE_WRITEBACK_ENABLED': 'false',
    'WOOCOMMERCE_WRITEBACK_DRY_RUN': 'true',
    'WOOCOMMERCE_ORDER_RECONCILIATION_ENABLED': 'false',
    'WOOCOMMERCE_STOCK_SYNC_JOBS_ENABLED': 'false',
    'WOOCOMMERCE_DAILY_FULL_STOCK_SYNC_ENABLED': 'false',
    'WOOCOMMERCE_WEBHOOK_ENABLED': 'false',
})
sys.path.insert(0, str(repository / 'backend'))
from app.core.config import get_settings
settings = get_settings()
if settings.auth_required or settings.app_env != 'development':
    raise RuntimeError('The local launcher requires an isolated development environment.')
if any((settings.woocommerce_base_url, settings.woocommerce_consumer_key,
    settings.woocommerce_consumer_secret, settings.google_reports_client_secret,
    settings.google_reports_refresh_token, settings.smtp_host, settings.map_api_key,
    settings.operations_alert_webhook_url)):
    raise RuntimeError('External integration credentials must be empty for the local workspace.')
if any((settings.woocommerce_read_enabled, settings.woocommerce_writeback_enabled,
    settings.woocommerce_order_reconciliation_enabled, settings.woocommerce_stock_sync_jobs_enabled,
    settings.woocommerce_daily_full_stock_sync_enabled, settings.woocommerce_webhook_enabled)):
    raise RuntimeError('External integrations must be disabled for the local workspace.')

from alembic import command
from alembic.config import Config
config = Config(str(repository / 'backend/alembic.ini'))
config.set_main_option('script_location', str(repository / 'backend/alembic'))
command.upgrade(config, 'head')
print(f'Local runtime: {runtime}; external integrations disabled.', flush=True)

import uvicorn
uvicorn.run('app.main:app', host='127.0.0.1', port=8000, access_log=False)
