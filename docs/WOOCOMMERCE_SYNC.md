# WooCommerce Sync Plan

This document describes WooCommerce integration behavior. The current
implementation supports read-only product/variation sync, read-only REST order
snapshot sync, and a signed phase-1 `order.created` webhook through the backend
only.

## System Roles

- WooCommerce remains the storefront and customer-facing product/order system.
- Pongo Inventory OS is the operational inventory layer.
- Pongo Inventory OS syncs WooCommerce data into PostgreSQL.
- The React frontend reads from the Pongo backend/database only.
- The frontend must never call WooCommerce directly.

## Credentials

Backend WooCommerce environment variables. Webhook and writeback values may
remain at their disabled safe defaults until those paths are intentionally used:
- `WOOCOMMERCE_BASE_URL`
- `WOOCOMMERCE_CONSUMER_KEY`
- `WOOCOMMERCE_CONSUMER_SECRET`
- `WOOCOMMERCE_ENVIRONMENT`
- `WOOCOMMERCE_READ_ONLY`
- `WOOCOMMERCE_READ_ENABLED`
- `WOOCOMMERCE_WRITEBACK_ENABLED`
- `WOOCOMMERCE_WRITEBACK_DRY_RUN`
- `WOOCOMMERCE_STAGING_LIVE_TEST_MODE`
- `WOOCOMMERCE_ALLOW_STOCK_WRITE`
- `WOOCOMMERCE_ALLOW_ORDER_STATUS_WRITE`
- `WOOCOMMERCE_ALLOW_PRODUCT_METADATA_WRITE`
- `WOOCOMMERCE_ALLOW_CUSTOMER_WRITE`
- `WOOCOMMERCE_ALLOW_COUPON_WRITE`
- `WOOCOMMERCE_ALLOW_REFUND_WRITE`
- `WOOCOMMERCE_ALLOW_DELETE`
- `WOOCOMMERCE_ALLOWED_HOST`
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

Never commit real credentials. Example docs and tests must use placeholders only.
The webhook secret is independent from the REST API consumer secret and must be
at least 32 bytes. The status API may report that it is present/configured but
must never return its value.
The frontend never receives the consumer key or secret. Status responses expose
only the base URL, host, and boolean/flag metadata.

Settings → Connection can verify and replace the REST store URL, consumer key,
and consumer secret through the backend. Settings → Sync & Mapping owns
catalog, order, remap, and sync-history workflows. Settings → Writeback owns
guarded stock/order-status previews and the paginated writeback queue. The
backend performs a read-only connection check before saving credentials to
encrypted PostgreSQL storage; the check requires both product-list and
order-list access, and blank credential fields preserve existing values. The
connection form never changes writeback flags. When a new store URL differs
from `WOOCOMMERCE_ALLOWED_HOST`, the operator must explicitly authorize the
exact replacement host; Pongo verifies the read-only connection before saving
the base URL and allowed host together. After saving, the backend starts a
bounded open-order quick sync; periodic reconciliation remains the durable
recovery path and imports any backlog beyond that first batch.

## Read-Only Sync First

Product/variation and order ingestion are read-only. Writeback exists only
behind preview, queue, approval, allowlisted operations, and dry-run. Do not
enable the production stock-authority policy until:
- product/variation mapping is stable;
- local item workflows are stable;
- stock movement auditing is verified;
- Pongo explicitly approves stock writeback behavior.

REST credentials are sent with HTTPS Basic Auth. They are never placed in URL
query strings, application logs, frontend state, or API responses.

## Writeback Safety

Staging live tests require staging mode. Production stock writes require
`WOOCOMMERCE_PRODUCTION_STOCK_AUTHORITY=pongo`; without that exact policy they
fail closed.

The inbound webhook is configured separately from writeback. It can remain
read-only against WooCommerce while `WOOCOMMERCE_READ_ONLY=true`,
`WOOCOMMERCE_WRITEBACK_ENABLED=false`, and all live-write flags are false.
Receiving a webhook does not grant or perform a WooCommerce write.

Required guard rules for a live staging send:

- environment must be `staging`
- read-only mode must be false
- writeback must be enabled
- staging live test mode must be true
- dry-run must be false
- WooCommerce base URL host must match `WOOCOMMERCE_ALLOWED_HOST`
- operation type must be allowlisted
- endpoint path must be allowlisted
- method must be `PUT` or `PATCH`
- payload must contain only fields allowlisted for the operation

Safe default dry-run should remain true until a live staging test is intentional:

```bash
WOOCOMMERCE_WRITEBACK_DRY_RUN=true
```

Live staging tests intentionally flip dry-run off and live-test mode on:

```bash
WOOCOMMERCE_WRITEBACK_DRY_RUN=false
WOOCOMMERCE_STAGING_LIVE_TEST_MODE=true
WOOCOMMERCE_ALLOW_STOCK_WRITE=true
WOOCOMMERCE_ALLOW_ORDER_STATUS_WRITE=true
```

Allowed operation types:

- `update_product_stock`
- `update_variation_stock`
- `update_order_status`

Payload allowlists:

- Stock: `stock_quantity`, `stock_status`, `manage_stock`
- Order status: `status`

Disallowed:

- DELETE
- POST writes
- arbitrary endpoint writes
- customer writes
- coupon writes
- refund writes
- product metadata writes
- product edits beyond stock
- production WooCommerce writeback

## Product Sync Behavior

Implemented endpoints:
- `GET /api/integrations/woocommerce/status`
- `POST /api/integrations/woocommerce/products/preview`
- `POST /api/integrations/woocommerce/products/commit`
- `GET /api/integrations/woocommerce/sync-runs`
- `GET /api/integrations/woocommerce/sync-runs/{id}`

Sync-run history is returned newest-first with bounded server pagination. The
list endpoint defaults to 50 rows, accepts `page` and `page_size` (maximum 100),
and reports the complete filtered total separately from the returned row count.
Sync-run detail returns retained errors newest-first in bounded pages using
`error_page` and `error_page_size` (default 50, maximum 100), with an exact
retained-error total and standard page metadata.

Order-fetch job history is also database-paged (`page`, `page_size`; default 20,
maximum 100) and reports the exact number of order-fetch jobs without loading
unrelated sync runs. Woo remap mappings and candidates use database-backed
pages (default and maximum 100). Candidate ordering remains catalog records
first, then every unique error-only remote record in retained sync history.
For repeated errors on the same Woo product/variation, the newest error supplies
the candidate metadata. Counts, filters, and page boundaries are calculated in
SQL, while mappings and suggestion rows are bulk-loaded for only the requested
page.

The settings UI calls preview/commit in pages of Woo parent products. Each
backend batch fetches:
- simple products;
- variable products;
- all variations for variable products.

Existing items are matched by an exact unique SKU, then by an exact unique
barcode only when SKU did not match. Existing item IDs and Pongo-owned fields
are preserved; only Woo mapping/snapshot metadata is attached. Woo records
without a local match create a new `inventory_items` row. Duplicate local or
remote SKUs and mapping conflicts are reported and left unchanged.

## Variation Sync Behavior

Every WooCommerce variation creates or updates one `inventory_items` row. Parent variable products are not sellable stock units unless WooCommerce exposes them as a simple sellable product.

Example:
- Dog Food Can 100g -> one item
- Dog Food Can 200g -> one item
- Dog Food Can 500g -> one item

## WooCommerce Fields For Newly Created Items

New Woo-only items may receive:
- Woo Product ID
- Woo Variation ID
- SKU
- Product name or variation name
- Description
- Category
- Image URL
- Stock quantity
- Stock status
- Regular price
- Sale price
- Weight
- Length
- Width
- Height
- Brand, when available through taxonomy or metadata
- Woo Product Type
- Woo Permalink
- Woo Status
- Woo Manage Stock
- Woo Stock Status
- Woo Stock Quantity Snapshot
- Woo Last Synced At
- Woo Sync Status
- Woo Sync Error

## Pongo OS-Owned Fields

These fields must not be overwritten by refresh:
- Manufacturer
- Manufacturer Website
- Client
- Warehouse
- Inventory Location
- Default Location
- Allocated
- Sellable
- Under Par
- On Order
- Unit of Measurement
- Recommended Retail Price
- Unit Cost
- Default Econ Order
- Default Lead Time Days
- Par Level
- Assembly
- Serializable
- Track Lot
- Perishable
- Re-Order
- Storage Volume
- Manual brand override
- Location stock
- Received inventory data
- Cycle count data
- Route data

Barcode rule:
- Barcode may be filled from a clearly dedicated Woo barcode/meta field only
  for a newly created item. Existing Pongo barcodes are preserved.

Woo stock rule:
- WooCommerce stock quantity is stored only as `woo_stock_quantity_snapshot`.
- Local Pongo OS `In Stock` is not overwritten by WooCommerce product sync.
- Existing descriptions, categories, brands, prices, costs, locations, expiry
  records, and all other Pongo-owned fields are not overwritten.

## Refresh Summary

Refresh should return:
- created_count
- updated_count
- skipped_count
- error_count
- errors

## Product and Variation Normalization

Simple products:
- `remote_type = simple`
- `woo_product_id = product.id`
- `woo_variation_id = null`
- SKU is required for auto-create.
- Product name/description/category/brand/prices/status/stock snapshot/weight
  and dimensions are normalized into local sync-safe fields.

Variations:
- `remote_type = variation`
- `woo_product_id = parent product.id`
- `woo_variation_id = variation.id`
- SKU is required for auto-create.
- Description is generated from parent product name plus variation attributes.
- Parent category/brand are used when variation data does not provide them.
- Variation dimensions fall back to parent dimensions where practical.

Variable parent products are not inventory items by themselves unless they are
represented as directly sellable records. The current sync imports variations
for variable products and skips blank-SKU records.

## Matching Rules

Remote sellable records match local items in this order:
1. Same Woo Product ID and Woo Variation ID.
2. Exact SKU match.
3. Exact Barcode match.

If SKU and Barcode point to different local items, the row is marked conflict
and is not committed. Product name is not used as a primary match key. Local
items missing from WooCommerce are not deleted or deactivated.

## Preview and Commit

Preview:
- Fetches WooCommerce products/variations.
- Returns create/update/skip/conflict/error rows.
- Does not write local items.
- Does not create stock movements.
- Does not write WooCommerce.

Commit:
- Fetches WooCommerce products/variations again.
- Creates or updates local Pongo OS items only.
- Stores sync run history and row-level sync errors.
- Skips blank-SKU records and conflicts.
- Never writes WooCommerce products, orders, or stock.

## Remap Behavior

Remap allows staff to link or relink a local item to WooCommerce using:
- Woo Product ID
- Woo Variation ID
- SKU
- Barcode
- Product name

Use cases:
- SKU changed
- Variation mapping broke
- Product was imported manually first
- Duplicate SKU issue
- Product not linked correctly

## Order Sync Behavior

Implemented endpoints:
- `GET /api/integrations/woocommerce/status`
- `POST /api/integrations/woocommerce/orders/preview`
- `POST /api/integrations/woocommerce/orders/commit`
- `POST /api/integrations/woocommerce/orders/quick-sync`
- `POST /api/integrations/woocommerce/orders/history-import`
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
- `GET /api/orders/open/export`

Order sync pulls requested WooCommerce orders into local `orders` and
`order_items` snapshot tables. The default operational statuses are
`processing`, `on-hold`, and `pending`, configured through
`WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES`.

Requested statuses such as `processing`, `on-hold`, and `pending` can be stored
as local snapshots, but only `processing` is operational for allocation and
picking. Pending, on-hold, completed, cancelled, failed, refunded, and other
non-processing snapshots do not reserve new stock and do not appear in Open
Orders, Allocate, or Pick Orders. They can still feed sync history, the Business
Dashboard, and Pongo Insights.

The dedicated worker dyno owns periodic order reconciliation. It is enabled by
default when WooCommerce reads are configured and queues a pass every 120
seconds. Every pass reads every active order so processing, pending, and on-hold
orders cannot be skipped by a stale modified-time cursor. Terminal statuses use
the previous successful remote-scan time as their incremental cursor.
Active and terminal statuses are committed in batches of 25, so a large Woo
history never lives in web-dyno memory. The default terminal set includes
completed, failed, cancelled, and refunded orders.

The separate historical reporting import scans the complete order history
across all standard and custom statuses as GET-only pages of up to 100. Its next page,
frozen cutoff, retry count, and date coverage persist in
`woocommerce_sync_runs.progress`, so a worker restart resumes at the last
committed page. Newly discovered historical orders are marked
`is_historical_snapshot`; they are available to Insights and Reports but are
excluded from Open, Allocate, Pick, Completed Operations, and Routes. The
history path never changes stock or allocation quantities and never writes to
WooCommerce. Only after Woo pagination and distinct-order coverage are fully
verified does a rerun mark snapshots no longer returned by WooCommerce as
source-absent; those rows remain stored for audit but stop contributing to
intelligence. Active processing, pending, and on-hold orders continue through
the normal two-minute reconciliation.

Pongo OS is single-store by design. Once local orders exist, changing the
WooCommerce host is blocked; a different store requires an isolated database
so order IDs, history, and reporting cannot be mixed across stores.

Every worker attempt is stored in the existing WooCommerce sync ledger.
`GET /api/integrations/woocommerce/status` exposes whether the scheduler is
running, healthy, stale, or degraded, plus its last attempt, success, failure,
error count, and safe error message. `completed_with_errors` advances the
modified-time cursor but remains degraded until a clean pass succeeds.
Before the first ledger entry is committed, status reports that the first
reconciliation is starting instead of incorrectly calling it stale.

`POST /api/integrations/woocommerce/orders/fetch-now` queues one priority
manual pass. Duplicate clicks reuse the queued/running job. The worker checks
the queue every five seconds and restarts its Python interpreter after every
order, stock, or historical-order page to return retained memory to the dyno.

The browser no longer posts `orders/quick-sync` on a timer. It may refresh local
Pongo order views with GET requests, while the signed webhooks and server job
remain responsible for ingestion. The quick-sync endpoint remains available
for an explicit operator-triggered import and is also reused once by the backend
immediately after credentials are saved.

Completing a picked order immediately sends its final local stock quantities
and completed order status through the guarded WooCommerce writeback path.
Separately, the worker creates one forced, resumable full-catalog stock job at
the first cycle after midnight in `ADMIN_TIMEZONE` (default
`America/Edmonton`). `WOOCOMMERCE_DAILY_FULL_STOCK_SYNC_ENABLED=false` disables
that nightly reconciliation. Its date-based idempotency key prevents duplicate
jobs after worker restarts.

## Signed Order Webhook: Phase 1

Endpoint:

- `POST /api/integrations/woocommerce/webhooks/orders`

The receiver is disabled by default. Enabling it requires:

```bash
WOOCOMMERCE_WEBHOOK_ENABLED=true
WOOCOMMERCE_WEBHOOK_SECRET=<distinct random secret of at least 32 bytes>
WOOCOMMERCE_WEBHOOK_MAX_BODY_BYTES=1048576
WOOCOMMERCE_ALLOWED_HOST=<expected WooCommerce source host>
```

`WOOCOMMERCE_ALLOWED_HOST` must be nonblank and must exactly match the source
hostname. The delivery URL must be a public HTTPS backend URL; `127.0.0.1` and
`localhost` cannot receive a webhook from a remote WooCommerce site.

The backend verifies a base64 HMAC-SHA256 signature over the exact raw body,
then validates `X-WC-Webhook-Source`, topic, resource, event, webhook ID,
delivery ID, content type, body size, and order payload shape. Re-encoding parsed
JSON before verification is not valid because the signature covers the bytes as
delivered. WooCommerce’s header contract is described in its
[webhook documentation](https://developer.woocommerce.com/docs/apis/rest-api/v2/webhooks),
and the exact signature generation is visible in the current
[`WC_Webhook` implementation](https://woocommerce.github.io/code-reference/files/woocommerce-includes-class-wc-webhook.html).

When WooCommerce first activates a webhook it sends an unsigned setup ping. The
receiver accepts only the exact body `webhook_id=<positive integer>` with no
signature, returns a ready/no-op response, and changes no order or ledger data.
Unsigned JSON is rejected.

Phase-1 scope:

- Only authenticated `order.created` imports a local order snapshot.
- If its WooCommerce `date_modified` is older than or equal to the matching local order's
  snapshot, the signed delivery is audited as ignored so delayed delivery
  cannot regress newer REST or webhook data.
- Other authenticated, internally consistent topics such as `order.updated`
  are recorded as `ignored` and return success without changing an order.
- Imported active orders go through the existing matching and safe local
  auto-allocation path.
- Import may increase local `Allocated` and create allocation/audit rows, but
  never reduces `In Stock`, creates a stock movement, or writes WooCommerce.
- The receiver does not send customer email, SMS, browser push, or any other
  outbound notification.

Every authenticated JSON delivery has a durable
`woocommerce_webhook_deliveries` row identified by webhook ID, delivery ID, and
the SHA-256 hash of the raw body. Terminal replays increment `attempt_count` and
return a duplicate response without repeating order import, allocation, or staff
notification. The ledger stores the payload hash and safe metadata instead of a
second copy of the customer payload.

## Internal New-Order Event Feed

Endpoint:

- `GET /api/integrations/woocommerce/webhooks/events?after_id=<cursor>&limit=50`
- `GET /api/integrations/woocommerce/webhooks/events?initialize=true&limit=50`
  to establish a new session baseline without returning historical events

The feed reads immutable `woocommerce_order_events` outbox rows created only
when a webhook transaction successfully creates a local order. Each event
contains safe order-summary fields needed by the internal staff UI notice.
`latest_event_id` is the informational order-event high-water mark.
`next_after_id` is the safe cursor for the next request; the client drains pages
with `after_id=next_after_id` while `has_more=true`. Replayed, stale, ignored,
failed, and update-only deliveries do not create a new-order notice. If a failed
delivery later succeeds, its outbox ID is assigned only at the successful
commit, so an earlier cursor cannot skip it.

The frontend establishes its baseline with `initialize=true`, polls the feed
every 15 seconds while visible and on focus/visibility changes, and deduplicates
events by immutable outbox ID. Later `order_created` events create a persistent
dismissible toast and session-only Bell history/unread badge. Update and
cancellation events refresh local order data but are never announced as new
customer orders. These notices do not acknowledge events globally, call
WooCommerce, or send a customer-facing notification.

Order sync is read-only against WooCommerce:
- no WooCommerce order status writes;
- no WooCommerce product or stock writes;
- no local item In Stock changes;
- local allocation quantity changes are allowed only through FIFO
  auto-allocation for active processing orders or audited release when an order
  leaves processing;
- no stock movements;
- no receiving, cycle count, picking, fulfillment, completion, or route
  workflow side effects.

Line matching rules:
1. Woo Product ID + Woo Variation ID.
2. Exact SKU.
3. Exact Barcode from Woo order line metadata.

If these identifiers match different local items, the line is marked
`conflict`. If no local item matches, the line is marked `unmatched`. Order sync
does not create missing items.

Availability snapshot:
- `sellable_snapshot = item.In Stock - item.Allocated`
- `available` when sellable covers ordered quantity
- `partial` when some sellable exists but not enough
- `unavailable` when a matched item has zero sellable quantity
- `unknown` when the line is unmatched or conflict
- `shortage_quantity = max(quantity_ordered - sellable_snapshot, 0)`

Preview:
- Fetches requested orders.
- Returns order and line actions, match statuses, availability snapshots, and
  warnings/errors.
- Does not write local orders or order lines.

Commit:
- Fetches requested orders again.
- Creates or updates local order/order line snapshots.
- Runs safe oldest-first local auto-allocation for active processing orders
  after the sync batch is stored.
- Stores sync run history with `sync_type = orders`.
- Stores sync errors for unmatched, conflict, and skipped rows. Requested
  non-open WooCommerce statuses are not skipped; they are stored as local
  read-only snapshots.
- Does not pick, route, fulfill, complete, reduce In Stock, create stock
  movements, or write WooCommerce.

## Auto-Allocation After Order Sync

Allocation is a local Pongo OS workflow after WooCommerce order sync. It uses
local `orders`, `order_items`, `inventory_items`, and
`inventory_item_locations` only. Only active `processing` orders participate.
The queue uses WooCommerce `date_created ASC`, then local order ID ASC as a
deterministic tie-breaker; missing order dates sort after dated orders.

Allocation:
- previews recommended reservation quantities without writing data;
- increases local item-location and aggregate Allocated on commit;
- leaves local item In Stock unchanged;
- recalculates Sellable as In Stock minus Allocated;
- updates local order line `quantity_allocated`;
- creates local `allocations`, `allocation_lines`, and
  `inventory_audit_events` rows;
- can split a single order line across multiple active locations when needed;
- reserves available partial quantities for the oldest competing order before
  a newer order can use the same stock;
- marks shortages, unmatched lines, conflicts, partial allocation, and no
  location stock as allocation exceptions for the Allocate view;
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not pick, route, fulfill, create shipping labels, or notify customers.

Order sync preserves existing local allocation quantities when refreshing the
same processing order. After the full sync batch is stored, it runs one FIFO
reconciliation pass so a newest-first WooCommerce response cannot jump ahead of
an older local processing order.

FIFO allocation is also retried after direct, bulk, and scanner receiving;
standard and scanner stock adjustments; standard and scanner cycle counts;
completion releases; and synchronized WooCommerce status changes that release
unpicked allocations. Staff can explicitly run the same idempotent queue pass
through `POST /api/allocations/auto/commit`.

`GET /api/allocations/exceptions` supplies the shortage-only Allocate workspace.
It returns unresolved processing-order lines by default, with ordered,
allocated, unallocated, picked, and currently available quantities. Fully
allocated lines are returned only when explicitly requested.

When a previously allocated order changes from `processing` to a
non-processing WooCommerce status, Pongo OS releases its remaining unpicked
allocation, records deallocation audits, removes the order from operational
queues, and gives the released stock to the next eligible FIFO order. Quantity
already picked is not released.

## Picking After Allocation

Picking is a local Pongo OS workflow after allocation and is the local stock
reduction point. It uses local `orders`, `order_items`, `inventory_items`,
`inventory_item_locations`, `picks`, `pick_lines`, `stock_movements`, and
`inventory_audit_events` only.

Picking:
- previews recommended pick quantities from already allocated order lines;
- rejects unallocated, unmatched, conflict, unknown item, overpicked, and fully
  picked lines;
- updates local order line `quantity_picked` and legacy `picked_qty` on commit;
- updates local order line `quantity_stock_reduced`;
- reduces local item-location and aggregate In Stock;
- reduces local item-location and aggregate Allocated;
- recalculates local Sellable;
- creates local `picks`, `pick_lines`, and `inventory_audit_events` rows;
- creates local `stock_movements` rows with
  `movement_type = pick_stock_reduction`;
- supports scanner idempotency keys so retrying a scan does not double-reduce
  stock;
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not route, fulfill, create shipping labels, or notify customers.

Order sync should preserve existing local picked quantities when refreshing the
local order snapshot.

## Completion And Fulfillment Compatibility

Completion is a local Pongo OS workflow after picking or as an explicit
complete-without-picking exception. Fulfillment remains for compatibility and
history. These paths use local `orders`, `order_items`, `fulfillments`,
`fulfillment_lines`, and `inventory_audit_events` only in the normal picked
path because stock was already reduced during picking.

Completion/fulfillment compatibility:
- completing a picked order marks it completed/closed and does not reduce stock
  again;
- completing without picking marks it completed/closed, releases remaining
  local allocation, and records that stock was not reduced;
- fulfillment on an already stock-reduced picked order creates compatibility
  records and returns a warning that stock was already reduced during picking;
- fulfillment on an unpicked order is blocked instead of silently reducing
  stock through the old path;
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not route, create shipping labels, create purchase orders, manage
  suppliers, or notify customers.

Order sync should preserve existing local fulfilled quantities when refreshing
the local order snapshot.

## Fulfillment Reporting

Fulfillment Report and Completed Orders export are local read-only reporting
surfaces. They read from `fulfillment_lines`, `fulfillments`, local `orders`,
local `order_items`, and local `inventory_items`.

Reporting:
- calculates fulfilled value from local fulfilled quantity and local item unit
  cost;
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not change local item In Stock or Allocated;
- does not create stock movements or audit events;
- does not route, create shipping labels, create purchase orders, manage
  suppliers, or notify customers.

## Route Creation

Route Creation uses completed local orders after fulfillment. It reads local
orders and writes local `routes` and `route_stops` only.

Routing:
- includes local orders with `fulfilled` or `partially_fulfilled` status;
- excludes orders already assigned to a non-cancelled route;
- previews selected order IDs before writing route records;
- creates route-stop snapshots for Woo order number/ID, customer contact,
  shipping summary, and local order status;
- can finalize or cancel local routes;
- can export one local route CSV.

Route creation:
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not call maps, geocoding, routing, or optimization providers;
- does not create shipping labels, delivery tracking events, or customer
  outbound/customer notifications;
- does not change local item In Stock, Allocated, Sellable, On Order, stock
  movements, inventory audit events, order item quantities, or order status.

## Stock Update Safety

Stock-changing local actions must always create stock movement rows.
WooCommerce stock updates must happen through the backend only, from guarded
jobs or queued previews, with dry-run true by default and no DELETE support.

## Local Remap Metadata

WooCommerce remap endpoints are implemented under
`/api/integrations/woocommerce/remap/*`.

Remap behavior:
- Uses local synced item metadata and sync error rows as candidate sources.
- Previews a proposed Woo product/variation to local item mapping.
- Commits by deactivating previous active local mappings for that Woo
  product/variation and creating a new active `woo_item_mappings` row.
- May update local item Woo ID metadata.
- Does not call WooCommerce.
- Does not write WooCommerce products, orders, statuses, or stock.
- Does not overwrite manual Pongo OS fields.
- Does not mutate local stock, allocated, sellable, picked, fulfilled, route,
  or order status quantities.

## Stock Writeback Workflow

Pongo OS sends stock only through the guarded backend writeback queue. The
frontend never receives credentials and never calls WooCommerce directly.

Current behavior:
- Frontend still never calls WooCommerce directly.
- WooCommerce credentials are configured through the authenticated Pongo UI and
  remain encrypted in backend PostgreSQL storage.
- A successful pick reduces local stock only; it does not change WooCommerce
  stock until that picked order is completed.
- Completing a picked order creates, approves, and sends one stock writeback
  queue item for each changed mapped inventory item.
- Completing an unpicked order does not reduce stock and does not create a
  stock writeback. Completion sends only the order-status writeback.
- Manual stock adjustments, including scanner adjustment commits, send the
  changed mapped item after the audited local adjustment commits.
- `POST /api/integrations/woocommerce/writeback/stock/sync` with `force=false`
  retries only mapped items whose local `sellable` differs from the last
  successful WooCommerce stock snapshot.
- The same endpoint with `force=true` resends every active mapped inventory
  item, even when its snapshot already matches.
- Successful sends update `woo_stock_quantity_snapshot`; failed sends remain in
  the audited queue and leave the local stock commit intact.
- Unmapped items are skipped and reported in the synchronization response.
- Before skipping an unmapped item, stock sync may recover its product and
  variation IDs from previously matched WooCommerce order lines. Recovery is
  allowed only when every matched line points to one unambiguous remote item.
- Stock writes send both `stock_quantity` and the matching `stock_status`
  (`instock` above zero, `outofstock` at zero). The quantity is local Sellable
  (`In Stock - Allocated`) so open-order reservations are not offered twice.
- Bulk receiving, cycle counts, and transfers remain local-only unless they use
  a separately documented writeback path.
- Expanded reports read local tables only.
- Local remap search in Items is candidate search only; actual remap remains
  local metadata and does not call WooCommerce.

## Pongo Insights Safety Boundary

Pongo Insights reads local WooCommerce order snapshots, local order lines, and
local inventory item fields. It does not call WooCommerce from the frontend or
backend, and it does not write WooCommerce products, orders, statuses, stock, or
subscription records.

If subscription, refund, coupon, payment, or address fields are not present in
local snapshots, Insights returns empty states or `data_quality` warnings. It
does not fake metrics.

## Business Dashboard Safety Boundary

The default Dashboard reads local WooCommerce order snapshots for today's
business metrics, open orders, revenue comparison, and city-level order
geography. It does not call WooCommerce live, does not write WooCommerce, and
does not update local order or inventory state.

Subscription cards remain empty with a data quality warning until subscription
snapshots are synced locally. Map markers use exact local coordinates only when
already stored; otherwise supported cities use approximate city-level markers.

## Import Mappings Identity And Ownership

Import Mappings matches exact variation ID first, exact simple product ID with a
null variation ID second, an existing explicit mapping third, and exact unique
SKU only when Woo IDs are absent. Otherwise it reports a conflict. It never
matches by name or chooses silently between duplicate SKUs.

A simple product becomes one stock item. Every purchasable variation becomes an
independent item with the parent in `woo_product_id` and the exact child in
`woo_variation_id`. Variable parents are skipped reference containers and
cannot hold inventory, allocate, pick, receive a barcode, or receive stock
writeback. An independently purchasable variable parent requires manual review.

Woo owns storefront IDs/type, names/descriptions, variation attributes, SKU,
categories/image, Woo prices, Woo dimensions/weight, publication/stock status,
stock snapshot, and sync timestamps. Pongo owns barcode, cost, brand override,
manufacturer data, UOM, warehouse/location, operational and allocated stock,
reorder data, local metadata, and all operational history. Repeated runs are
idempotent and refresh only Woo-owned fields.

Before stock queue approval/send, mapping is revalidated. Missing, ambiguous,
inactive, incomplete variation, duplicate-target, or stale queue targets fail
closed. Pending/failed stock rows may be explicitly revalidated, which rebuilds
the current target and absolute quantity and returns the row to pending
approval. Completed and dry-run history is never changed or automatically sent.
Remap remains preview-first, local-only, stock-neutral, and audited.

For later catalog additions, run Import Mappings again: a new simple product
creates one item; a new purchasable variation creates one item; existing items
receive only allowed Woo-owned refreshes.
