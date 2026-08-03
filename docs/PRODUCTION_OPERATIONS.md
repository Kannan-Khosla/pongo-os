# Production operations

## Stock authority

Pongo OS is the production stock authority. Settings → Connection exposes an audited access mode: **Read only** permits WooCommerce GET operations, while **Read & write** activates the existing queued stock and completed-order writeback workflows. Every mode change records the staff identity and timestamp in `woocommerce_access_mode_changes`. Product metadata, customer, coupon, refund, and delete workflows are not exposed by Pongo OS.

WooCommerce stock writeback uses local Sellable (`In Stock - Allocated`), not
physical In Stock, so inventory reserved by imported open/POS orders is not
made available to customers again.

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
4. Run `alembic upgrade head` (expected revision `20260803_0030`), then `/ready` and the release smoke tests.
5. If a migration fails, stop the release and restore the verified pre-release backup. Do not improvise a production downgrade; migration downgrades are validated for development recovery, while the database backup is the production rollback boundary.

Keep encrypted backups outside the application host, apply a retention policy, and run a restore verification at least monthly and before every schema release.

## Readiness and alerts

- `/health` is the process liveness check.
- `/ready` returns HTTP 503 until the schema, login, inventory data, Woo webhook/reconciliation, production stock authority, CORS, and writeback guard are ready.
- Set `OPERATIONS_ALERT_WEBHOOK_URL` to a private incident webhook. Pongo sends one alert after the configured number of consecutive server reconciliation failures.
- Application request logs are JSON and include a request ID, method, path, status, and duration. Request bodies, credentials, and query strings are not logged.

## Heroku deployment

Pongo OS deploys as one Heroku app. The Node.js buildpack builds
`frontend/dist`, the Python buildpack installs the FastAPI backend, the release
process runs `alembic upgrade head`, and the web process serves both the API and
the built frontend. A separate `worker` process runs two-minute WooCommerce
order reconciliation and resumable stock-sync jobs; it also queues the forced
daily catalog reconciliation after midnight in `ADMIN_TIMEZONE`. Do not run
schedulers in the web process. Keep `heroku/nodejs` first and `heroku/python` last. Attach
Heroku Postgres before the first release, set `APP_ENV=production`, and use the
app's exact HTTPS origin for `BACKEND_CORS_ORIGINS`.
