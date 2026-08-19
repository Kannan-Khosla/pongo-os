# API Specification

This document describes the current Pongo Inventory OS backend API plus planned
future boundaries. The backend implements health, Command Center dashboard,
Items, item import/export, Locations, inventory by-location reporting/export,
Stock by Location v2, inventory transfers, stock adjustments, direct receiving,
received inventory reporting, cycle counts, read-only
WooCommerce product and order sync, signed phase-1 order webhooks and staff
event feed, local WooCommerce remap metadata, guarded WooCommerce writeback,
open orders, allocations,
scanner-style picks with pick-time stock reduction, local completion,
fulfillment compatibility/history, completed orders, SKU Orders reporting, and
local-only route creation/management.

## API Rules

- Frontend calls only the Pongo Inventory OS backend.
- Frontend never calls WooCommerce directly.
- WooCommerce credentials are submitted to the authenticated backend, stored
  encrypted in PostgreSQL, and never returned by the API.
- Stock-changing endpoints must create stock movement/audit rows.
- Pick, unpick, direct/bulk receipt, transfer, and adjustment commit requests
  require a nonblank `idempotency_key` (maximum 120 characters). Reusing the
  same key with the same payload replays the stored response; reusing it with
  different data returns HTTP `409`.
- WooCommerce credentials are never returned by API responses.
- WooCommerce writeback is allowlisted, queued, and audited. Production stock
  writes require the explicit Pongo stock-authority policy and all normal
  host, operation, payload, permission, and dry-run guards.
- WooCommerce DELETE is always blocked.
- Order completion sends the linked WooCommerce order a guarded `completed`
  status update through the backend writeback queue.
- The inbound webhook receiver is disabled by default, uses a separate secret,
  authenticates the exact raw body, and never treats CORS or source headers
  alone as authentication.
- Webhook-backed UI notices are internal staff feedback only. They do not send
  customer messages or make outbound WooCommerce requests.
- Allocation reserves local stock only; picking is the local stock reduction
  step; completion never reduces stock again.
- Route map/geocoding/optimization providers are disabled unless configured
  backend-side. Provider endpoints must never expose secrets.
- A user with `access_level=demo` is rebound after authentication to the
  isolated seeded demo database. Demo requests may read mock data and run
  explicitly allowlisted non-persisting previews; all other writes return
  `403 demo_read_only`, and external integration routes return
  `403 demo_external_access_blocked`.

## Current API Groups

- `GET /health`
- Authentication: `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`. Auth responses include `access_level`, `data_scope`, and `permissions`.
- Readiness: `GET /ready`
- Dashboard: `/api/dashboard`, `/api/dashboard/summary`, `/api/dashboard/activity`, `/api/dashboard/warnings`
- Items and item CSV import/export: `/api/items`, `/api/items/import/*`
- Import jobs: `/api/import-jobs`
- Locations and location CSV import/export: `/api/locations`
- Inventory reports/exports: `/api/inventory`
- Location inventory: `/api/inventory/locations`, `/api/inventory/locations/export`
- Inventory transfers: `/api/inventory/transfers`
- Stock adjustments: `/api/inventory/adjustments`
- Receipts/direct receiving: `/api/receipts`
- Reports: background jobs under `/api/reports/jobs/*`, immutable runs and delivery under `/api/reports/runs/*`, plus legacy received, fulfillment, and SKU-order report endpoints
- Cycle counts: `/api/cycle-counts`
- WooCommerce product import and guarded metadata sync: `/api/integrations/woocommerce/products/*`
- WooCommerce read-only order sync: `/api/integrations/woocommerce/orders/*`
- WooCommerce signed order webhook and event cursor:
  `/api/integrations/woocommerce/webhooks/*`
- WooCommerce local remap: `/api/integrations/woocommerce/remap/*`
- WooCommerce staging writeback queue: `/api/integrations/woocommerce/writeback/*`
- Orders: `/api/orders/open`, `/api/orders/allocate`, `/api/orders/pick`, `/api/orders/completed`, `/api/orders/history`, `/api/orders/{id}`
- Allocations: `/api/allocations`, `/api/allocations/exceptions`,
  `/api/allocations/auto/commit`
- Picks and scanner picks: `/api/picks`
- Fulfillments: `/api/fulfillments`
- Routes and open-order delivery planning: `/api/routes`

## Health

### GET /health

Returns service health and basic build metadata.

Current response:

```json
{
  "status": "ok",
  "service": "pongo-inventory-os"
}
```

## Compatibility Note

`GET /api/reports` returns the verified report catalog, reporting timezone, and
non-secret Google Sheets/email configuration status. Workflow report
endpoints are implemented under specific report paths.

`GET /api/reports/google-sheets/configuration` returns presence flags, the
optional Drive folder ID, the exact OAuth redirect URI, and configuration audit
metadata; it never returns OAuth credentials.
`POST /api/reports/google-sheets/oauth/start` stores the OAuth app credentials
encrypted, returns a Google authorization URL with signed ten-minute state, and
never exposes a refresh token. `GET /api/reports/google-sheets/oauth/callback`
validates that state against the authenticated staff session, exchanges the
single-use code server-side, stores the returned refresh token encrypted, and
redirects to the Google Sheets Settings result state.

`POST /api/reports/google-sheets/configuration` remains for backward-compatible
administrative bootstrap. Blank credential fields retain already-saved values.

## Dashboard

### GET /api/dashboard

Returns Command Center data from local records only:
- inventory health cards
- order operations cards
- route cards
- recent activity
- data quality warnings

Inventory, order, route, and warning totals are calculated as SQL aggregates.
Warning samples are independently capped at five records per warning group,
and each recent-activity source query is capped by the requested activity
limit. The response therefore keeps exact card and warning counts without
hydrating the complete item, order-line, route-stop, or route tables.

Aliases:
- `GET /api/dashboard/summary`
- `GET /api/dashboard/activity?limit=25`
- `GET /api/dashboard/warnings`

Dashboard endpoints are read-only.

## WooCommerce Local Remap

These endpoints never call or write WooCommerce. They only manage local mapping
metadata and local item Woo ID metadata.

- `GET /api/integrations/woocommerce/remap/candidates`
- `POST /api/integrations/woocommerce/remap/preview`
- `POST /api/integrations/woocommerce/remap/commit`
- `GET /api/integrations/woocommerce/remap/mappings`
- `POST /api/integrations/woocommerce/remap/deactivate`

Remap preserves manual Pongo OS item fields and does not change stock,
allocated, sellable, picked, fulfilled, or order status quantities.

Both remap list endpoints accept `page` (default `1`) and `page_size` (default
`100`, maximum `100`) and return exact `total`, `total_pages`,
`returned_count`, `has_previous`, and `has_next` metadata. Mapping filters are
applied in PostgreSQL before counting and paging. Candidate results preserve
the established ordering: unique local catalog records first, followed by
every unique error-only Woo record still present in retained sync history.
Error-only records use the newest error for each Woo product/variation identity
and are counted and paged in SQL, so records older than the first 200 errors do
not disappear. Active mappings and local-item suggestions are bulk-loaded for
only the requested page using a fixed number of queries; a larger page does not
add one database query per candidate.
The deprecated candidate `limit` parameter remains accepted but is capped at
100; clients should use `page_size`.

## WooCommerce Status And Staging Writeback

### GET /api/integrations/woocommerce/status

Returns configuration state without exposing secrets:

- `configured`
- `base_url_host`
- `environment`
- `read_only`
- `writeback_enabled`
- `dry_run`
- `read_enabled`
- `staging_live_test_mode`
- `stock_write_allowed`
- `order_status_write_allowed`
- `product_metadata_write_allowed`
- `customer_write_allowed`
- `coupon_write_allowed`
- `refund_write_allowed`
- `delete_allowed`
- `allowed_host`
- `host_allowed`
- `last_product_sync`
- `last_order_sync`
- `webhook_enabled`
- `webhook_configured`
- `webhook_secret_present`
- `last_webhook_delivery`
- `order_reconciliation`
- `last_error`

The status endpoint may show whether key/secret env vars are present, but it
never returns their values.

`webhook_configured` is true only when the receiver is enabled, the webhook
secret is at least 32 UTF-8 bytes, and `WOOCOMMERCE_ALLOWED_HOST` is nonblank.
`last_webhook_delivery`, when present, contains only `id`, `topic`, `status`,
`woo_order_id`, `created_order`, and `received_at`.

`order_reconciliation` reports `enabled`, `running`, `healthy`, `degraded`,
`stale`, the configured interval/statuses, last attempt/success/failure,
current error count, and a safe operator message. Scheduler state is derived
from durable `woocommerce_sync_runs` records; secrets are never included.

### Staging writeback endpoints

- `POST /api/integrations/woocommerce/writeback/stock/preview`
- `POST /api/integrations/woocommerce/writeback/stock/sync`
- `GET /api/integrations/woocommerce/writeback/stock/jobs`
- `GET /api/integrations/woocommerce/writeback/stock/jobs/{id}`
- `POST /api/integrations/woocommerce/writeback/stock/jobs/{id}/resume`
- `POST /api/integrations/woocommerce/writeback/stock/jobs/{id}/cancel`
- `POST /api/integrations/woocommerce/writeback/order-status/preview`
- `POST /api/integrations/woocommerce/writeback/queue`
- `GET /api/integrations/woocommerce/writeback/queue`
- `GET /api/integrations/woocommerce/writeback/queue/{id}`
- `POST /api/integrations/woocommerce/writeback/queue/{id}/approve`
- `POST /api/integrations/woocommerce/writeback/queue/{id}/send`
- `POST /api/integrations/woocommerce/writeback/queue/{id}/cancel`
- `GET /api/integrations/woocommerce/writeback/status`
- `GET /api/integrations/woocommerce/writeback/logs`

Preview endpoints build local proposed payloads only. Queue creates local
`woo_writeback_queue` rows only. Send requires an approved queue item and
records a dry-run result without sending when `WOOCOMMERCE_WRITEBACK_DRY_RUN=true`.

`POST /writeback/stock/sync` accepts `{ "force": false }` for changed mapped
items only and `{ "force": true }` for every active mapped item. It creates,
approves, and sends the existing audited queue operation per item. The response
reports sent, dry-run, failed, unchanged, and unmapped counts. Successful sends
refresh each item's WooCommerce stock snapshot.
For local items without stored Woo IDs, sync first attempts an unambiguous
mapping from matched imported order lines. Positive quantities explicitly send
`stock_status=instock`; zero sends `stock_status=outofstock`.
The default quantity is local Sellable (`In Stock - Allocated`); an explicit
preview quantity remains available for controlled one-off tests.

Writeback queue, writeback log, and stock-sync job history are server-paged.
Queue and log history accept `page` (default `1`) and `page_size` (default
`50`, maximum `100`). Stock-sync jobs use a default `page_size` of `25` and
also accept the deprecated `limit` alias for older clients. Queue and log
history accept `search`, matched case-insensitively against operation type,
entity type, local entity ID, Woo entity ID, and status. Every response keeps
its existing collection and exact filtered `total`, and adds `page`,
`page_size`, `total_pages`, `returned_count`, `has_previous`, and `has_next`.

Live staging send is guarded by all of these conditions:

- `WOOCOMMERCE_ENVIRONMENT=staging`
- `WOOCOMMERCE_READ_ONLY=false`
- `WOOCOMMERCE_STAGING_LIVE_TEST_MODE=true`
- `WOOCOMMERCE_WRITEBACK_ENABLED=true`
- `WOOCOMMERCE_WRITEBACK_DRY_RUN=false`
- Woo base URL host exactly matches `WOOCOMMERCE_ALLOWED_HOST`
- operation type is allowlisted
- endpoint path is allowlisted
- HTTP method is `PUT` or `PATCH`
- payload fields are allowlisted for the operation

Allowed operation types are `update_product_stock`, `update_variation_stock`,
and `update_order_status`. Product/variation stock writes may send only
`stock_quantity`, `stock_status`, and `manage_stock`. Order-status writes may
send only `status`. No customer, coupon, refund, metadata/product-edit,
arbitrary endpoint, POST, or DELETE writeback is available.

## Pick Scanner

Scanner-style picking is additive on top of the existing pick commit service:

- `GET /api/picks/orders/{order_id}/scanner`
- `POST /api/picks/orders/{order_id}/scan/preview`
- `POST /api/picks/orders/{order_id}/scan/commit`

Scanner commit increments local picked quantity and reduces local stock through
the pick service. It reduces `In Stock`, reduces `Allocated`, recalculates
`Sellable`, creates `pick_stock_reduction` stock movements, and never writes
WooCommerce. Scanner commit accepts an `idempotency_key`; replaying the same
key does not reduce stock a second time.

## SKU Orders Report

- `GET /api/reports/sku-orders`
- `GET /api/reports/sku-orders/summary`
- `GET /api/reports/sku-orders/export`

This report is read-only over local order snapshots.

## Route Local Management

Local route management now includes:
- `PATCH /api/routes/{route_id}`
- `POST /api/routes/{route_id}/stops/reorder`
- `PATCH /api/routes/{route_id}/stops/{stop_id}`
- `GET /api/routes/{route_id}/map`
- `POST /api/routes/{route_id}/geocode/preview`
- `POST /api/routes/{route_id}/geocode/commit`
- `POST /api/routes/{route_id}/optimize/preview`
- `POST /api/routes/{route_id}/optimize/commit`

Map/geocoding/optimization endpoints are provider-architecture endpoints. They
do not expose keys and default to disabled/no-op behavior unless backend
provider configuration is explicitly added later.

## Items

### GET /api/items

List items with search, category, active/inactive, and include non-inventory filters.

Implemented query params:
- `search`
- `category`
- `warehouse`
- `inventory_location`
- `brand`
- `active`
- `include_non_inventory`
- `include_facets` (default `true`; optimized clients use `false` and load
  `GET /api/items/facets` once)
- `woo_sync_status`
- `woo_product_id`
- `woo_variation_id`
- `data_quality`: one or more comma-separated values from `missing_barcode`,
  `missing_brand`, `missing_cost`, `unmapped`, `receiving`, and
  `missing_location`; multiple values use OR semantics
- `page` and `page_size` (`page_size` is limited to 100)
- `sort_by`: `sku`, `barcode`, `description`, `brand`, `category`, `in_stock`,
  `allocated`, `sellable`, `unit_cost`, `sales_price`, or `updated_at`
- `sort_direction`: `asc` or `desc`

Returns canonical CSV-style field names plus internal display fields such as
`id`, `active`, `nonInventory`, `imageUrl`, `wooProductId`, and
`wooVariationId`. The list envelope includes `page`, `page_size`, `total`,
`total_pages`, `returned_count`, `has_previous`, `has_next`, and full-catalog
`facets` for raw category and brand filter values. Facets are not limited to
the current page; clients may decode entities for display but must send the raw
facet value back to the API. For backward
compatibility, omitting both pagination parameters still returns the complete
filtered list. A requested page beyond the filtered result is clamped to the
last valid page (or page 1 for an empty result).

### GET /api/items/facets

Return the distinct, sorted full-catalog category and brand filter values.
The frontend keeps this metadata separately from paginated item rows so page
changes do not repeat the facet queries. Operational stock quantities are not
included or cached by this endpoint.

### GET /api/items/{id}

Return one item, including location stock summary.

### GET /api/items/{id}/locations

List stock-location rows for one item. These rows are the operational source for
`In Stock`, `Allocated`, `Sellable`, and `On Order`.

### GET /api/items/{id}/activity

Returns one chronological item timeline across stock movements, notes, item
imports, receipts, counts, transfers, adjustments, allocations, picks,
fulfillments, and order lines. Supports `type`, `start_date`, `end_date`,
`limit` (capped at `200`), and `offset`. Type and date predicates are applied
inside PostgreSQL. The service calculates the exact cross-source `total`, loads
only the top `offset + limit` rows from each applicable source, merges those
bounded results chronologically, and returns the existing `activity`, `total`,
`limit`, and `offset` fields.

### POST /api/items/{id}/locations

Create or activate an item-location row. This endpoint changes location
metadata only; stock quantities must be changed through receiving, cycle count,
fulfillment, transfer, or adjustment workflows.

### PATCH /api/items/{id}/locations/{item_location_id}

Update item-location metadata such as default flag, active flag, labels, and par
level. This endpoint does not directly change stock.

## Stock by Location v2

- `GET /api/inventory/locations`
- `GET /api/inventory/locations/export`
- `POST /api/inventory/transfers`
- `GET /api/inventory/transfers`
- `GET /api/inventory/transfers/{id}`
- `POST /api/inventory/adjustments`
- `GET /api/inventory/adjustments`
- `GET /api/inventory/adjustments/{id}`

Transfers and adjustments are local-only. They create stock movements and keep
item aggregate totals reconciled with active item-location rows. They do not
write WooCommerce.

Transfer and adjustment commit bodies may include `idempotency_key`.

Each adjustment line must provide `new_quantity`, the absolute final location
quantity. Delta-style `quantity_change` input is rejected. `new_quantity`
accepts zero; `reason` is optional and blank values are normalized to
`Manual stock adjustment` in the audit record.
The commit still rejects negative stock and any final quantity below the
location's allocated quantity.

`GET /api/inventory/transfers` and `GET /api/inventory/adjustments` accept
`page` (default `1`) and `page_size` (default `50`, maximum `100`). Their
existing filters are applied before PostgreSQL calculates the exact `total`.
Responses add `page`, `page_size`, `total_pages`, `returned_count`,
`has_previous`, and `has_next` without changing the existing collection keys.

`GET /api/inventory/locations` accepts `page` (default `1`) and `page_size`
(default `20`, maximum `100`). It optionally accepts `item_ids` as a
comma-separated list of positive inventory item IDs. This allows a paginated
catalog view to request location rows only for the current page. Filtering and
the exact `total` are calculated in PostgreSQL before rows are paged. The
response also includes `total_pages`, `returned_count`, `has_previous`, and
`has_next`; pages beyond the result are clamped to the final page. The separate
`/locations/export` endpoint remains an unbounded filtered CSV export.
Each location row is self-contained for paginated displays: alongside its
location-level `active` flag, it includes the product-owned `brand`, `category`,
`unit_cost`, and `item_active` fields.

### POST /api/items

Create a manual local item. Future behavior may optionally push to WooCommerce, but not in MVP.

Implemented for local Pongo Inventory OS persistence only. SKU is required.
Calculated fields are recomputed before save:
- `Sellable = In Stock - Allocated`
- `Under Par = In Stock <= Par Level`
- `Storage Volume = Storage Length * Storage Width * Storage Height`

### PATCH /api/items/{id}

Update Pongo OS-owned item fields.

Implemented for local Pongo Inventory OS persistence only. Calculated fields are
recomputed before save.

### GET /api/items/export

Export inventory item CSV.

Implemented. Exports filtered rows using the exact canonical inventory CSV
header order from `docs/CSV_COLUMNS.md`. Internal fields are not included.

## Guided Item Import Workspace

The Items UI uses the following authenticated, backend-owned contract. Full
business rules and request flow are in `docs/ITEM_IMPORTS.md`.

### GET /api/items/import/schema

Returns the versioned outcomes, supported fields, labels, types, aliases,
required fields, examples, upload limit, and preview lifetime.

### GET /api/items/import/templates/{outcome}

Returns an outcome-specific CSV. `outcome` is `add_items`, `update_items`,
`update_stock`, or `starting_inventory`. `include_existing=true` is supported
for `update_items` and `update_stock`; the latter exports one exact current total
per SKU. Metadata templates never include quantities.

### POST /api/items/import/previews

Accepts multipart `outcome` and `file`. Validates the upload boundary, persists
the exact source, source hash, actor, detected columns, suggested mappings, and
all normalized preview rows. For `update_stock`, SKU and In stock are required;
distinct location rows are summed by SKU, warehouse/location and extra export
columns are ignored, and both source-row and SKU counts are returned. Returns a
resumable `preview_id` and summary.

### GET /api/items/import/previews/{preview_id}

Returns preview metadata, mapping, summary, expiry, status, and committed result.
Previews are actor-scoped.

### GET /api/items/import/previews/{preview_id}/rows

Server-side row pagination and optional `state` / `search` filters. Page size is
limited to 100.

### PATCH /api/items/import/previews/{preview_id}/mapping

Accepts the complete source-to-destination mapping, `allow_blank_clears`, and
an optional mapping-profile id. Revalidates all rows.

### PATCH /api/items/import/previews/{preview_id}/rows/{row_number}

Accepts field-level `values` corrections and/or `excluded`. Revalidates the
preview and preserves the original source row.

### POST /api/items/import/previews/{preview_id}/revalidate

Revalidates persisted rows against current item/location data.

### POST /api/items/import/previews/{preview_id}/commit

Requires JSON `idempotency_key`. Stops on a stale preview. Metadata commits are
transactional and stock-invariant. `update_stock` refuses exclusions and true
safety errors, records unknown SKUs as nonblocking skips, skips totals that
already match, and commits all matched changes as one locked, idempotent
transaction and stock adjustment. Every matched item is locked before the final
stale check, including unchanged rows. It returns `stock_adjustment_id`,
`stock_units_delta`, `skipped_count`, `source_row_count`, and `sku_count`. When live writeback is enabled it also returns
`woo_stock_sync_job_id` for the queued chunked sync. Starting inventory delegates
to the guarded opening-balance mutation and creates audited movement rows.

### POST /api/items/import/previews/{preview_id}/cancel

Marks an uncommitted preview cancelled.

### /api/items/import/profiles

Authenticated-user CRUD for reusable, outcome-specific mapping profiles:
`GET`, `POST`, `PATCH /{profile_id}`, and `DELETE /{profile_id}`.

### Legacy item import compatibility

The following two endpoints are retained for canonical Zenventory-format files.
New Items UI work must use the persisted preview endpoints above.

### POST /api/items/import/preview

Preview a Zenventory-compatible item CSV import.

Implemented. Accepts `multipart/form-data` with a `file` upload. This endpoint
parses and validates the CSV but does not write to the database.

Header rules:
- Canonical column names from `docs/CSV_COLUMNS.md` are required.
- The legacy product export header that omits `Manufacturer` and uses
  `Default Lead Time (Days)` is accepted; `Manufacturer` is defaulted blank and
  lead time is normalized to `Default Lead Time Days`.
- Comma-delimited and tab-delimited item import files are accepted.
- Header whitespace is trimmed.
- Column names are case-sensitive.
- Missing canonical columns reject the file.
- Extra columns are ignored and returned as warnings.

Matching rules:
- SKU exact match is checked first.
- Barcode exact match is checked second when Barcode is present.
- If SKU and Barcode match two different existing items, the row is invalid.

Calculated fields are recomputed during preview:
- `Sellable = In Stock - Allocated`
- `Under Par = In Stock <= Par Level`
- `Storage Volume = Storage Length * Storage Width * Storage Height`

Returns:
- `total_rows`
- `valid_rows`
- `invalid_rows`
- `create_count`
- `update_count`
- `skipped_count`
- `warnings`
- `errors`
- `preview_rows`

### POST /api/items/import/commit

Commit a Zenventory-compatible item CSV import.

Implemented. Accepts the same `multipart/form-data` `file` upload as preview.
The backend revalidates and reparses the file before writing. Valid rows create
or update local Pongo Inventory OS items only. The endpoint does not call
WooCommerce and does not run receiving, cycle count, allocation, picking, or
other stock-changing workflows.

The commit writes an `import_jobs` record plus `import_errors` rows for failed
CSV rows.

Returns:
- `import_job_id`
- `total_rows`
- `created_count`
- `updated_count`
- `skipped_count`
- `failed_count`
- `errors`

### POST /api/items/sync/woocommerce

Trigger backend WooCommerce product and variation sync.

Replaced by the read-only WooCommerce integration endpoints under
`/api/integrations/woocommerce`.

Returns:
- created_count
- updated_count
- skipped_count
- error_count
- errors

### POST /api/items/{id}/remap

Link or relink a local item to a WooCommerce product or variation.

Not implemented yet.

Accepted identifiers:
- Woo Product ID
- Woo Variation ID
- SKU
- Barcode
- Product name

## Import Jobs

### GET /api/import-jobs

List CSV import jobs, newest first.

Implemented for item and location CSV imports. Supports `outcome`, `status`,
`item_imports_only`, and bounded `limit` filters. Existing callers that omit
`page` and `page_size` continue to receive the legacy array (bounded by
`limit`, maximum `500`). Supplying either `page` or `page_size` opts into the
server-paged response:

- `jobs`
- `total`
- `page`
- `page_size` (default `50`, maximum `100`)
- `total_pages`
- `returned_count`
- `has_previous`
- `has_next`

Filters and the exact total are evaluated in PostgreSQL. Results are ordered by
`created_at DESC, id DESC`, and requests beyond the final page resolve to the
last available page.

### GET /api/import-jobs/{id}

Return one import job with row-level errors.

Implemented for item and location CSV imports.

### GET /api/import-jobs/{id}/failed-rows

Download failed rows as CSV.

Implemented. The CSV uses the fields for the import outcome plus Error Code,
Error Field, Error Message, and Suggested action columns.

### GET /api/import-jobs/{id}/source-file

Downloads the exact UTF-8 source CSV captured by the guided preview.

### GET /api/import-jobs/{id}/changes

Returns field-level before/after metadata changes with item, filename, actor,
and timestamp. This detail is server-paged with `page` (default `1`) and
`page_size` (default `50`, maximum `100`). The response contains `changes`,
`total`, `page`, `page_size`, `total_pages`, `returned_count`, `has_previous`,
and `has_next`. Each change retains `id`, `item_id`, `sku`, `field`, `before`,
`after`, `source_filename`, `created_by`, and `created_at`.

### POST /api/import-jobs/{id}/rollback

Guarded all-or-nothing rollback for completed `update_items` metadata. Refuses
the rollback if any imported field has changed. Never deletes items or reverses
inventory movements.

## WooCommerce Integration

All WooCommerce integration endpoints are backend-only. The React frontend calls
the Pongo backend and never calls WooCommerce directly. Authenticated staff may
submit credentials to the backend, which encrypts them in PostgreSQL and never
returns them in API responses.

Backend environment variables used by WooCommerce integration. The REST
credentials and exact allowed host may use these as a deployment fallback; UI
values take precedence after a successful save. The webhook secret may remain
blank while the receiver is disabled:
- `WOOCOMMERCE_CONFIGURATION_ENCRYPTION_KEY` (required for UI-saved production credentials)
- `WOOCOMMERCE_TIMEOUT_SECONDS`
- `WOOCOMMERCE_PAGE_SIZE`
- `WOOCOMMERCE_ORDER_SYNC_PAGE_SIZE`
- `WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES`
- `WOOCOMMERCE_ORDER_RECONCILIATION_ENABLED`
- `WOOCOMMERCE_ORDER_RECONCILIATION_INTERVAL_SECONDS`
- `WOOCOMMERCE_ORDER_RECONCILIATION_STALE_AFTER_SECONDS`
- `WOOCOMMERCE_ORDER_RECONCILIATION_LOOKBACK_HOURS`
- `WOOCOMMERCE_ORDER_RECONCILIATION_STATUSES`
- `WOOCOMMERCE_SYNC_ERROR_RETENTION_DAYS` (default `90`)
- `WOOCOMMERCE_WEBHOOK_ENABLED`
- `WOOCOMMERCE_WEBHOOK_SECRET`
- `WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES`

### GET /api/integrations/woocommerce/status

Return safe configuration status.

Response:
- `configured`
- `base_url_present`
- `consumer_key_present`
- `consumer_secret_present`
- `configuration_source`
- `configuration_updated_by`
- `configuration_updated_at`
- `webhook_enabled`
- `webhook_configured`
- `webhook_secret_present`
- `last_webhook_delivery`
- `order_reconciliation`
- `message`

No secret values are returned.

Webhook configuration is independent from REST credential configuration and
writeback enablement. The response reports only enable/configuration/presence
booleans and safe last-delivery metadata.

Optional query param:
- `check=true`: performs safe read-only product and processing-order requests to verify
  connectivity when credentials are configured.

### POST /api/integrations/woocommerce/configuration

Verify and save the WooCommerce REST connection in encrypted backend storage.

Request:
- `base_url`: required HTTPS store URL (`http` is accepted only for localhost)
- `consumer_key`: required when no key is already configured; blank preserves it
- `consumer_secret`: required when no secret is already configured; blank preserves it
- `allow_host_change`: defaults to `false`; must be explicitly `true` when the
  requested store host differs from the currently authorized host

The backend tests the supplied credentials with read-only product-list and
processing-order-list requests before atomically updating the encrypted
singleton configuration row. After saving, it schedules one bounded open-order
quick sync (up to 25 newest orders per open status); the full server
reconciliation still imports the complete backlog. The response returns only the store
URL, host, presence booleans, and a success message. It never returns either
credential. A host mismatch fails before the connection request unless the
operator explicitly authorizes replacement. An authorized replacement updates
the base URL and exact allowed host together only after verification; it never
changes writeback feature flags.

### POST /api/integrations/woocommerce/products/preview

Fetch WooCommerce products and variations through the backend WooCommerce REST
API client and return what would happen locally without database writes.

Request:
- `include_statuses`: defaults to `["publish"]`
- `limit`: defaults to `500`
- `page`: optional Woo parent-product page for batched catalog reads
- `per_page`: defaults to `50`, maximum `100`
- `blocked_skus`: normalized duplicate Woo SKUs that commit must leave unchanged
- `created_by`: defaults to `system`

Preview does not:
- create or update local items
- create stock movements
- write to WooCommerce

Response:
- `configured`
- `total_remote_records`
- `create_count`
- `update_count`
- `matched_count`
- `skipped_count`
- `conflict_count`
- `error_count`
- `warnings`
- `errors`
- `preview_rows`
- `page`, `next_page`, `has_more`
- `unmatched_local_count`, `unmatched_local_skus` (populated after the final commit batch)

Preview row fields:
- `remote_type`
- `woo_product_id`
- `woo_variation_id`
- `sku`
- `barcode`
- `description`
- `category`
- `brand`
- `price`
- `regular_price`
- `stock_status`
- `stock_quantity_snapshot`
- `local_item_id`
- `action`
- `status`
- `warnings`
- `errors`

### POST /api/integrations/woocommerce/products/import-new

Primary no-CSV product intake. The endpoint scans WooCommerce once, filters out
already mapped simple products and variations, creates or links only the missing
sellable records, and returns `setup_item_ids` for the frontend setup sequence.
After the first successful reconciliation it passes a saved `modified_after`
cursor (with overlap) and fetches only unknown variation IDs. Missing SKU or
barcode does not block creation; the local item is marked `needs_setup`.

If the Woo scan fails, the endpoint returns `503` with “WooCommerce is
temporarily unavailable. No products were changed. Try again.” and advances no
cursor.

Response fields include `sync_run_id`, `status`, `checked_since`, counts,
`created_item_ids`, `setup_item_ids`, warnings/errors, and a user-facing
`message`.

`GET /api/items?latest_woo_import=true` returns only the exact item IDs created
by the newest `new_products` run that added products. Empty import checks do not
replace that filter target.

Action values:
- `create`
- `update`
- `match_only`
- `skip`
- `conflict`
- `error`

### POST /api/integrations/woocommerce/products/commit

Fetch products/variations again, validate again, and create/update only local
Pongo OS items. This endpoint never writes to WooCommerce.

Commit behavior:
- Creates one local item for each sellable simple product with a SKU.
- Creates one local item for each sellable variation with a SKU.
- Reuses an existing Woo ID mapping, otherwise matches by unique SKU, then by
  unique Barcode only when SKU did not match.
- Attaches only Woo mapping and snapshot metadata to existing items; existing
  item IDs and Pongo-owned fields are preserved.
- Skips blank-SKU records.
- Skips duplicate local/remote SKUs and mapping conflicts.
- Reports local items still unmatched after the final batch without changing them.
- Stores sync run history and sync errors.
- Does not create stock movements.
- Does not overwrite local In Stock, Allocated, Warehouse, Inventory Location,
  Default Location, Unit Cost, Par Level, reorder fields, or other manual
  operational fields.
- Stores Woo stock only in `woo_stock_quantity_snapshot`.

### GET /api/integrations/woocommerce/sync-runs

List WooCommerce sync runs.

Filters:
- `sync_type`
- `status`
- `date_from`
- `date_to`
- `page` (defaults to `1`)
- `page_size` (defaults to `50`, maximum `100`)

Runs are ordered by newest `started_at` and then newest ID. The response keeps
the existing `sync_runs` and `total` fields and adds `page`, `page_size`,
`total_pages`, `returned_count`, `has_previous`, and `has_next`. `total` is the
complete filtered count, not the number returned on the current page. A page
beyond the result is clamped to the last valid page (or page 1 when empty).

### GET /api/integrations/woocommerce/sync-runs/{id}

Return sync run detail and one bounded page of row-level sync errors. Use
`error_page` (default `1`) and `error_page_size` (default `50`, maximum `100`).
The existing `errors` field contains only that page, ordered newest-first, and
the response also reports `errors_total`, `errors_page`, `errors_page_size`,
`errors_total_pages`, `errors_returned_count`, `errors_has_previous`, and
`errors_has_next`. The run-level `error_count` remains the historical summary
recorded when the run finished; `errors_total` is the exact count of retained
detail rows currently present in the database.

### GET /api/integrations/woocommerce/orders/fetch-jobs

List manual/background order-fetch jobs with exact database-backed paging.
Use `page` (default `1`) and `page_size` (default `20`, maximum `100`). The
response retains `sync_runs` and `total` and adds `total_pages`,
`returned_count`, `has_previous`, and `has_next`. Results include only order
fetch jobs and are ordered newest-first. The deprecated `limit` parameter is
still accepted as a page-size alias for older clients.

### POST /api/integrations/woocommerce/orders/preview

Fetch eligible WooCommerce orders through the backend WooCommerce REST API
client and return what would happen locally without database writes.

Request:
- `include_statuses`: defaults to `["processing", "on-hold", "pending"]`
- `limit`: defaults to `500`
- `after`, `before`, `modified_after`, `modified_before`: optional WooCommerce date filters
- `created_by`: defaults to `system`

Preview does not:
- create or update local orders
- allocate, reserve, pick, or route order lines
- change item In Stock or Allocated quantities
- create stock movements
- write to WooCommerce

Matching rules for order lines:
- Woo Product ID + Woo Variation ID
- exact SKU
- exact Barcode from order line metadata
- conflict when those identifiers match different local items

Availability is a read-only snapshot:
- `sellable_snapshot = item.In Stock - item.Allocated`
- `available` when sellable covers ordered quantity
- `partial` when some sellable quantity exists but not enough
- `unavailable` when a matched item has no sellable quantity
- `unknown` for unmatched or conflict lines

### POST /api/integrations/woocommerce/orders/commit

Fetch eligible WooCommerce orders again, validate again, create/update local
`orders` and `order_items` rows, and run safe local FIFO auto-allocation for
active `processing` orders. This endpoint never writes to WooCommerce and never
reduces local In Stock.

Commit behavior:
- Stores a local order snapshot for eligible open WooCommerce orders.
- Upserts order lines by Woo line item ID.
- Stores unmatched and conflict lines for staff review instead of creating
  inventory items.
- After all snapshots in the batch are stored, evaluates processing orders by
  `date_created ASC`, then local order ID ASC; missing dates sort last.
- Reserves all currently available quantity for the oldest competing order,
  including partial quantities, before evaluating newer orders.
- Creates posted allocation records/lines and increases local Allocated for
  full or partial reservations.
- For remaining shortages, unmatched lines, conflicts, partial stock, or no
  location stock, records allocation exception status/reasons for Allocate.
- Non-processing snapshots do not reserve stock or enter operational queues.
- When an existing allocated order changes to a non-processing WooCommerce
  status, releases its remaining unpicked allocation before rerunning FIFO.
- Reuses `woocommerce_sync_runs` with `sync_type = orders`.
- Stores order/line context in `woocommerce_sync_errors` for unmatched and
  conflict rows. Identical errors are stored once per sync run using a database
  uniqueness constraint, while each run keeps its own audit detail. Every
  committed catalog or order sync removes details older than the configured
  retention period, including successful runs that add no new errors.
- Summary responses include `auto_allocated_count`,
  `allocation_exception_count`, `unmatched_line_count`,
  `conflict_line_count`, and `pick_ready_count`.

### POST /api/integrations/woocommerce/orders/quick-sync

Fetch the newest WooCommerce orders per requested status and upsert local order
snapshots when an operator explicitly requests an immediate import. The
frontend does not call this endpoint on a timer. The backend also reuses the
same bounded workflow once immediately after credentials are saved. The backend scheduler owns
normal reconciliation and uses the fully paginated order-sync path so a large
backlog cannot be clipped. Retrieval remains newest first, but the subsequent
local allocation pass evaluates all eligible processing orders oldest
`date_created` first. It is still read-only against WooCommerce: it may
increase local Allocated, but it does not pick, fulfill, reduce In Stock, or
write back.

Query parameters:
- `per_status_limit`, default `10`, maximum `25`

Example operator payload:

```json
{
  "include_statuses": ["processing", "on-hold", "pending"],
  "limit": 30,
  "created_by": "operator"
}
```

Signed webhooks are the immediate ingestion path; the server reconciliation
loop is the durable recovery path.

### POST /api/integrations/woocommerce/orders/history-import

Queue or resume the full read-only WooCommerce order-history import across all
order statuses, including store-defined custom statuses.
The endpoint returns HTTP `202` with the durable sync-run row. Repeated requests
reuse an active job; a failed job resumes from its last committed status/page.
The WooCommerce worker processes one page at a time.

This import creates reporting-only historical order and line snapshots. It does
not allocate, release, pick, fulfill, route, create stock movements, change
inventory quantities, or call a WooCommerce write endpoint. Progress and
verified local date coverage are also exposed by
`GET /api/integrations/woocommerce/status` as `order_history_import` and
`order_history_coverage`. Coverage includes `source_absent_snapshot_count`;
these retained audit rows no longer contribute to intelligence after a verified
rerun confirms WooCommerce no longer returns them.

### POST /api/integrations/woocommerce/webhooks/orders

Receive WooCommerce webhook deliveries. The receiver is disabled by default
and fails closed unless all receiver configuration is present:

- `WOOCOMMERCE_WEBHOOK_ENABLED=true`
- `WOOCOMMERCE_WEBHOOK_SECRET` contains a distinct secret of at least 32 UTF-8
  bytes
- `WOOCOMMERCE_ALLOWED_HOST`, or the host from `WOOCOMMERCE_BASE_URL` when the
  explicit allowlist is blank, identifies the allowed webhook source host
- `WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES` sets the body limit; the default is
  `1048576` bytes and the runtime clamps it to 1 KiB through 10 MiB

The delivery URL must be publicly reachable over HTTPS, for example:

```text
https://<backend-host>/api/integrations/woocommerce/webhooks/orders
```

Localhost URLs cannot receive deliveries from a remote WooCommerce staging or
production site.

WooCommerce sends these expected delivery headers:

- `X-WC-Webhook-Source`
- `X-WC-Webhook-Topic`
- `X-WC-Webhook-Resource`
- `X-WC-Webhook-Event`
- `X-WC-Webhook-Signature`
- `X-WC-Webhook-ID`
- `X-WC-Webhook-Delivery-ID`

The backend computes base64-encoded HMAC-SHA256 over the exact raw request body
using `WOOCOMMERCE_WEBHOOK_SECRET` and compares it in constant time with
`X-WC-Webhook-Signature`. It then verifies that topic/resource/event agree and
that the normalized `X-WC-Webhook-Source` host exactly matches the allowlisted
host. JSON must use `Content-Type: application/json` and contain a positive
order `id`, a nonblank `status`, and a `line_items` array.

WooCommerce sends an unsigned setup ping when a webhook is first activated.
The receiver accepts only the exact body `webhook_id=<positive integer>` with no
signature as a no-op and returns `status = ready`. It creates no ledger, order,
allocation, or notification event.

Phase-1 topic behavior:

- Authenticated `order.created` imports the REST-shaped order payload through
  the existing local order-sync pipeline.
- An `order.created` snapshot whose WooCommerce `date_modified` is older than or equal to
  the existing local order snapshot is audited with `processing_status =
  ignored`; it cannot regress newer REST or webhook data and does not emit a
  staff event.
- Any other authenticated, internally consistent topic is recorded with
  `processing_status = ignored` and returns HTTP 200 without importing an order.
- A processing-order import runs the same audited queue-wide FIFO allocation as
  manual and quick sync. It can increase local `Allocated`, but does not reduce
  `In Stock`, create a stock movement, write WooCommerce, or send a customer
  notification.

Every authenticated JSON delivery is identified by the unique tuple
`(webhook_id, delivery_id, payload_sha256)`. Replaying a terminal delivery
increments its attempt count and returns `status = duplicate` without importing,
allocating, or notifying again. The raw customer payload is not duplicated in
the delivery ledger.

Response fields:

- `status`: `ready`, `processed`, `processed_with_errors`, `ignored`, or
  `duplicate`
- `duplicate`
- `delivery_id`
- `event_id`: immutable `woocommerce_order_events.id` when a new local order was
  published to the staff feed; otherwise `null`
- `woo_order_id`
- `local_order_id`
- `sync_run_id`
- `created_order`
- `message`

Validation errors use safe messages and do not expose the secret. Important
status codes are `400` for malformed JSON or inconsistent headers, `401` for a
missing/invalid signature, `403` for a disallowed source host, `413` for an
oversized body, `415` for a non-JSON media type, `422` for an invalid order
shape, and `503` when the receiver is disabled/misconfigured or a transaction
cannot be committed.

WooCommerce’s current delivery and header behavior is documented in the
[WooCommerce webhook API documentation](https://developer.woocommerce.com/docs/apis/rest-api/v2/webhooks)
and its [webhook implementation reference](https://woocommerce.github.io/code-reference/files/woocommerce-includes-class-wc-webhook.html).

### GET /api/integrations/woocommerce/webhooks/events

Return a read-only cursor feed used by the internal staff new-order notice.

Query parameters:

- `after_id`: exclusive immutable order-event cursor, default `0`; negative values are
  treated as `0`
- `limit`: default `50`, clamped to `1..100`
- `initialize`: boolean, default `false`; when `true`, returns no events and
  sets `next_after_id` to the current order-event high-water mark so a new UI session
  does not announce historical orders

Only immutable `woocommerce_order_events` rows created atomically with a
successful new local order appear in `events`. Ignored, duplicate, failed,
setup-ping, update-only, and already-local deliveries never produce an outbox
row or staff new-order event. A failed delivery that later succeeds receives a
new immutable event ID at successful commit time, so an earlier feed cursor
cannot skip it.

Event fields:

- `id`
- `topic`
- `woo_order_id`
- `local_order_id`
- `woo_order_number`
- `woo_status`
- `local_status`
- `customer_name`
- `currency`
- `total`
- `created_order`
- `received_at`

Response cursor fields:

- `latest_event_id` is the informational maximum immutable order-event ID.
- `next_after_id` is the safe exclusive cursor for the next request. Consumers
  must advance with this field, not directly with `latest_event_id`.
- `has_more` means another event page remains. Consumers must keep requesting
  with `after_id = next_after_id` until it becomes false.

The frontend begins a session with `initialize=true`, then polls globally every
15 seconds while the document is visible and also on focus/visibility changes.
The feed does not acknowledge events globally, mutate orders, call
WooCommerce, or send outbound/customer notifications.

### GET /api/orders/open

List active local open orders whose latest stored WooCommerce status is exactly
`processing`. Results are newest first. Fully auto-allocated processing orders
can appear here and in Pick Orders at the same time. Pending, on-hold, failed,
cancelled, refunded, and completed snapshots are excluded from this endpoint.

Filters:
- `search`
- `order_number`
- `customer`
- `containing_item`
- `warehouse`
- `availability_status`
- `matched_status`
- `page`
- `page_size` (maximum `100`)

`search` matches order number, customer name/email/phone, order-line SKU,
barcode or name, and the matched local inventory item's SKU, barcode or
description. Rows include allocation, pick, completion, can-pick/can-complete,
completed-without-picking, and stock-reduction fields. Queue rows also expose
`shipping_zip`, `company`, `ship_from`, `item_names`, and
`total_quantity_fulfilled` for the Open Customer Orders grid.

When pagination is requested, filtering and workflow membership are evaluated
in PostgreSQL before the page is selected. The response includes `page`,
`page_size`, `total_pages`, `returned_count`, `has_previous`, and `has_next`;
summary counts describe the complete filtered queue. Public list requests
default to page `1` with `20` rows. CSV export uses the same filtered service
through an explicit complete-list internal call, so exports are never clipped.
Queue pages defer the full stored WooCommerce payload. The list query extracts
only its small `shipping_lines` value for `shipping_via`; full raw payloads are
loaded only by workflows that explicitly require them.

### GET /api/orders/allocate

List processing orders that need allocation attention: shortages, unmatched
lines, conflicts, unavailable location stock, partial allocation, or failed
auto-allocation. Fully allocated orders are excluded.

Supports `page` and `page_size` with the same response metadata as Open Orders.

### GET /api/orders/pick

List processing orders whose required inventory lines are fully allocated and
are managed by picking. Partially allocated orders remain in Allocate. Fully
picked orders leave this queue and remain correctable through Open Orders'
audited Unpick action. Picking happens in this view and reduces local stock.
Queue rows also include `order_source`, `shipping_city`,
`shipping_state`, `shipping_via`, `skus`, `total_quantity_ordered`,
`total_quantity_allocated`, and `total_quantity_picked` for the manual picking
interface.

Supports `page` and `page_size` with the same response metadata as Open Orders.

### GET /api/orders/{id}

Return one local order with line-level match and availability detail. The detail
payload also includes stored billing, shipping, customer, payment and order
totals; each line exposes `unit_price`, `line_tax`, and `line_total` for the
Pongo invoice print view.

### POST /api/orders/bulk/complete

Mark selected local Open Orders completed. Picked orders complete without a
second stock reduction. Unpicked orders complete without reducing unpicked
stock and release remaining allocation. The response reports per-order success
or failure plus `woo_sync_status` and `woo_writeback_queue_id` for each order.

### POST /api/orders/bulk/unpick

Reverse all reversible picked quantities for selected active orders. The
operation restores In Stock and Allocated at original pick locations, updates
order and pick records, and creates `unpick_stock_restoration` movement and
audit rows. Completed or fulfilled orders are rejected, and reversed pick lines
cannot be reversed again. An optional `idempotency_key` makes a network retry
return the first result without restoring stock twice.

### GET /api/orders/{id}/workflow

Return the order, line statuses, workflow visibility flags, allocation
preview/status, pick status, stock-reduction status, and history references.

### POST /api/orders/{id}/auto-allocate/preview

Evaluate a local order for auto-allocation without writing data.

### POST /api/orders/{id}/auto-allocate/commit

Commit local auto-allocation for one active processing order. Available stock
may be reserved partially; unresolved quantities remain in Allocate. This
endpoint creates allocation records and audit events, increases local
Allocated, and never reduces In Stock or writes WooCommerce. Normal queue-wide
reconciliation uses `POST /api/allocations/auto/commit` so competing orders are
processed in FIFO order.

### POST /api/orders/{id}/complete/preview

Preview local order completion. `completion_mode` can be `complete`,
`complete_picked`, or `complete_without_picking`. `complete` selects the safe
path from current server-side pick state.

### POST /api/orders/{id}/complete/commit

Complete or close a local order.

`complete` is the normal Open Orders command. It completes a fully picked order
without reducing stock again. For any not-fully-picked order, it releases
remaining allocation and completes without reducing unpicked stock. The UI
must warn the staff member before sending that request.

`complete_picked` marks an already picked order completed/closed and does not
reduce stock again.

`complete_without_picking` marks the order completed/closed, releases remaining
unpicked allocation, creates an audit event that stock was not reduced, and
does not reduce stock.

Unless `queue_woo_status_update` is explicitly false, the endpoint creates,
approves, and sends an audited queue item that patches the linked WooCommerce
order to `completed`. The response includes `woo_sync_status`,
`woo_writeback_queue_id`, and `woo_sync_error`. Local completion remains
recorded if WooCommerce is unavailable so the failed queue item can be audited
and retried without repeating stock actions.

### GET /api/orders/open/export

Export filtered local open orders as CSV.

### GET /api/orders/completed

Read-only list of local orders whose local completion state is completed,
closed, fulfilled, partially fulfilled, or completed without picking.

Filters:
- `local_status`
- `date_from`
- `date_to`
- `customer_email`
- `woo_order_number`
- `sku`
- `barcode`
- `search`
- `page` (defaults to `1`)
- `page_size` (defaults to `20`, maximum `100`)

Rows include Woo order identifiers/status, local status, customer name/email,
order total, order dates, line count, fulfilled line count, total ordered,
allocated, picked, fulfilled, remaining to fulfill, and fulfilled value.
All filters and the exact `total` are evaluated in PostgreSQL before rows are
paged. The response also includes `total_pages`, `returned_count`,
`has_previous`, and `has_next`; pages beyond the result are clamped to the
final page.

### GET /api/orders/completed/export

Export every matching completed/partially completed order line as CSV using the
same filters. CSV export is not limited by list pagination.

CSV header order:
- Woo Order Number
- Woo Order ID
- Woo Status
- Local Status
- Customer Name
- Customer Email
- Order Total
- Line SKU
- Line Barcode
- Line Name
- Quantity Ordered
- Quantity Allocated
- Quantity Picked
- Quantity Fulfilled
- Remaining To Fulfill
- Fulfillment Status
- Fulfilled Value
- Date Created
- Date Modified

## Allocations

Allocation reserves local Pongo OS sellable inventory for active processing
orders.
Allocation is local-only: it does not write WooCommerce, reduce In Stock, pick
orders, create routes, fulfill orders, or send outbound/customer notifications.

Auto-allocation uses the same local reservation rules after WooCommerce order
sync and whenever a stock-changing workflow makes sellable stock available.
Only active `processing` orders participate. The queue is ordered by
WooCommerce `date_created ASC`, then local order ID ASC; missing dates sort
after dated orders. It may split one order line across multiple active
item-location rows, preferring the default location and then highest sellable
quantity. The oldest order receives any partial quantity before a newer order
can reserve the same stock.

### POST /api/allocations/auto/commit

Run queue-wide FIFO allocation and commit the result.

The operation is idempotent for already reserved quantities: it evaluates only
remaining unallocated quantities. PostgreSQL runs serialize through a
transaction-level allocation lock, and each order is isolated so a failed order
does not partially commit its allocation plan.

Response fields:

- `status`
- `attempted_orders`
- `allocated_orders`
- `partially_allocated_orders`
- `exception_orders`
- `total_quantity_allocated`
- `allocation_ids`
- `errors`

The same FIFO reconciliation runs automatically after order sync, direct/bulk/
scanner receiving, standard/scanner adjustments, standard/scanner cycle count,
completion releases, and synchronized non-processing WooCommerce status
changes that release unpicked allocations.

### GET /api/allocations/exceptions

List line-level allocation exceptions for processing orders. By default the
endpoint returns only lines with unresolved quantities; use
`include_fully_allocated=true` to include 100% allocated matched lines.
Zero-quantity WooCommerce lines retained only as retired audit history are
excluded. A retired line remains visible when it still carries allocated,
picked, fulfilled, or stock-reduced quantity, or an explicit reconciliation
exception.

Filters:

- `search`: order number, customer, SKU, barcode, or description
- `warehouse`
- `ordered_from`
- `ordered_to`
- `include_fully_allocated`
- `view`: `orders` (line pagination) or `items` (item-group pagination)
- `item_id`: optional matched-item selector for a paged affected-order drill-down
- `unmatched_line_id`: optional unmatched-group selector for a paged drill-down
- `page` (defaults to `1`)
- `page_size` (defaults to `20`, maximum `100`)

Each line includes order and item identifiers, ordered date, customer, SKU,
barcode, description, warehouse/location, ordered, allocated, unallocated,
picked and currently available quantities, allocation status, and exception
reason. Summary fields are `total_orders`, `total_lines`,
`total_quantity_unallocated`, `lines_with_available_stock`, and
`lines_out_of_stock`; those totals cover the complete filtered result rather
than only the returned page. Item view responses return exact aggregate records
in `item_groups` and leave `lines` empty, so one popular SKU cannot make a page
unbounded. Each group includes an exact affected-order count and summed
quantities plus a representative item identity. Selecting a group switches to
the `orders` view with its `item_id` or `unmatched_line_id`; those affected
lines use normal bounded pagination, so every record remains reachable. Only
one group selector may be sent at a time. The response also includes
`warehouses`, `view`,
`total_item_groups`, `returned_item_groups`, `page`, `page_size`, `total_pages`,
`returned_count`, `has_previous`, and `has_next`.

### GET /api/allocations/exceptions/export

Export the complete allocation-exception result as CSV using the same filters
as `GET /api/allocations/exceptions`. Pagination parameters are intentionally
not accepted, so a page-sized UI response never clips the export.

### POST /api/allocations/preview

Preview allocation recommendations for one or more eligible local processing
orders.

Request:
- `idempotency_key`: optional retry-safe request identity
- `order_ids`: local order IDs
- `lines`: optional explicit order line quantities
- `allocation_strategy`: `available_first` for the current MVP
- `allow_partial`
- `created_by`
- `notes`

Preview response includes:
- `total_orders`
- `total_lines`
- `allocatable_lines`
- `partial_lines`
- `skipped_lines`
- `conflict_lines`
- `total_quantity_to_allocate`
- `total_shortage_quantity`
- `preview_orders`

Preview does not update items, order lines, allocations, audit events, stock
movements, or WooCommerce.

### POST /api/allocations/commit

Commit allocation after revalidating all selected lines.

Commit behavior:
- Creates a posted allocation header and allocation lines.
- Increases local item `Allocated`.
- Leaves local item `In Stock` unchanged.
- Recalculates item `Sellable` and `Under Par`.
- Updates local order line `quantity_allocated`.
- Leaves `quantity_picked` unchanged.
- Updates local order status to `open`, `partially_allocated`, or `allocated`.
- Creates `inventory_audit_events` rows with `event_type = allocate`.
- Does not create stock movement rows because allocation does not change
  physical stock.
- Never writes WooCommerce.

Atomicity:
- Item aggregates and all affected item-location rows are locked in a
  deterministic order before quantity validation.
- Commit revalidates current item sellable quantity and remaining order
  quantity.
- Requested quantity cannot exceed remaining order quantity.
- Requested quantity cannot exceed current item Sellable.
- Allocation cannot make item Allocated exceed item In Stock.
- When `allow_partial` is false, any non-fully-allocatable selected line rejects
  the entire commit.

### GET /api/allocations

List allocation history.

Filters:
- `status`
- `allocation_type`
- `order_id`
- `woo_order_id`
- `woo_order_number`
- `date_from`
- `date_to`
- `created_by`
- `page` (defaults to `1`)
- `page_size` (defaults to `20`, maximum `100`)

The response reports the exact complete filtered `total` plus `page`,
`page_size`, `total_pages`, `returned_count`, `has_previous`, and `has_next`.
Only the selected page and its lines are loaded.

### GET /api/allocations/{id}

Return allocation header, lines, and audit event references.

### GET /api/allocations/{id}/export

Export one allocation as CSV.

CSV columns:
`Allocation Number`, `Status`, `Created At`, `Posted At`,
`Woo Order Number`, `Order ID`, `SKU`, `Barcode`, `Description`, `Warehouse`,
`Inventory Location`, `Quantity Ordered`, `Previously Allocated`,
`Quantity Allocated`, `Allocated After`, `In Stock Before`,
`Sellable Before`, `Sellable After`, `Shortage Quantity`, `Line Status`,
`Notes`.

## Picks

Picking records operational progress against already allocated local order
lines and is the local stock reduction step. Picking is local-only: it does not
write WooCommerce, create routes, fulfill orders, or send outbound/customer
notifications. The primary frontend workflow is manual quantity entry per
order line; scanner endpoints remain backend compatibility APIs and are not
required by the Pick Orders screen.

### POST /api/picks/preview

Preview pick recommendations for one or more allocated local orders.

Request:
- `order_ids`: local order IDs
- `lines`: optional explicit order line quantities
- `pick_strategy`: `allocated_first` for the current MVP
- `allow_partial`
- `created_by`
- `notes`

Preview response includes:
- `total_orders`
- `total_lines`
- `pickable_lines`
- `partial_lines`
- `skipped_lines`
- `conflict_lines`
- `total_quantity_to_pick`
- `warnings`
- `errors`
- `preview_orders`

Line preview includes ordered quantity, allocated quantity, previously picked
quantity, remaining to pick, recommended pick quantity, picked-after quantity,
warehouse, inventory location, and pick status.

Preview does not update items, order lines, picks, audit events, stock
movements, or WooCommerce.

### POST /api/picks/commit

Commit picking after revalidating all selected lines.

Commit behavior:
- Creates a posted pick header and pick lines.
- Updates local order line `quantity_picked` and legacy `picked_qty`.
- Updates local order line `quantity_stock_reduced`.
- Reduces local item-location and aggregate `In Stock`.
- Reduces local item-location and aggregate `Allocated`.
- Recalculates `Sellable`.
- Updates local order status to `partially_picked` or `picked` when applicable.
- Creates `stock_movements` rows with `movement_type = pick_stock_reduction`.
- Creates `inventory_audit_events` rows with `event_type = pick_stock_reduction`.
- Never writes WooCommerce.

Atomicity:
- Commit revalidates remaining quantity to pick.
- Requested quantity cannot exceed allocated quantity.
- Requested quantity cannot exceed allocated minus already picked.
- Requested quantity cannot reduce stock more than picked or allocated
  quantity.
- Commit cannot make location or aggregate In Stock/Allocated negative.
- When `allow_partial` is false, any non-fully-pickable selected line rejects
  the entire commit.

### GET /api/picks

List pick history.

Filters:
- `status`
- `pick_type`
- `order_id`
- `woo_order_id`
- `woo_order_number`
- `date_from`
- `date_to`
- `created_by`
- `page` (defaults to `1`)
- `page_size` (defaults to `20`, maximum `100`)

The response reports the exact complete filtered `total` plus `page`,
`page_size`, `total_pages`, `returned_count`, `has_previous`, and `has_next`.
Only the selected page and its lines are loaded.

### GET /api/picks/{id}

Return pick header, lines, and audit event references.

### GET /api/picks/{id}/export

Export one pick as CSV.

CSV columns:
`Pick Number`, `Status`, `Created At`, `Posted At`, `Woo Order Number`,
`Order ID`, `SKU`, `Barcode`, `Description`, `Warehouse`,
`Inventory Location`, `Quantity Ordered`, `Quantity Allocated`,
`Previously Picked`, `Quantity Picked`, `Picked After`, `Remaining To Pick`,
`Line Status`, `Notes`.

## Fulfillments

Fulfillment remains for legacy compatibility and history/reporting. It is no
longer the normal stock reduction step; picking reduces stock. Fulfillment is
local-only: it does not write WooCommerce, update WooCommerce order status,
update WooCommerce stock/products, create routes, create shipping labels, send
outbound/customer notifications, create purchase orders, or add supplier
workflows.

### POST /api/fulfillments/preview

Preview fulfillment recommendations for one or more picked local orders.

Request:
- `order_ids`: local order IDs
- `lines`: optional explicit order line quantities
- `fulfillment_strategy`: `picked_first` for the current MVP
- `allow_partial`
- `created_by`
- `notes`

Preview response includes:
- `total_orders`
- `total_lines`
- `fulfillable_lines`
- `partial_lines`
- `skipped_lines`
- `conflict_lines`
- `total_quantity_to_fulfill`
- `warnings`
- `errors`
- `preview_orders`

Line preview includes ordered, allocated, picked, previously fulfilled,
remaining to fulfill, recommended fulfill quantity, fulfillment status, current
item In Stock, Allocated, Sellable, warehouse, and inventory location.

Preview does not update item quantities, order lines, fulfillment records,
fulfillment lines, stock movements, audit events, or WooCommerce.

### POST /api/fulfillments/commit

Commit fulfillment after revalidating all selected lines.

Commit behavior:
- Creates a posted fulfillment header and fulfillment lines.
- Updates local order line `quantity_fulfilled` and legacy `fulfilled_qty`.
- If picking already reduced stock, does not reduce stock again and returns a
  warning that stock was already reduced during picking.
- Updates local order completion/legacy fulfillment state.
- Creates `inventory_audit_events` rows for compatibility history.
- Creates no stock movement rows in the normal picked-order path.
- Rejects unpicked orders instead of silently reducing stock through the old
  path.
- Never writes WooCommerce.

Atomicity:
- Commit revalidates remaining quantity to fulfill.
- Requested quantity cannot exceed picked quantity.
- Requested quantity cannot exceed allocated quantity.
- Fulfillment cannot double-reduce stock already reduced by picking.
- When `allow_partial` is false, any non-fully-fulfillable selected line rejects
  the entire commit.

Stock movement rows:
- Normal picked-order fulfillment creates no stock movement rows because
  picking already created `pick_stock_reduction` movements.

Audit event rows:
- `event_type = fulfill`
- `quantity_delta` is negative
- previous/new In Stock, Allocated, and Sellable are captured
- `reference_type = fulfillment`
- `reference_id = fulfillments.id`
- `reference_number = fulfillment_number`

### GET /api/fulfillments

List fulfillment history.

Filters:
- `status`
- `fulfillment_type`
- `order_id`
- `woo_order_id`
- `woo_order_number`
- `date_from`
- `date_to`
- `created_by`
- `page` (defaults to `1`)
- `page_size` (defaults to `20`, maximum `100`)

The response reports the exact complete filtered `total` plus `page`,
`page_size`, `total_pages`, `returned_count`, `has_previous`, and `has_next`.
Only the selected page and its lines are loaded.

### GET /api/fulfillments/{id}

Return fulfillment header, lines, stock movement references, and audit event
references.

### GET /api/fulfillments/{id}/export

Export one fulfillment as CSV.

CSV columns:
`Fulfillment Number`, `Status`, `Created At`, `Posted At`,
`Woo Order Number`, `Order ID`, `SKU`, `Barcode`, `Description`, `Warehouse`,
`Inventory Location`, `Quantity Ordered`, `Quantity Allocated`,
`Quantity Picked`, `Previously Fulfilled`, `Quantity Fulfilled`,
`Fulfilled After`, `Remaining To Fulfill`, `In Stock Before`,
`Allocated Before`, `Sellable Before`, `In Stock After`, `Allocated After`,
`Sellable After`, `Line Status`, `Notes`.

## Locations

### GET /api/locations

List warehouse/inventory locations.

Implemented query params:
- `search`
- `warehouse`
- `code`
- `name`
- `zone`
- `aisle`
- `active`

Search covers warehouse, code, name, description, zone, and aisle.

### GET /api/locations/{id}

Return one location.

### POST /api/locations

Create a location.

Implemented for local Pongo Inventory OS persistence only. Required fields:
- `warehouse`
- `code`
- `name`

If a location is marked default, the backend clears other defaults in the same
warehouse.

### PATCH /api/locations/{id}

Update a location.

Implemented for local Pongo Inventory OS persistence only.

### DELETE /api/locations/{id}

Soft delete/deactivate a location by setting `isActive` to false.

### GET /api/locations/export

Export locations CSV.

Implemented. Exports filtered rows using the canonical location CSV header from
`docs/CSV_COLUMNS.md`.

### POST /api/locations/import/preview

Preview a location CSV import.

Implemented. Accepts `multipart/form-data` with a `file` upload. This endpoint
parses and validates the CSV but does not write to the database.

Header rules:
- Canonical location columns from `docs/CSV_COLUMNS.md` are required.
- Header whitespace is trimmed.
- Column names are case-sensitive.
- Missing canonical columns reject the file.
- Extra columns are ignored and returned as warnings.

Matching rules:
- Existing locations match by exact Warehouse + Location Code.
- Missing matches create new locations.

Returns:
- `total_rows`
- `valid_rows`
- `invalid_rows`
- `create_count`
- `update_count`
- `skipped_count`
- `warnings`
- `errors`
- `preview_rows`

### POST /api/locations/import/commit

Commit a location CSV import.

Implemented. Valid rows create or update local location records only. The
endpoint does not change item stock, create stock movements, or run receiving,
cycle count, allocation, picking, route, or WooCommerce workflows.

The commit writes an `import_jobs` record with `import_type = locations` plus
`import_errors` rows for failed CSV rows.

Returns:
- `import_job_id`
- `total_rows`
- `created_count`
- `updated_count`
- `skipped_count`
- `failed_count`
- `warnings`
- `errors`

## Inventory

### GET /api/inventory/export/by-location

Export inventory by warehouse/location as CSV.

Implemented. Uses current item text fields for `Warehouse`,
`Inventory Location`, and `Default Location`; item-location foreign keys are
not globally enforced yet.

Supported query params:
- `warehouse`
- `inventory_location`
- `default_location`
- `category`
- `brand`
- `under_par`
- `non_inventory`

CSV columns are documented in `docs/CSV_COLUMNS.md`.

Calculated fields are recomputed at export time:
- `Sellable = In Stock - Allocated`
- `Under Par = In Stock <= Par Level`
- `Storage Volume = Storage Length * Storage Width * Storage Height`
- `Inventory Value = In Stock * Unit Cost`

### GET /api/inventory/summary/by-location

Return inventory totals grouped by warehouse and inventory location.

Implemented. Supports the by-location filters plus `search` and the same
comma-separated `data_quality` values as `GET /api/items`, allowing inventory
cards and catalog rows to describe the same filtered record set. Filtering,
grouping, and numeric totals are calculated in one database aggregation query;
operational stock quantities are not cached.

Each group includes:
- `warehouse`
- `inventory_location`
- `item_count`
- `total_in_stock`
- `total_allocated`
- `total_sellable`
- `total_on_order`
- `total_inventory_value`
- `under_par_count`

## Receiving

### POST /api/receipts/direct/preview

Validate a direct receiving payload without database writes.

Implemented. Preview does not update item stock, create receipts, create
receipt lines, or create stock movements.

Validation rules:
- Receipt warehouse is required.
- Each line must match an existing item by `item_id`, exact SKU, or exact Barcode.
- If SKU and Barcode match different items, the line is invalid.
- Unknown items are rejected; receiving does not auto-create items.
- Each line requires an active location matching warehouse + Location Code or
  warehouse + Location Name.
- Quantity Received must be greater than zero.

### POST /api/receipts/direct/commit

Commit direct receiving without PO.

Implemented. The commit is atomic: if any line is invalid, the full receipt is
rejected and no stock is updated.

The body may include `idempotency_key`; the bulk receipt commit supports the
same field.

On success:
- Creates a `receipts` row with `receipt_type = direct` and `status = posted`.
- Creates receipt line rows.
- Increases item `In Stock`.
- The receipt operation itself does not reserve stock, but it runs FIFO
  reconciliation in the same transaction; waiting processing orders may
  therefore increase `Allocated` immediately after receipt stock is posted.
- Recalculates item Sellable, Under Par, and Storage Volume.
- Creates one stock movement/audit row per received line.

Intentional exclusions:
- No purchase orders.
- No supplier management.
- No WooCommerce calls.
- No picking, route, or fulfillment workflow. Receiving may trigger local FIFO
  allocation for waiting processing orders.
- No weighted average cost update.

### POST /api/receipts

Create a direct receiving session with one or more receipt item rows. Increases location stock and creates stock movement rows.

### GET /api/receipts

List receipts using `page` (default `1`) and `page_size` (default `20`, maximum
`100`). The response includes the exact complete filtered `total`,
`total_pages`, `returned_count`, `has_previous`, and `has_next`. Receipt detail
and per-receipt CSV export endpoints are unchanged.

### GET /api/receipts/{id}

Return receipt details and item rows.

### GET /api/stock-movements

List stock movement audit rows using `page` (default `1`) and `page_size`
(default `20`, maximum `100`). The response includes the exact complete
filtered `total`, `total_pages`, `returned_count`, `has_previous`, and
`has_next`. The separate `/api/stock-movements/export` endpoint remains an
unbounded filtered CSV export.

Implemented filters:
- `item_id`
- `sku`
- `barcode`
- `warehouse`
- `inventory_location`
- `movement_type`
- `reference_type`
- `reference_id`
- `date_from`
- `date_to`

## Cycle Count

Cycle Count is implemented as the second stock-changing workflow after Direct
Receiving. It does not call WooCommerce and does not run picking, route,
fulfillment, purchase order, or supplier workflows. A committed count reruns
local FIFO allocation because a positive variance may make stock available to
waiting processing orders.

### POST /api/cycle-counts/preview

Validate a cycle count payload and calculate variances without writing stock
changes.

Implemented behavior:
- Does not update item stock.
- Does not create cycle count rows.
- Does not create stock movements.
- Matches items by `item_id`, exact SKU, or exact Barcode.
- Rejects a line when SKU and Barcode match different existing items.
- Rejects unknown items.
- Requires warehouse.
- Requires an active location when `inventory_location` is provided.
- Requires `inventory_location` for `count_type = full_location`.
- Requires `counted_quantity >= 0`.

Response fields:
- `total_lines`
- `valid_lines`
- `invalid_lines`
- `adjustment_lines`
- `total_positive_variance`
- `total_negative_variance`
- `total_absolute_variance`
- `total_variance_value`
- `errors`
- `warnings`
- `preview_lines`

Preview line fields:
- `line_number`
- `item_id`
- `sku`
- `barcode`
- `description`
- `warehouse`
- `inventory_location`
- `system_quantity`
- `counted_quantity`
- `variance_quantity`
- `unit_cost`
- `variance_value`
- `status`
- `warnings`
- `errors`

### POST /api/cycle-counts/commit

Validate and post a cycle count atomically.

Implemented behavior:
- Rejects the full count if any line is invalid.
- Creates a `cycle_counts` header row with `status = posted`.
- Creates one `cycle_count_lines` row per valid line.
- Updates item `In Stock` to `counted_quantity` only when variance is non-zero.
- The count adjustment itself leaves Allocated unchanged, then FIFO
  reconciliation may reserve newly available stock.
- Recalculates Sellable, Under Par, and Storage Volume.
- Creates stock movement rows only for variance lines.

Stock movement audit fields:
- `movement_type = cycle_count_adjustment`
- `quantity_delta = counted_quantity - system_quantity`
- `previous_in_stock = system_quantity`
- `new_in_stock = counted_quantity`
- `reference_type = cycle_count`
- `reference_id = cycle_count id`
- `reference_number = count_number`

Calculation rules:
- `system_quantity` is captured from current item `In Stock`.
- `variance_quantity = counted_quantity - system_quantity`.
- `variance_value = variance_quantity * unit_cost`.
- Null or blank unit cost is treated as zero.

### GET /api/cycle-counts

List cycle count events.

Implemented filters:
- `status`
- `warehouse`
- `inventory_location`
- `count_type`
- `date_from`
- `date_to`
- `created_by`

History is server-paged with `page` (default `1`) and `page_size` (default
`50`, maximum `100`). The response keeps `cycle_counts` and the exact filtered
`total`, and adds `page`, `page_size`, `total_pages`, `returned_count`,
`has_previous`, and `has_next`.

### GET /api/cycle-counts/{id}

Return cycle count detail with lines.

### GET /api/cycle-counts/{id}/export

Export one cycle count as CSV.

CSV header order:
- Count Number
- Status
- Created At
- Posted At
- Warehouse
- Inventory Location
- SKU
- Barcode
- Description
- System Quantity
- Counted Quantity
- Variance Quantity
- Unit Cost
- Variance Value
- Notes

### POST /api/cycle-counts/{id}/cancel

Not implemented. The current MVP posts counts immediately and does not persist
draft counts.

## Orders

Implemented Zenventory-style order workflow endpoints:
- `POST /api/integrations/woocommerce/orders/preview`
- `POST /api/integrations/woocommerce/orders/commit`
- `POST /api/integrations/woocommerce/orders/quick-sync`
- `POST /api/integrations/woocommerce/webhooks/orders`
- `GET /api/integrations/woocommerce/webhooks/events`
- `GET /api/orders/open`
- `GET /api/orders/allocate`
- `GET /api/orders/pick`
- `GET /api/orders/completed`
- `GET /api/orders/history`
- `GET /api/orders/{id}`
- `GET /api/orders/{id}/workflow`
- `POST /api/orders/{id}/auto-allocate/preview`
- `POST /api/orders/{id}/auto-allocate/commit`
- `GET /api/allocations/exceptions`
- `POST /api/allocations/auto/commit`
- `POST /api/orders/{id}/complete/preview`
- `POST /api/orders/{id}/complete/commit`
- `GET /api/picks/orders/{order_id}/scanner`
- `POST /api/picks/orders/{order_id}/scan/preview`
- `POST /api/picks/orders/{order_id}/scan/commit`

Order sync runs processing-only FIFO auto-allocation. Open Orders lists active
processing orders, Allocate lists unresolved order/item quantities, Pick Orders
lists fully allocated processing orders ready to pick, and Completed Orders
lists locally closed orders. Picking reduces local stock and completion does not
reduce stock again.

`GET /api/orders/history` is a bounded compatibility view over the allocation,
pick, and fulfillment ledgers. It accepts `page` (default `1`) and `page_size`
(default `20`, maximum `100`). The same requested page is applied independently
to each ledger; a ledger with no rows on that page returns an empty array rather
than repeating its final page. Existing `allocations`, `picks`, `fulfillments`,
and exact combined `total` fields are preserved. Top-level pagination metadata
describes the combined response, and the `pagination` object reports exact
`total`, `total_pages`, `returned_count`, `has_previous`, and `has_next` values
for each ledger. The active frontend reads the three dedicated paginated ledger
endpoints instead of this compatibility route.

## Reports

### Verified report runs

- `GET /api/reports` lists the 17-report catalog.
- `GET /api/reports/sharing/status` returns non-secret delivery readiness.
- `POST /api/reports/runs/{report_key}` generates and freezes a report snapshot.
  Its interactive `rows` preview accepts `row_page` and `row_page_size`
  (maximum 100) and includes exact `row_pagination` metadata.
- `POST /api/reports/jobs/{report_key}` queues an asynchronous report run and
  deduplicates an identical active request.
- `GET /api/reports/jobs/{job_id}` returns report generation status and progress.
- `POST /api/reports/jobs/latest/{report_key}` returns the latest immutable run
  whose normalized filters exactly match the request. It accepts the same
  bounded row-preview parameters.
- `GET /api/reports/runs/{run_id}` returns the frozen snapshot with a bounded
  `rows` preview and accepts `row_page` and `row_page_size` (maximum 100).
- `GET /api/reports/runs/{run_id}/csv` exports that snapshot as UTF-8 CSV.
- `GET /api/reports/runs/{run_id}/pdf` exports that snapshot as a paginated PDF.
  Both endpoints stream worker-rendered, SHA-256-verified artifacts stored with
  the immutable run; they return `409` when an older run has no artifact.
- `POST /api/reports/runs/{run_id}/google-sheets` creates and optionally shares
  a Google Sheet from that snapshot.
- `POST /api/reports/runs/{run_id}/email` emails PDF/CSV attachments and an
  optional Google Sheet link.

All output formats for one run use the same stored payload, run ID, definition
version, generation time, and SHA-256 evidence hash. See `docs/REPORTING.md`.
Preview pagination never changes the stored payload or its evidence hash. CSV,
PDF, Google Sheets, and email deliveries always use every row in that immutable
payload, regardless of which preview page is open in the browser.

### GET /api/reports/received-inventory

Return read-only received inventory report rows derived from receipt lines and
receipt headers.

Implemented filters:
- `date_from`
- `date_to`
- `warehouse`
- `inventory_location`
- `sku`
- `barcode`
- `category`
- `brand`
- `receipt_number`
- `reference_number`
- `created_by`

Date filters use receipt `received_at` and fall back to receipt `created_at`
when `received_at` is missing. `date_from` is inclusive on or after that date;
`date_to` is inclusive on or before that date.

Each row includes:
- `receipt_id`
- `receipt_number`
- `receipt_type`
- `status`
- `received_at`
- `created_at`
- `warehouse`
- `inventory_location`
- `default_location`
- `sku`
- `barcode`
- `description`
- `category`
- `brand`
- `quantity_received`
- `unit_cost`
- `total_received_value`
- `reference_number`
- `created_by`
- `line_notes`
- `receipt_notes`

Calculation:
- `total_received_value = quantity_received * unit_cost`
- Blank or null unit cost is treated as zero.

Data source rules:
- Receipt lines are the operational source of truth for received rows.
- Receipt headers supply receipt number, type, status, received date, reference
  number, created by, and notes.
- Item rows enrich category, brand, barcode, and description when a receipt
  line does not already store the value.
- Stock movements remain audit trail data and are not the primary report source.

Current limitation: this report is based on direct receiving records only
because purchase order receiving is not built.

### GET /api/reports/received-inventory/summary

Return totals and grouped summaries for the same filters as
`GET /api/reports/received-inventory`.

Response fields:
- `total_receipts`
- `total_lines`
- `total_quantity_received`
- `total_received_value`
- `unique_skus`
- `unique_locations`
- `date_from`
- `date_to`
- `by_warehouse`
- `by_location`
- `by_sku`

Grouped summary fields:
- `by_warehouse`: warehouse, total lines, total quantity received, total received value.
- `by_location`: warehouse, inventory location, total lines, total quantity received, total received value.
- `by_sku`: SKU, barcode, description, brand, category, total quantity received, total received value, receipt count.

### GET /api/reports/received-inventory/export

Export the received inventory report as CSV using the same filters as the JSON
report.

CSV header order:
- Receipt Number
- Receipt Type
- Status
- Received At
- Warehouse
- Inventory Location
- Default Location
- SKU
- Barcode
- Description
- Category
- Brand
- Quantity Received
- Unit Cost
- Total Received Value
- Reference Number
- Created By
- Line Notes
- Receipt Notes

### GET /api/reports/fulfillments

Read-only fulfillment/completed-order line report. Uses `fulfillment_lines` as
the primary source and enriches rows from `fulfillments`, local `orders`, local
`order_items`, and `inventory_items`. It does not use WooCommerce and does not
modify inventory or order state.

Filters:
- `date_from`
- `date_to`
- `warehouse`
- `inventory_location`
- `sku`
- `barcode`
- `category`
- `brand`
- `fulfillment_number`
- `woo_order_number`
- `woo_order_id`
- `customer_email`
- `local_status`
- `created_by`

Date filters use `fulfillments.posted_at` and fall back to
`fulfillments.created_at` when posted time is missing.

Calculation:
- `fulfilled_value = quantity_fulfilled * unit_cost`
- blank unit cost is treated as zero

### GET /api/reports/fulfillments/summary

Return totals and grouped summaries for the same filters as the fulfillment
report. Groupings include warehouse, location, SKU, and order.

### GET /api/reports/fulfillments/export

Export the fulfillment report as CSV using the same filters as the JSON report.

CSV header order:
- Fulfillment Number
- Status
- Posted At
- Created At
- Woo Order Number
- Woo Order ID
- Local Status
- Customer Name
- Customer Email
- Warehouse
- Inventory Location
- SKU
- Barcode
- Description
- Category
- Brand
- Quantity Ordered
- Quantity Allocated
- Quantity Picked
- Quantity Fulfilled
- Previously Fulfilled
- Remaining To Fulfill
- Unit Cost
- Fulfilled Value
- In Stock Before
- Allocated Before
- Sellable Before
- In Stock After
- Allocated After
- Sellable After
- Created By
- Line Notes
- Fulfillment Notes

### GET /api/reports/inventory

Inventory export.

### GET /api/reports/inventory-by-location

Inventory export grouped by item/location.

### GET /api/reports/fulfillment

Order fulfillment export.

### GET /api/reports/sku-orders

SKU/barcode order report with search by SKU, barcode, description, and date range.

## Routes

Route records are local-only. The open-order planner constructs keyless Google
Maps direction URLs but does not send orders to Google, call a map/geocoding
API, persist a route, call WooCommerce, or change inventory/order state.

### POST /api/routes/open-orders/plan

Build a read-only delivery plan from selected non-historical operational open
orders with complete shipping addresses. Omitting `order_ids` preserves the
legacy behavior and selects every routable order; an empty list selects none.

Request body:
- `start_address` (defaults to `5855 99 Street NW, Edmonton, AB`)
- `driver_count` (1–50)
- `return_to_start`
- `order_ids` (optional list of at most 5,000 local order IDs)
- `assignment_method` (`equal_time` or `directions`)
- `order_directions` (optional per-order corrections using `N`, `S`, `E`, `W`,
  `NE`, `NW`, `SE`, `SW`, `Central East`, or `Central West`)
- `direction_assignments` (driver numbers with zero or more assigned directions)

`equal_time` uses a deterministic delivery-area and stop-workload estimate to
minimize the estimated duration spread while keeping postal areas together when
possible. It does not claim live Google travel or traffic time. `directions`
supports the ten exact zones above; each driver may receive several zones and
each zone may be shared. When assignments are supplied, the backend never adds
another zone implicitly. Every selected order appears exactly once in a driver
plan or in `unassigned_orders` with a reason. Orders missing a street plus
city/postal code are returned in `excluded_orders` with an actionable reason.

The response includes `available_orders`, selected/assigned/unassigned counts,
`estimate_basis`, `total_estimated_duration_minutes`, parallel
`estimated_completion_minutes`, map coordinate coverage, per-stop direction,
contact/address/total snapshots, and each driver's assigned directions and
estimated duration. IDs that are no longer eligible are safely skipped with a
warning.

Each driver includes ordered stop snapshots and one or more shareable Google
Maps direction URLs. Delivery links contain at most four stops so the three
intermediate-waypoint mobile-browser limit is respected. Long routes therefore
continue as numbered parts, with each part beginning at the prior part's last
stop. Planning is synchronous, read-only, and does not create `routes` or
`route_stops` rows.

Eligible route candidates are non-historical local orders with
`local_status = completed`, `fulfilled`, or `partially_fulfilled` that are not
already assigned to a non-cancelled route.

### GET /api/routes/candidates

List completed local orders that can be placed onto a route.

Query filters:
- `route_date` (the UTC calendar date of `orders.date_created`)
- `local_status`
- `customer_email`
- `woo_order_number`
- `search`

Candidate results are server-paged with `page` (default `1`) and `page_size`
(default `50`, maximum `100`). Eligibility, active-route exclusion, filters,
and the exact `total_candidates` are evaluated in PostgreSQL before the ordered
page is loaded. The response retains `total_candidates` and `candidates` and
adds `page`, `page_size`, `total_pages`, `returned_count`, `has_previous`, and
`has_next`. Ordering is stable by order creation time, Woo order number, then
local order ID. Requests beyond the final page resolve to the final available
page.

Route history is server-paged with `page` (default `1`) and `page_size`
(default `50`, maximum `100`). Filters and the exact `total` are evaluated in
PostgreSQL before the ordered page is loaded. The response keeps `routes` and
adds `page`, `page_size`, `total_pages`, `returned_count`, `has_previous`, and
`has_next`. Requests beyond the final page resolve to the final available page.

Response includes order/customer/shipping snapshots, fulfilled line count,
fulfilled quantity, and a warning when an order is only partially fulfilled.

### POST /api/routes/preview

Validate selected local order IDs before route creation.

Request body:
- `route_date`
- `route_name`
- `driver_name`
- `vehicle_name`
- `order_ids`
- `created_by`
- `notes`

Preview returns valid/invalid stop rows in the selected order. Preview does not
write database rows and does not mutate orders or inventory.

### POST /api/routes/commit

Create a local draft route and route stops from selected valid completed orders.
Commit revalidates selected orders before writing. If any selected order is
invalid, no route is created.

Commit writes:
- `routes`
- `route_stops`

Commit does not update WooCommerce order status, products, or stock. It does
not change local order status, item In Stock, Allocated, Sellable, On Order, or
stock movements.

### GET /api/routes

List local routes.

Query filters:
- `status`
- `route_date`
- `date_from`
- `date_to`
- `driver_name`
- `vehicle_name`
- `search`

### GET /api/routes/{route_id}

Return a route with route stops.

### GET /api/routes/{route_id}/export

Export one route as CSV with route and stop snapshots.

### POST /api/routes/{route_id}/finalize

Mark a draft route finalized locally. This does not dispatch, notify, label,
track delivery, or update WooCommerce.

### POST /api/routes/{route_id}/cancel

Mark a route cancelled locally. Stops remain for audit/review, and the orders
become eligible for a future route because cancelled routes are ignored by the
candidate filter.

Not implemented yet:
- traffic-aware or road-network route optimization
- address validation/geocoding
- embedded in-app maps
- delivery tracking
- customer notifications

## Items Control Center And Bulk Operations

Implemented endpoints:
- `GET /api/items/search`
- `GET /api/items/{id}/detail`
- `GET /api/items/{id}/activity`
- `GET /api/items/{id}/history?section=...`
- `GET /api/items/{id}/receipts`
- `GET /api/items/{id}/cycle-counts`
- `GET /api/items/{id}/adjustments`
- `GET /api/items/{id}/transfers`
- `GET /api/items/{id}/allocations`
- `GET /api/items/{id}/picks`
- `GET /api/items/{id}/fulfillments`
- `GET /api/items/{id}/orders`
- `GET /api/items/{id}/stock-movements`
- `GET/POST/PATCH/DELETE /api/items/{id}/notes`
- `POST /api/items/bulk/preview`
- `POST /api/items/bulk/commit`

Bulk edit uses a preview/commit flow with `{ item_ids, updates }`. It supports
shared catalog metadata, costs/prices, replenishment fields, handling flags,
additive tags (`add_tags`), and an existing active location (`location_id`,
optionally `make_default_location`). Adding a location creates a zero-quantity
item/location assignment and never moves stock. SKU, barcode, direct location
labels, stock quantities, derived values, WooCommerce identity, and unknown
fields fail closed.

## UI Saved Views

Implemented endpoints:
- `GET /api/ui/saved-views?page=items`
- `POST /api/ui/saved-views`
- `PATCH /api/ui/saved-views/{id}`
- `DELETE /api/ui/saved-views/{id}`

Saved views are global/system-scoped until auth/RBAC is added.

## Bulk Receiving

Implemented endpoints:
- `POST /api/receipts/bulk/preview`
- `POST /api/receipts/bulk/commit`
- `GET /api/receipts/{id}/detail`
- `GET /api/receipts/{id}/export`

Bulk commit creates one `receipts` row, one `receipt_items` row per valid
line, updates `inventory_item_locations`, recalculates item aggregate stock
fields, creates one stock movement per committed line, and reruns FIFO
allocation for waiting processing orders before commit. Preview is read-only.

## Scanner Workflows

Implemented endpoints:
- `GET /api/scanner/inventory/lookup`
- `GET /api/scanner/location/lookup`
- `POST /api/scanner/receiving/scan/preview`
- `POST /api/scanner/receiving/scan/commit`
- `POST /api/scanner/cycle-count/preview`
- `POST /api/scanner/cycle-count/commit`
- `POST /api/scanner/transfers/preview`
- `POST /api/scanner/transfers/commit`
- `POST /api/scanner/adjustments/preview`
- `POST /api/scanner/adjustments/commit`

Scanner endpoints treat hardware scanners as keyboard input. Stock-changing
scanner commits are local only and create stock movement/audit records through
the existing stock services. Scanner receiving, positive stock adjustments,
and positive cycle-count results rerun FIFO allocation; scanner previews remain
read-only.

Product scan matching evaluates the captured barcode both as entered and with
exactly one leading zero added or removed. SKU matching remains exact; if the
barcode variants identify more than one item, the scan fails closed instead of
guessing. Manual adjustment reasons are optional and receive the standard
audited default when omitted.

## Expanded Reports

Implemented read-only row, summary, and CSV export endpoints:
- `/api/reports/inventory-valuation`
- `/api/reports/low-stock`
- `/api/reports/stock-movement-ledger`
- `/api/reports/item-activity`
- `/api/reports/location-utilization`
- `/api/reports/margin-by-sku`
- `/api/reports/receiving-cost`
- `/api/reports/adjustments`

Each report also supports `/summary` and `/export`.

The inventory valuation summary distinguishes inventory records, normalized
unique SKUs, SKUs with matching location rows, and valued SKUs with both a
matching location row and unit cost. It also returns counts for missing or
duplicate SKUs, missing locations, missing cost, location-filter exclusions,
and a structured `exclusion_summary` for user-facing explanations. Valuation
rows require an active location row with populated warehouse and location.
They preserve missing `unit_cost`, `inventory_value`, `sales_price`,
`retail_value`, and `margin_estimate` as `null`; valid zero cost or price
remains numeric zero, and summaries sum only available values. Inventory CSV
exports likewise leave unavailable cost/value cells blank rather than writing
a fabricated zero.

Rows, summaries, and CSV exports accept identical filter sets for each report.
In particular, item activity includes `start_date`, `end_date`, `sku`,
`barcode`, and `movement_type`; margin by SKU includes `start_date`,
`end_date`, `sku`, `brand`, and `category`; receiving cost includes
`start_date`, `end_date`, `sku`, `warehouse`, and `inventory_location`; and
adjustments includes `adjustment_type`, `sku`, `warehouse`, and
`inventory_location`.

## Pongo Insights

Implemented read-only dashboard endpoints:
- `GET /api/insights/overview`
- `GET /api/insights/orders-revenue`
- `GET /api/insights/customer-metrics`
- `GET /api/insights/customer-segmentation`
- `GET /api/insights/product-sku`
- `GET /api/insights/subscriptions`
- `GET /api/insights/subscription-products`
- `GET /api/insights/inventory-forecasting`
- `GET /api/insights/coupons`
- `GET /api/insights/payment-health`
- `GET /api/insights/geography`
- `GET /api/insights/product-affinity`
- `GET /api/insights/reorder-forecast`

Implemented CSV exports:
- `GET /api/insights/orders-revenue/export`
- `GET /api/insights/customer-metrics/export`
- `GET /api/insights/product-sku/export`
- `GET /api/insights/reorder-forecast/export`
- `GET /api/insights/geography/export`

Common query params include `start_date`, `end_date`, `brand`, `category`,
`sku`, `customer_email`, `city`, `postal_code`, `payment_method`,
`order_status`, `limit`, and `offset`.

Insights endpoints read local tables only and return `data_quality` warnings
for missing source data instead of faking metrics.

Revenue dashboards use one canonical metric set: `gross_sales` is the sum of
pre-discount order subtotals, `discount_amount` is the synced WooCommerce order
discount total, and `net_sales` is the sum of post-discount line totals before
shipping, tax, and refunds. `average_order_value` uses net sales divided by the
included sales-order count and is `null` when no orders match. Refund amount and rate are `null` until refund
detail is synced; they are never represented as calculated zeroes. Product
rows expose `product_title` and retain `description` as the same concise title
for compatibility. Product profitability rows also expose `cost_available`;
when required cost is missing, estimated cost, margin, and margin percentage
remain `null`, while a legitimate zero cost remains numeric zero.

Inventory forecasting uses only successful orders that match the selected date
range and order filters. SKU, brand, and category filters also scope both the
sales lines and inventory rows returned by the forecast; failed or cancelled
orders never contribute demand. Each forecast row exposes `forecast_available`
and `forecast_status`. Demand, velocity, days-left, and reorder quantities are
`null` with `insufficient_history` status when usable sales history is absent;
summary fields expose available and insufficient-history counts plus an overall
forecast status.

Subscription dashboards use the latest complete active WooCommerce
subscription snapshot. Subscription rows expose the official next-payment
date, renewal quantity, Pongo in-stock/sellable quantities, mapping status, and
30-day stock risk. Product rows aggregate active subscriptions and units per
renewal. Until the first successful snapshot, `data_available` is false and KPI
values remain nullable; a failed refresh keeps the last good snapshot.

## Business Dashboard

Implemented read-only dashboard endpoints:
- `GET /api/business-dashboard`
- `GET /api/business-dashboard/today`
- `GET /api/business-dashboard/open-orders`
- `GET /api/business-dashboard/woocommerce-open-orders`
- `GET /api/business-dashboard/subscriptions`
- `GET /api/business-dashboard/revenue-comparison`
- `GET /api/business-dashboard/order-map`

`/api/business-dashboard` combines today's metrics, open orders, subscription
state, revenue comparison, order map/geography, and data quality warnings.

The combined business dashboard and its detailed sections read local order
snapshots and order lines only. They do not call WooCommerce, mutate orders,
mutate stock, or geocode addresses through an external provider.

`GET /api/business-dashboard/woocommerce-open-orders?page=1&page_size=100` is
the isolated exception. The backend sends one read-only WooCommerce list
request for status `processing` (`page_size` is capped at 100), joins an
existing local order ID without creating a snapshot, and returns:

```json
{
  "source": "woocommerce",
  "fetched_at": "2026-08-11T19:20:03+00:00",
  "statuses": {"processing": 7},
  "summary": {"open_orders_count": 7},
  "total": 7,
  "page": 1,
  "page_size": 100,
  "total_pages": 1,
  "orders": [
    {
      "woo_order_id": 38682,
      "local_order_id": null,
      "order_number": "38682",
      "status": "processing",
      "customer_name": "Avery Stone",
      "customer_email": "avery@example.invalid",
      "currency": "CAD",
      "total": "61.07",
      "date_created": "2026-08-19T15:38:00",
      "date_modified": "2026-08-19T15:40:00",
      "line_count": 2
    }
  ]
}
```

The endpoint returns HTTP 503 with code
`woocommerce_open_orders_unavailable` when the rows or exact remote pagination
totals cannot be verified; it never substitutes the local snapshot total and
never mutates local order, allocation, stock, or audit state. Demo access
returns `source: "demo"` from the isolated mock database without contacting
WooCommerce, normalizes the mock rows to `processing`, and derives its total
from those same returned mock rows.

### Live Woo Order Operations

All order-operation mutations require a nonblank `idempotency_key` in the JSON
body. An optional `Idempotency-Key` header may repeat it; a mismatch returns
HTTP 409.

- `POST /api/orders/woocommerce/{woo_order_id}/reconcile` with
  `{"idempotency_key":"..."}` fetches that exact live Woo order, requires it
  to remain `processing`, reconciles it into the local operational store, and
  returns `{"status":"reconciled","woo_order_id":501,"local_order_id":12,
  "order":<OpenOrderDetail>}`. It does not change Woo status or stock.
- `POST /api/orders/woocommerce/{woo_order_id}/status` accepts
  `target_status` (`completed` or `cancelled`), `completion_mode` (`complete`,
  `complete_picked`, or `complete_without_picking`), `reason`, and
  `idempotency_key`. The backend re-fetches the exact Woo order and requires
  live status `processing`. It infers and revalidates the safe completion path
  under the order lock; partial picking blocks completion. Cancellation blocks
  any picked, fulfilled, or stock-reduced quantity, creates a durable local
  cancellation guard, releases allocations only after Woo confirms
  cancellation, and cannot race an accepted local completion. The response
  includes `local_order_id`, `local_status`, `released_quantity`,
  `woo_sync_status`, `woo_writeback_queue_id`, and `woo_sync_error`.
- `POST /api/orders/{order_id}/lines/{order_line_id}/substitute` accepts
  `replacement_inventory_item_id`, `reason`, and `idempotency_key`. It releases
  the old unpicked allocation, selects the effective replacement, and reruns
  allocation. Woo line items are never changed. `OpenOrderLineRead` retains the
  commercial Woo identity in `sku`, `barcode`, and `name`, exposes the
  operational identity in `item_id`, `effective_sku`, `effective_barcode`, and
  `effective_name`, and exposes the audit identity in `substituted_from_item_id`,
  `substituted_from_sku`, `substituted_from_name`, `substitution_reason`,
  `substituted_by`, and `substituted_at`.
- `POST /api/orders/{order_id}/prepare-picking` accepts `reason` and
  `idempotency_key`. It is restricted to a pristine local
  `completed_without_picking` order whose exact live Woo order still reports
  `completed`, has no prior pick history, and has no picked, fulfilled, or
  stock-reduced quantity. It opens only the recovery picking workflow and does
  not change Woo status.

Status-action retries must reuse the same idempotency key, order, target, and
reason. A failed or timed-out Woo write may be retried with that key. If Woo
already accepted a timed-out request, the retry reconciles the live target
status and marks the matching queue row sent. Different completion and
cancellation intents are mutually exclusive once either local transition has
won.

Counts, totals, customer first-order classification, units, and daily revenue
comparison are calculated in SQL with the same status precedence and configured
admin-timezone day boundaries as the API fields. Order-map detail is limited to
the requested day. The open-order card returns at most 200 newest rows while
`summary.open_orders_count` remains the exact full filtered count. Subscription
detail reads only the local normalized subscription snapshot; raw WooCommerce
order payloads are not loaded for dashboard requests.

## Woo Mapping And Item Enrichment

- `POST /api/integrations/woocommerce/products/sync/preview` previews batched
  simple-product, variable-parent, and variation actions without writes.
- `POST /api/integrations/woocommerce/products/sync/commit` commits one item
  per valid simple product or purchasable variation and returns result counts.
- `GET /api/items/enrichment/export` downloads the protected-identity
  enrichment template separately from the canonical item export.
- `POST /api/items/enrichment/preview` accepts multipart `file` and
  `import_opening_stock`, performs no writes, and reports row matching,
  changes, warnings, conflicts, unmatched rows, and errors.
- `POST /api/items/enrichment/commit` revalidates and commits the upload. It
  never creates items or changes mapping identity. Reapplying an opening-balance
  file returns HTTP 409.
- `POST /api/integrations/woocommerce/remap/preview` validates an exception
  mapping without writes.
- `POST /api/integrations/woocommerce/remap/commit` updates local mapping
  metadata, writes an audit event, and reprocesses eligible unmatched order
  lines/allocation.
- `POST /api/integrations/woocommerce/writeback/queue/{queue_id}/revalidate`
  rebuilds only a pending/failed stock queue row from the current mapping and
  quantity. Completed and dry-run history is immutable.

Mapping import, enrichment, and remap never send a WooCommerce write.
