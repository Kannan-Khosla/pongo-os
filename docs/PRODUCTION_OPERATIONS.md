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
3. Verify the backup against a disposable database whose name ends in `_restore_verify`: `RESTORE_VERIFY_DATABASE_URL=... make verify-postgres-backup BACKUP=/secure/path/pongo-before-release.dump`. For a schema release, run this verifier from the checkout matching the source database revision (the currently deployed release), because the candidate checkout correctly expects its newer head.
4. Run `alembic upgrade head`, then `/ready` and the release smoke tests. The backup verifier derives the expected revision from the single Alembic head in the release checkout, requires the restored database to contain exactly that one revision, and verifies every table declared by the current ORM model graph. It therefore stays current as migrations are added and fails closed on ambiguous revisions or an incomplete application schema.
5. If a migration fails, stop the release and restore the verified pre-release backup. Do not improvise a production downgrade; migration downgrades are validated for development recovery, while the database backup is the production rollback boundary.

Keep encrypted backups outside the application host, apply a retention policy, and run a restore verification at least monthly and before every schema release.

The GitHub release gate runs on a pinned Ubuntu 24.04 image with PostgreSQL 16
server and client tools. Browser-contract retries are disabled so a flaky first
attempt cannot be hidden by a retry. A failed browser run retains the
Playwright report plus the isolated API, frontend, and fake-Woo service logs;
the workflow has read-only repository permission and checkout credentials are
not persisted.

## Hosting portability

Google Sheets credentials are configured in Settings → Google Sheets and are
stored encrypted in PostgreSQL, not in Heroku configuration. When moving Pongo
to another host, migrate the database and preserve the existing
`WOOCOMMERCE_CONFIGURATION_ENCRYPTION_KEY`; it is the deployment-neutral master
key for encrypted integration records. Losing or changing that key makes saved
WooCommerce and Google credentials unreadable.

Create a Google OAuth **Web application** client and copy the exact authorized
redirect URI displayed by Pongo into Google Cloud. For the current production
origin it is
`https://inventory.pongo.ca/api/reports/google-sheets/oauth/callback`. If the
public origin changes, update the Google OAuth client to the new URI shown in
Settings before reconnecting. Staff never configure or copy a refresh token.

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
daily catalog reconciliation after midnight in `ADMIN_TIMEZONE` and generates
queued legal/reporting snapshots. Do not run
schedulers in the web process. Keep `heroku/nodejs` first and `heroku/python` last. Attach
Heroku Postgres before the first release, set `APP_ENV=production`, and use the
app's exact HTTPS origin for `BACKEND_CORS_ORIGINS`.

## Performance contract

- API responses larger than 1 KB use gzip compression. Hashed frontend assets
  are immutable so browsers and Cloudflare may cache them safely.
- Insights and the business dashboard read local, versioned metric snapshots;
  they never wait on WooCommerce during navigation.
- Item, inventory, Open Orders, Allocate, and Pick Orders use server pagination and
  SQL-side filtering. Item facets load separately and are reused across page
  changes; operational stock is never cached with them. Inventory cards use a
  single SQL aggregation query. The
  frontend cancels obsolete requests, deduplicates identical GETs, and
  lazy-loads images and report/chart modules.
- Routine order-screen refresh runs every two minutes only while an affected
  view is visible; webhook notifications can still refresh that view sooner.
- Operational mutations invalidate affected metric snapshots immediately.
  WooCommerce sales metrics are refreshed after the two-minute reconciliation.
- A stale dashboard/filter snapshot is served immediately and marked for worker
  refresh; custom filters use the same queue as standard dashboard presets.
- Heavy report calculation and CSV/PDF rendering run on the worker; downloads
  stream verified artifacts stored in PostgreSQL. Keep both `web=1` and `worker=1` enabled;
  scaling the web process without revisiting cache/build locking is unsupported.
