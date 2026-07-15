# Pongo Inventory OS: Pre-Production Audit

Audit date: 2026-07-14. Read-only audit of the repository at commit `5d3b0e0` plus uncommitted working-tree changes. All statuses below were verified by reading code and running the existing test suites, migrations, and build. No code was modified.

## 1. Executive Summary

The codebase is in much better shape than a typical pre-launch project: 238 backend tests and 48 frontend tests pass, the full Alembic migration chain (0001 to 0019) runs cleanly on a fresh database, the production build succeeds, and the core inventory, order, and WooCommerce workflows are genuinely implemented end to end with disciplined transaction handling and audit trails. Nothing in the repository is outright broken. However, the application has zero authentication on roughly 150 API endpoints, including the endpoints that mutate stock and push order-status writes to WooCommerce, so it cannot be exposed to any network as-is. There is also no deployment configuration of any kind (no Procfile, Dockerfile, or CI), no logging or observability beyond a single logger in the WooCommerce client, and order sync only runs while a staff browser tab is open. The feature set is roughly MVP-complete for its stated scope; the remaining work is almost entirely production infrastructure, not features.

## 2. Tech Stack (as found in code)

- Backend: Python, FastAPI 0.124.4, SQLAlchemy 2.0.45, Alembic 1.17.2, httpx 0.28.1, psycopg 3.3.2, uvicorn 0.38.0, pydantic-settings 2.12.0, pytest 9.0.2 (`backend/requirements.txt`, pinned)
- Frontend: React 19.1, Vite 7, lucide-react; Vitest 4 + Testing Library for tests (`frontend/package.json`, `package-lock.json`)
- Database: SQLite for local dev, PostgreSQL targeted for production (`backend/app/db/session.py:9-14` rewrites the URL to psycopg3)
- No router library on the frontend; navigation is hash-based inside a single 10,636-line `frontend/src/App.jsx`

### Architecture

```
Staff browser (React SPA, single App.jsx)
   |  fetch -> API_BASE_URL (default http://127.0.0.1:8000)
   |  polls: quick order sync (~10s), webhook event feed (~2s)
   v
FastAPI backend (backend/app/main.py, 20 routers under /api)
   |-- services/ (all business logic: items, receiving, cycle counts,
   |    allocations FIFO, picks, order workflow, reports, insights,
   |    routes, imports)
   |-- SQLAlchemy models -> Postgres/SQLite (Alembic migrations 0001-0019)
   |
   |-- WooCommerceClient (httpx, key/secret in query params)
   |      reads: products, variations, orders (staging32.pongo.ca)
   |      writes: allowlisted, queued, manual approve/send only
   |
   `-- Inbound webhook POST /api/integrations/woocommerce/webhooks/orders
          HMAC-SHA256 verified, idempotency ledger, event outbox
```

There are no background jobs, no scheduler, and no queue worker. Every WooCommerce sync and writeback send is triggered by an HTTP request, which in practice means by a staff member's open browser tab.

## 3. Feature Status Table

| Feature | Status | Evidence |
|---|---|---|
| Health check | FULLY IMPLEMENTED | `backend/app/api/routes/health.py`. Note: static response, does not check DB connectivity. |
| Items CRUD, search, filters, detail control center | FULLY IMPLEMENTED | `routes/items.py` (507 lines), `services/items.py`, `services/item_control.py`; covered by `tests/test_items_api.py`. |
| Item CSV import/export (Zenventory format) | FULLY IMPLEMENTED | `services/item_import.py`, `routes/import_jobs.py`; `tests/test_items_import_api.py`. Invalid numerics are collected as row errors (`item_import.py:218-224`). |
| Locations CRUD + CSV import/export | FULLY IMPLEMENTED | `routes/locations.py`, `services/location_import.py`; `tests/test_locations_api.py`. |
| Stock by location v2 (item-location rows as source of truth) | FULLY IMPLEMENTED | `services/location_inventory.py` (936 lines); `tests/test_inventory_api.py`. |
| Direct receiving + bulk receiving sessions | FULLY IMPLEMENTED | `services/receiving.py`, `services/bulk_receiving.py`, `routes/receipts.py`; `tests/test_receiving_api.py`. Bulk endpoints take untyped `dict` payloads (`routes/receipts.py:38,43`). |
| Cycle counts | FULLY IMPLEMENTED | `services/cycle_counts.py`, `routes/cycle_counts.py`; `tests/test_cycle_counts_api.py`. |
| Stock adjustments + movements ledger | FULLY IMPLEMENTED | `routes/stock_movements.py`, movement rows written by all stock-changing services. |
| Scanner workflows (lookup, receiving, cycle count, transfer, adjustment) | FULLY IMPLEMENTED | `routes/scanner.py`; `tests/test_items_bulk_scanner_reports_api.py`. All 10 scan endpoints take untyped `dict` payloads (`routes/scanner.py:101-201`). |
| Inventory transfers | PARTIALLY IMPLEMENTED | Backend endpoints and `InventoryTransfer` model exist (`routes/scanner.py:147-176`, migration 0013), but the transfer UI is deliberately hidden (README line 224). Working but unreachable by staff. |
| WooCommerce product/variation sync (read-only) | FULLY IMPLEMENTED | `services/woocommerce_sync.py`, preview/commit + sync-run audit; `tests/test_woocommerce_sync_api.py`. |
| WooCommerce order sync + 10s quick sync | FULLY IMPLEMENTED | `services/woocommerce_orders.py` (938 lines), `routes/woocommerce.py:129-143`; `tests/test_woocommerce_order_sync_api.py`. No server-side schedule; runs only when the frontend polls. |
| WooCommerce order.created webhook | FULLY IMPLEMENTED | `services/woocommerce_webhooks.py` (454 lines): HMAC-SHA256 with `hmac.compare_digest` (line 313), body-size caps, header allowlist, source-host allowlist, idempotency ledger, event outbox, cursor feed; `tests/test_woocommerce_webhook_api.py`. Disabled by default. |
| WooCommerce writeback queue (stock, order status) | PARTIALLY IMPLEMENTED (by design) | `services/woocommerce_writeback.py`, `services/woocommerce_client.py:150-194` (allowlisted ops, DELETE always blocked, production limited to order-status completed). Staging-only for stock; manual preview -> queue -> approve -> send, no retry worker, no automatic sending. `tests/test_woocommerce_writeback_api.py`. |
| WooCommerce remap (local item to Woo product mapping) | FULLY IMPLEMENTED | `services/woocommerce_remap.py`; covered in `tests/test_woocommerce_sync_api.py`. |
| FIFO auto-allocation + shortage workflow | FULLY IMPLEMENTED | `services/allocations.py` (652 lines), `services/order_workflow.py` (806 lines); Postgres advisory lock for concurrency (`order_workflow.py:373-375`, no-op on SQLite); `tests/test_allocations_api.py`, `tests/test_order_workflow_api.py`. |
| Pick queue, per-line picks, bulk pick/unpick, pick history | FULLY IMPLEMENTED | `services/picks.py` (859 lines) with rollback-on-error transactions (lines 274, 395-400); `tests/test_picks_api.py`. |
| Order completion (picked and unpicked paths) | FULLY IMPLEMENTED | `order_workflow.py:401-443`, guards against double stock reduction; `tests/test_order_workflow_api.py`. |
| Legacy fulfillments + fulfillment report | FULLY IMPLEMENTED | `services/fulfillments.py`, `services/fulfillment_report.py`; `tests/test_fulfillments_api.py`, `tests/test_fulfillment_reports_api.py`. |
| Completed orders list/export | FULLY IMPLEMENTED | `services/completed_orders.py`, `routes/orders.py:70-104`. |
| Reports suite (11 report families, each with list/summary/export) | FULLY IMPLEMENTED | `routes/reports.py` (586 lines), all query real tables. Several filter in Python after loading all rows (see Performance). `GET /api/reports` itself returns `{"status": "placeholder"}` (`reports.py:35-36`), which is trivial and unused. |
| Inventory Overview dashboard | FULLY IMPLEMENTED | `services/dashboard.py`; loads all items/orders/routes into memory per request (lines 33-35). `tests/test_business_dashboard_api.py` sibling coverage. |
| Business dashboard | FULLY IMPLEMENTED (one section empty by design) | `services/business_dashboard.py`. Subscriptions section reads `raw_woo_payload["subscriptions"]`, which standard Woo order payloads never contain, so it shows a designed empty state with a data-quality warning (lines 89-100, 63-64). City map uses 7 hardcoded Edmonton-area coordinates (lines 18-26). |
| Pongo Insights (13 BI dashboards) | FULLY IMPLEMENTED | `services/insights.py` (915 lines), all derived from local orders/items; loads every order into memory per request (`insights.py:64-66`). `tests/test_insights_api.py`. |
| Saved item views / UI settings | FULLY IMPLEMENTED | `routes/ui.py`, untyped `dict` payloads (lines 39, 57). |
| Route creation, metadata, stop reorder, CSV, map payload | FULLY IMPLEMENTED (local only) | `services/routes.py`; `tests/test_routes_api.py`. |
| Route geocoding / optimization / live map providers | STUB (deliberate) | `services/routes.py:324-365` returns `status="disabled"`, "Provider integration is not enabled for live calls in this MVP". Config keys exist (`config.py:41-45`) but nothing consumes `MAP_API_KEY`. |
| Frontend Categories / Commodities views | STUB | `App.jsx:3316-3325` renders `StandardPage` labeled "Placeholder view for later item taxonomy management", backed by hardcoded `mockItems` (`App.jsx:398`, rendered at `App.jsx:9386`). |
| Frontend Location Stock sub-view | STUB | `App.jsx:3987-3996`: "Placeholder for future item-location stock splits. Item stock logic is not connected yet." |
| Staff auth / login | MISSING | No auth code anywhere in the repo. README lines 51-52 confirm it is intentionally not built. |
| Production deployment (Heroku files, CI) | MISSING | No Procfile, Dockerfile, docker-compose, or `.github/` anywhere. README line 15: "Deployment target: Heroku later". |
| Purchase orders, suppliers, shipping labels, customer notifications | MISSING | Referenced in README lines 56 and 242 as intentionally out of scope; no code exists. |

## 4. Broken Things

None found. I looked specifically for unresolved imports, calls to nonexistent functions, schema mismatches, and dead code paths, and verified behavior by running the suites:

- 238/238 backend tests pass (`pytest backend/tests`, 11.07s)
- 48/48 frontend tests pass (Vitest)
- `npm run build` succeeds (with a bundle-size warning, see below)
- `alembic upgrade head` runs the full 19-migration chain cleanly on a fresh database

One caveat: backend tests create the schema with `Base.metadata.create_all` (for example `tests/test_items_api.py:20`) rather than running migrations, so model/migration drift would not be caught by the suite. My manual migration run passed, but the suites do not guard this continuously.

## 5. Production Blockers

These must be fixed before this system is exposed beyond localhost. Effort: S = under a day, M = days, L = a week or more.

1. **No authentication or authorization on any endpoint (L).** Every route in `backend/app/main.py:19-38` is open, including stock mutation, bulk order completion, and `POST /api/integrations/woocommerce/writeback/queue/{id}/send` (`routes/woocommerce.py:344-349`), which pushes real writes to WooCommerce. Anyone who can reach the backend owns the inventory and the store integration. The README defers "Auth/RBAC" but launch without at least a simple staff login plus server-side session/token checks is not viable.
2. **No deployment configuration (M).** Nothing exists to deploy: no Procfile/Dockerfile, no CI, no production CORS origins, no production `DATABASE_URL` handling beyond the env var, and `APP_ENV` is read into config but never used anywhere in the code. The frontend bakes `VITE_API_BASE_URL` at build time and silently falls back to `http://127.0.0.1:8000` (`App.jsx:99`); a misconfigured build would produce a UI that quietly talks to nothing.
3. **No logging or observability (M).** The only logger in the entire backend is in `woocommerce_client.py`. There is no request logging, no global exception handler, no error tracker, and no alerting. When something breaks in production you will find out from staff, not from the system. The health endpoint (`routes/health.py`) does not even check database connectivity.
4. **Order sync depends on an open browser tab (M).** Quick sync fires from a frontend `setInterval` (`App.jsx:884`), and the webhook only covers `order.created`. Overnight or whenever no one has the app open, status changes and edits in WooCommerce accumulate unsynced, and FIFO allocation does not run. A server-side scheduled sync (or worker) is needed for correctness, not just convenience.
5. **Sixteen mutation endpoints accept untyped `dict` payloads (S/M).** All scanner commits, bulk receiving, bulk item update, item notes, and saved views (`routes/scanner.py:101-201`, `routes/receipts.py:38-43`, `routes/items.py:119-124,366,380`, `routes/ui.py:39,57`) bypass Pydantic validation. Malformed input reaches service code directly; combined with no auth this is the riskiest input surface. Define request schemas.
6. **Rotate the WooCommerce staging keys before launch and confirm production key handling (S).** `backend/.env` is correctly gitignored and the git history is clean (verified with `git grep` across all commits), but live staging keys currently sit in a plaintext local file and the client sends key/secret as URL query parameters (`woocommerce_client.py:227`), which commonly end up in server access logs. Plan production keys as deployment secrets only, and prefer Basic auth over query-string credentials if the host supports it.

## 6. Should-Fix (non-blocking)

- **Unbounded list endpoints.** `GET /api/items` returns every item with no limit/offset (`routes/items.py:129-152`); insights and the two dashboards load every order and item into memory on each request (`insights.py:64-66`, `dashboard.py:33-35`, `business_dashboard.py`); several reports load all rows and filter in Python (`reports.py:328-357, 372-387, 465-485`). Fine at current boutique scale, painful as order history grows. Add pagination and push date filters into SQL.
- **Frontend is a single 10,636-line file** (`App.jsx`) plus a 5,112-line CSS file, producing one 524 kB JS chunk (build warning). It works, but it will resist every future change. Split by page and add code splitting.
- **Frontend test coverage is thin relative to the surface**: 48 tests against 10.6k lines cover the shell, navigation, Items, Scanner, and Reports switching; the order workflow, receiving, and WooCommerce screens have no tests. There are no end-to-end tests.
- **Repository hygiene**: a 24.6 MB `Untitled.mov` is committed (git repo is 88 MB), and `tmp/`, `.pytest_cache/`, and `.DS_Store` files are lying around untracked. Remove the video from history before adding collaborators or CI.
- **Polling load**: every open tab quick-syncs orders every 10 seconds and polls the event feed every 2 seconds (`App.jsx:884,902`). Multiple tabs multiply WooCommerce API load. Once a server-side sync exists, the frontend should poll the local DB only.
- **Tests should exercise Alembic** (run migrations in at least one test) so schema drift is caught.
- **`WOOCOMMERCE_READ_ONLY=false` and live writeback flags are enabled in the local `.env`**; the safe defaults exist in code, but document that production must start from `.env.example` values, not a copy of the current dev file.
- Dependency health is good: `npm audit` reports 0 vulnerabilities and Python pins are current; keep them pinned.

## 7. Distance to Production

Honest assessment: about 70 percent of the way to the stated MVP, but the missing 30 percent is concentrated in exactly the things that make software production-grade rather than feature-complete. Feature work is essentially done and well tested; infrastructure work has not started. The critical path, in order:

1. Authentication and authorization (nothing else can ship without it)
2. Deployment pipeline: Heroku (or other) config, production env separation, migrated Postgres, production CORS, frontend build/env wiring
3. Server-side scheduled order sync so correctness does not depend on an open browser tab
4. Logging, global error handling, a real health check, and error tracking
5. Request schema validation on the 16 untyped endpoints
6. Production WooCommerce credential handling and the guarded order-status writeback path enabled deliberately
7. Pagination and query pushdown on the hot list/report endpoints

Items 1 and 2 alone are roughly 2 to 3 weeks of focused work; the rest is another 1 to 2 weeks. Nothing discovered suggests hidden rot: the code under the surface matches what the README claims, which is rare.

## 8. Recommended Next 10 Tasks

1. Add staff authentication: a users table, login endpoint, hashed passwords, and a FastAPI dependency that protects every `/api` router; wire a login screen and token handling into the frontend.
2. Add an authorization gate specifically on WooCommerce writeback approve/send and bulk order actions (even a simple role flag), since these have external and irreversible effects.
3. Define Pydantic request schemas for the 16 `dict` endpoints in `routes/scanner.py`, `routes/receipts.py`, `routes/items.py`, and `routes/ui.py`.
4. Create deployment artifacts: Procfile (web: uvicorn, release: alembic upgrade head) or Dockerfile, production settings profile that actually uses `APP_ENV`, production CORS origins, and a documented `VITE_API_BASE_URL` build step.
5. Set up CI (GitHub Actions): backend pytest, frontend vitest and build, and an Alembic upgrade against a fresh Postgres service container.
6. Add logging middleware (request method, path, status, duration), a global exception handler that logs stack traces, and an error tracker such as Sentry; extend `/health` to ping the database.
7. Implement a server-side scheduled quick sync (APScheduler, Heroku Scheduler, or a worker dyno) and reduce frontend polling to local-DB reads.
8. Add limit/offset pagination to `GET /api/items` and the report list endpoints, and move date filtering into SQL for the movement ledger, margin, and receiving-cost reports.
9. Rotate the staging WooCommerce keys, move credentials to deployment secrets, and switch the client to HTTP Basic auth for the Woo REST API instead of query-string credentials.
10. Purge `Untitled.mov` from git history, delete stray `tmp/` and cache artifacts, and split `App.jsx` into per-page modules with route-level code splitting.
