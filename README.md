# Pongo Inventory OS

Pongo Inventory OS is a standalone internal inventory and operations system for Pongo Pet Supplies. It is the operational inventory layer beside WooCommerce: WooCommerce remains the customer-facing storefront, while Pongo OS manages local item data, stock workflows, order allocation, picking, completion, reports, and routes.

This is not a WordPress plugin, not a WooCommerce plugin, and not a shortcode app.

## Stack

- Backend: FastAPI
- ORM: SQLAlchemy
- Migrations: Alembic
- Local dev DB: SQLite
- Target production DB: PostgreSQL
- Frontend: React with Vite
- Deployment target: Heroku later
- WooCommerce integration: backend-only REST API plus a signed order webhook

## Current Modules

Implemented locally:
- Command Center dashboard
- Persistent Items
- Guided, resumable item CSV import with column matching, inline correction,
  mapping profiles, immutable previews, audited history, and safe rollback
- Locations and inventory by location reporting/export
- Stock by Location v2 with item-location source-of-truth rows
- Direct receiving without purchase orders
- Received inventory report
- Cycle count
- Read-only WooCommerce product/variation sync
- Local WooCommerce remap metadata
- Read-only WooCommerce order sync and open orders
- Signed WooCommerce `order.created` and `order.updated` webhook import with a
  durable delivery ledger, immutable order-event audit, new-order-only cursor
  feed, and session-scoped staff notification center
- Staging-only WooCommerce writeback queue foundation with optional live test mode
- Automatic guarded staging stock writeback when picked orders are completed
  and after manual adjustments, plus changed-only and full-catalog controls
- Processing-only FIFO auto-allocation on WooCommerce order import and stock
  availability changes; oldest WooCommerce `date_created` receives stock first
  and partial quantities are reserved
- Allocate shortage workflow with Orders/Items views, audited stock adjustment,
  and manual FIFO reconciliation
- Arrow-driven pick queue, manual per-line picked quantities, pick history,
  selectable Pick/Unpick bulk actions, and audited pick-time stock reduction
- Local order completion
- Legacy fulfillment compatibility/history
- Stock adjustments
- Fulfillment/completion report
- Completed orders export
- SKU Orders report
- Selectable open-order delivery planning from the Pongo warehouse, balanced by estimated workload or explicitly assigned N/S/E/W/NE/NW/SE/SW/Central East/Central West zones across 1–50 drivers, with a responsive all-stop overview, shareable Google Maps navigation links, and separate completed-route records
- Cookie-based staff login plus an isolated read-only demo role with mock data only
- Immutable, hash-verified report runs with interactive dashboards, CSV/PDF, Google Sheets, and audited email sharing
- Resumable background full-catalog WooCommerce stock-sync jobs with progress, retry, resume, and cancel controls

Not implemented yet:
- Provider-backed street-map tiles, address geocoding, or traffic-aware route optimization calls
- Supplier management, purchase orders, delivery issue logs, customer notifications, and shipping labels

## Safety Boundaries

- Do not commit credentials, API keys, secrets, or real customer data.
- WooCommerce credentials are submitted only to the authenticated backend and
  stored encrypted in PostgreSQL; the encryption key remains a backend environment secret.
- Saving WooCommerce credentials verifies read access to both products and
  orders, then starts a bounded server-side open-order sync immediately; the
  periodic reconciliation job imports the full backlog and later changes.
- The webhook receiver is disabled by default. Its separate secret must be at
  least 32 bytes and must never be committed, logged, or returned by the API.
- Frontend code must never call WooCommerce directly.
- WooCommerce sync reads staging/production data through the backend only.
- WooCommerce writeback is allowlisted, queued, and audited. Production stock
  writes require the explicit `WOOCOMMERCE_PRODUCTION_STOCK_AUTHORITY=pongo`
  policy plus the normal host, operation, payload, dry-run, and permission guards.
- Settings → Connection provides an audited `read_only` / `read_write` switch.
  Read-only mode permits WooCommerce GET operations; read-write mode enables the
  supported stock and completed-order writeback workflows.
- WooCommerce DELETE is always blocked.
- WooCommerce stock is stored only as a read-only snapshot.
- Completing an order sends a guarded, audited `completed` status update through
  the backend writeback queue. The frontend never calls WooCommerce directly.
- Authenticated `order.created` and `order.updated` webhook deliveries reconcile
  statuses and line quantities. Other topics are audited and ignored; periodic
  backend reconciliation covers missed deliveries.
- The frontend seeds the durable event cursor without replaying old alerts,
  polls it every 2 seconds while visible, and uses quick-sync creation counts as
  a deduplicated fallback alert.
- The new-order notice is an internal Pongo staff UI alert. It does not send
  email, SMS, browser push, or any customer-facing notification.
- Pongo OS local inventory is the operational source of truth.
- Location stock rows are the operational quantity source; item stock fields
  are cached aggregates for compatibility and fast display.
- Stock-changing local workflows must create stock movement or audit rows.
- Picking reduces local In Stock and Allocated quantities and creates
  `pick_stock_reduction` stock movements.
- Completing a picked order never reduces stock again.
- Completing an unpicked order does not reduce stock and releases remaining
  local allocation.
- WooCommerce `processing` orders and newly ingested FooSales POS orders
  participate in Open, Allocate, and Pick. Reporting-only historical snapshots
  never enter those operational queues.
  Allocation runs oldest first with a deterministic local-order-ID tie-break;
  partially allocated orders remain in Allocate until fully pick-ready.
- Receiving, stock adjustments, cycle counts, completion releases, and synced
  non-processing status changes automatically retry FIFO allocation. A status
  change out of processing releases the order's remaining unpicked reservation
  before the next eligible order is evaluated.
- Route, dashboard, report, remap, and metadata work must not mutate stock quantities.
- Map/geocoding/optimization providers are disabled unless configured backend-side.

## Local Setup

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
DATABASE_URL=sqlite:///local_items_dev.db .venv/bin/python -m alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Local URLs:
- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/health

## Tests And Builds

Backend tests:

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Frontend build:

```bash
cd frontend
npm run build
```

Frontend tests:

```bash
cd frontend
npm test -- --run
```

Frontend QA checklist: `docs/FRONTEND_QA.md`.

## Environment

Use placeholders only in `.env.example`. Backend encryption and webhook secrets belong in local or deployment environment variables.

Staff configure the WooCommerce store URL, consumer key, and consumer secret in
Settings → Connection. The authenticated backend verifies them and stores them
encrypted in PostgreSQL; responses expose only presence flags. Do not commit,
print, document, or return real credentials. Set
`WOOCOMMERCE_CONFIGURATION_ENCRYPTION_KEY` to a stable random value of at least
32 bytes in production.

The inbound order webhook is a separate, read-only integration and does not
require writeback to be enabled. Its safe defaults are:

```bash
WOOCOMMERCE_WEBHOOK_ENABLED=false
WOOCOMMERCE_WEBHOOK_SECRET=
WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES=1048576
```

When deliberately enabling it, set a distinct random secret of at least 32
bytes in both WooCommerce and the backend deployment environment. WooCommerce
must deliver to a publicly reachable HTTPS URL:
`https://<backend-host>/api/integrations/woocommerce/webhooks/orders`.
`WOOCOMMERCE_ALLOWED_HOST` is required and is the exact allowlisted
`X-WC-Webhook-Source` host. Localhost URLs cannot receive a staging
WooCommerce webhook.

Live staging write tests are configured separately and require all of these
non-secret guard flags in addition to the staging REST API key and secret:

```bash
WOOCOMMERCE_ENVIRONMENT=staging
WOOCOMMERCE_READ_ONLY=false
WOOCOMMERCE_READ_ENABLED=true
WOOCOMMERCE_WRITEBACK_ENABLED=true
WOOCOMMERCE_WRITEBACK_DRY_RUN=false
WOOCOMMERCE_STAGING_LIVE_TEST_MODE=true
WOOCOMMERCE_ALLOW_STOCK_WRITE=true
WOOCOMMERCE_ALLOW_ORDER_STATUS_WRITE=true
WOOCOMMERCE_ALLOW_PRODUCT_METADATA_WRITE=false
WOOCOMMERCE_ALLOW_CUSTOMER_WRITE=false
WOOCOMMERCE_ALLOW_COUPON_WRITE=false
WOOCOMMERCE_ALLOW_REFUND_WRITE=false
WOOCOMMERCE_ALLOW_DELETE=false
WOOCOMMERCE_ALLOWED_HOST=staging-hostname-only
```

Allowed staging writeback operation types are `update_product_stock`,
`update_variation_stock`, and `update_order_status`. Stock payloads may include
only `stock_quantity`, `stock_status`, and `manage_stock`; order payloads may
include only `status`. Writeback requests must be previewed, queued, approved,
and sent through backend endpoints. The frontend never calls WooCommerce
directly, and DELETE remains blocked even in live test mode.

Route provider placeholders are intentionally disabled by default:

```bash
ROUTE_GEO_PROVIDER=disabled
ROUTE_MAP_PROVIDER=disabled
ROUTE_OPTIMIZATION_PROVIDER=disabled
```

## Current Production Operations Chunk

Current local build now includes:
- Pongo-branded frontend design tokens using primary blue `#0f149a`, soft peach surfaces, consistent button states, contained table scrolling, and no-horizontal-body-overflow safeguards.
- A default `Dashboard` home page for business metrics, customer/order activity, subscription empty states, revenue comparison, city-level order geography, and a first-position live WooCommerce `processing` order count. See `docs/BUSINESS_DASHBOARD.md`.
- The former operational dashboard is now `Inventory Overview`.
- Frontend Vitest/Testing Library coverage for design-system primitives, app shell navigation, Items, Scanner mode switching, and Reports single-panel switching.
- Production-grade Items and Inventory controls: rich filters, image-aware table rows, column visibility, saved item views, shared safe bulk editing for non-unique metadata/tags/locations/costs, debounced keyword search with live item/SKU suggestions, and an Item Detail Control Center.
- Item Detail Control Center tabs for overview, stock by location, activity, history, and metadata edit. Stock quantity edits remain routed through receiving, cycle count, or adjustment workflows.
- Bulk Receiving Session under Receiving. It previews multi-row receiving carts, commits valid rows into one local receipt, updates `inventory_item_locations`, recalculates item aggregate stock fields, and creates stock movements.
- Scanner page for inventory lookup, location lookup, receiving, cycle count,
  and adjustment. Items and every Inventory subpage also provide an on-demand
  phone-camera scanner for QR codes and product barcodes. Pick Orders uses
  manual per-line quantities and does not require barcode scanning.
- Barcode scans try the captured value and its single-leading-zero alternate;
  SKU identity remains exact. Manual inventory edits accept one non-negative
  final quantity (including zero), keep allocation safeguards, and audit a
  default reason when staff leave the optional reason blank.
- Inventory is organized into sidebar subpages: All Inventory, Inventory by Location, Low Stock, Expiring Stock, Par Level, and Stock Movements. Transfer UI is hidden and is not part of the active frontend workflow.
- Expanded read-only reports: inventory valuation, low stock/reorder, stock movement ledger, item activity, location utilization, margin by SKU, receiving cost, and adjustment/damage/loss.
- Verified reporting workspace with 17 immutable, hash-audited report types,
  interactive charts, CSV/PDF downloads, Google Sheets publishing, and direct
  email delivery. Calculation and accounting boundaries are documented in
  `docs/REPORTING.md`.
- Pongo Insights: a separate read-only BI page with tabbed dashboards for executive overview, revenue, customers, segmentation, SKU demand, subscriptions empty states, forecasting, coupons, payment health, geography, affinity, and reorder forecast. See `docs/INSIGHTS.md`.
- Zenventory-style Orders workflow: Woo order sync runs FIFO for processing and FooSales POS
  auto-allocation, Open Orders is review/completion, Allocate shows unresolved
  Orders/Items shortages, fully allocated orders enter Pick Orders, and Order
  History holds allocation/pick/legacy fulfillment records. See
  `docs/ORDER_WORKFLOW.md`.
- Event-driven Woo order reconciliation: signed `order.created` and
  `order.updated` deliveries are imported through the backend, recorded in a
  durable idempotency ledger, and published to an immutable local event outbox
  for the internal staff new-order alert. A backend scheduler reconciles missed
  and terminal changes; browser refreshes are display-only.
- Resumable GET-only historical WooCommerce order import: past orders across all statuses
  feed Insights and Reports without allocating stock, entering warehouse
  workflows, or writing to WooCommerce.

Still intentionally delayed:
- Granular staff RBAC beyond the isolated demo role.
- Live WooCommerce credential/webhook contract checks outside the deployed application.
- Purchase orders and supplier management.
- Shipping labels, customer notifications, delivery issue logs,
  return-to-inventory workflows, provider-backed street-map tiles, address geocoding, and
  traffic-aware route optimization provider calls.

## Demo Account

Demo users can browse every normal workspace using a separate seeded mock
database. They cannot read production records, save changes, publish reports,
or access WooCommerce/Google integrations. Create or rotate an account after
running migrations:

```bash
cd backend
.venv/bin/python scripts/create_demo_user.py --email demo@example.com
```

The command prompts for a 12+ character password and refuses to convert an
existing staff account.

## Item Import And WooCommerce Catalog Workflows

Items → **Import items** is a dedicated six-step workspace for four explicit
outcomes: Add new items, Update item details, Override stock levels, or Set starting inventory. The
backend owns the field schema and templates, persists resumable previews,
suggests and saves column mappings, supports row-level correction/exclusion,
stops stale commits, records field-level audit history, and produces original
and failed-row downloads. Metadata imports cannot change on hand, allocated,
available, or movement history. **Update stock CSV** accepts a full inventory
export directly: SKU and In stock are mandatory, while warehouse/location are
ignored with unrelated columns. Multiple location rows for one SKU are summed
into one exact SKU total. Matching totals are skipped, unknown SKUs remain
unchanged, and every matched difference is applied in one audited transaction.
Invalid quantities, allocation conflicts, or stale stock block every matched
change. Allocated and Sellable remain system-managed. Starting inventory
remains limited to pre-operational stock.

WooCommerce catalog sync is separate under Items → More. It previews and imports
every Woo simple product and purchasable variation through the backend-only
integration. A variable parent is reference metadata, not a stock item.
Repeated syncs refresh Woo-owned fields without overwriting operational stock or
history.

See [`docs/ITEM_IMPORTS.md`](docs/ITEM_IMPORTS.md) for templates, validation,
concurrency, rollback, API, configuration, and the QA runbook. Legacy canonical
import and enrichment endpoints remain for compatibility but are not used by the
new Items workflow.

Development reset commands are guarded and never call WooCommerce:

```bash
make reset-local-db
make seed-local-locations
```

Back up the local database first. See `docs/FIRST_TIME_WOO_MIGRATION.md`.
# pathwright
