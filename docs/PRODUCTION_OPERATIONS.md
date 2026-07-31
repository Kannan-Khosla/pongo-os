# Production operations

## Stock authority

Pongo OS is the production stock authority. Production stock writes remain blocked unless `WOOCOMMERCE_PRODUCTION_STOCK_AUTHORITY=pongo`, writeback and stock/order-status permissions are enabled, and dry-run is off. Product metadata, customers, coupons, refunds, and deletes remain blocked.

## Staff access

Set `AUTH_REQUIRED=true`. Every production registration, including the first,
requires `REGISTRATION_ENABLED=true` and the backend-only
`REGISTRATION_ACCESS_CODE`. Registration creates equal-access staff accounts;
RBAC is intentionally out of scope. Use HTTPS so the secure, HttpOnly session
cookie is never sent over plaintext transport.

## Release migration and recovery

1. Put workers into maintenance mode and stop background jobs.
2. Create a custom PostgreSQL backup: `make backup-postgres BACKUP=/secure/path/pongo-before-release.dump`.
3. Verify the backup against a disposable database whose name ends in `_restore_verify`: `RESTORE_VERIFY_DATABASE_URL=... make verify-postgres-backup BACKUP=/secure/path/pongo-before-release.dump`.
4. Run `alembic upgrade head` (expected revision `20260731_0027`), then `/ready` and the release smoke tests.
5. If a migration fails, stop the release and restore the verified pre-release backup. Do not improvise a production downgrade; migration downgrades are validated for development recovery, while the database backup is the production rollback boundary.

Keep encrypted backups outside the application host, apply a retention policy, and run a restore verification at least monthly and before every schema release.

## Readiness and alerts

- `/health` is the process liveness check.
- `/ready` returns HTTP 503 until the schema, login, inventory data, Woo webhook/reconciliation, production stock authority, CORS, and writeback guard are ready.
- Set `OPERATIONS_ALERT_WEBHOOK_URL` to a private incident webhook. Pongo sends one alert after the configured number of consecutive server reconciliation failures.
- Application request logs are JSON and include a request ID, method, path, status, and duration. Request bodies, credentials, and query strings are not logged.
