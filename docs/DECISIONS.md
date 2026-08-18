# Architecture Decisions

## ADR-001: Standalone App Instead of Plugin

Decision: Pongo Inventory OS will be a standalone app, not a WordPress or WooCommerce plugin.

Reason: Operational inventory workflows, credentials, reports, and future routing features should live outside the storefront runtime.

## ADR-002: FastAPI Backend

Decision: Use FastAPI for the backend.

Reason: It is lightweight, typed, testable, and a good fit for API-first inventory workflows.

## ADR-003: PostgreSQL Database

Decision: Use PostgreSQL as the system of record.

Reason: Inventory, orders, receipts, stock movements, and route data need relational integrity and strong querying.

## ADR-004: React Frontend

Decision: Use React for the admin frontend.

Reason: The app needs a standalone operational dashboard with tables, forms, filters, and scanning workflows.

## ADR-005: WooCommerce REST API Integration

Decision: Integrate through WooCommerce REST API from the backend only.

Reason: WooCommerce remains storefront source, while frontend credentials must never be exposed.

## ADR-006: Read-Only WooCommerce Sync First

Decision: Start with read-only product and variation sync.

Reason: Stock writeback should wait until mappings, local workflows, and audit behavior are stable.

## ADR-007: Stock by Location

Decision: Use `inventory_item_locations` as the operational source for
item/location stock splits. `inventory_items` keeps aggregate `in_stock`,
`allocated`, `sellable`, and `on_order` totals for compatibility and fast UI
display.

Reason: A SKU can exist in multiple physical locations, and totals must be derived from those rows.

Update 2026-07-07: Stock by Location v2 is implemented. Receiving, cycle count,
allocation, picking, and fulfillment compatibility now resolve item-location
rows. Transfers and explicit adjustments are local-only workflows. WooCommerce
writeback remains disabled.

## ADR-008: Direct Receiving Without PO

Decision: Build direct receiving only.

Reason: Pongo does not use purchase orders.

## ADR-009: Focused Order Workflow Views

Decision: Support focused Orders views: Open Orders, Allocate, Pick Orders,
Completed Orders, and Order History.

Reason: Pongo needs Zenventory-style warehouse operations without complex
enterprise delivery stages. The same active order can appear in Open Orders and
Pick Orders when allocated, while Allocate is reserved for exceptions.

## ADR-010: Routes as Separate Module

Decision: Route creation and optimization will be a separate module.

Reason: Routing should not complicate inventory receiving or picking workflows.

## ADR-011: Backend Foundation Before Workflow Logic

Decision: Scaffold FastAPI, SQLAlchemy models, Alembic migrations, environment
configuration, CORS, placeholder routers, and tests before implementing
WooCommerce sync or stock-changing workflows.

Reason: The system needs a stable local backend and database foundation before
adding operations that mutate inventory, allocate orders, receive stock, or call
external services.

Safety: Environment examples contain placeholders only. WooCommerce and map
provider credentials are not committed, and no external WooCommerce or map API
calls are attempted in the scaffold.

## ADR-012: Direct Receiving Is the First Stock-Changing Workflow

Decision: Implement direct receiving without purchase orders as the first
stock-changing workflow.

Reason: Pongo receives inventory directly and needs item stock increases before
cycle count, allocation, picking, or WooCommerce stock writeback are safe.

Safety: Direct receiving validates the full receipt before commit. If any line
is invalid, no item stock is changed. Every successful received line creates a
stock movement/audit row. Unit cost is stored on receipt lines and movements but
does not overwrite item Unit Cost in this phase.

## ADR-013: Received Inventory Report Uses Receipt Lines

Decision: Generate the Received Inventory Report from receipt headers and
receipt item rows, enriching from item and location master data as needed.

Reason: Receipt lines are the operational source of truth for what was received,
while stock movements are the immutable audit trail for stock changes. Reporting
from receipt lines keeps received inventory audit views aligned with receiving
sessions, receipt numbers, reference numbers, line notes, and receipt notes.

Safety: The report endpoints are read-only. They do not modify inventory,
create stock movements, call WooCommerce, or introduce purchase order, supplier,
cycle count, allocation, picking, route, or fulfillment workflows.

## ADR-014: Cycle Count Posts Atomic Stock Adjustments

Decision: Implement Cycle Count as the second stock-changing workflow after
Direct Receiving, with preview and atomic commit endpoints.

Reason: Staff need to compare physical stock with system stock and post audited
adjustments without connecting WooCommerce stock writeback yet. Preview lets
staff review variances before stock changes, while commit revalidates the full
payload and rejects the entire count if any line is invalid.

Safety: Cycle Count updates item In Stock only on posted variance lines, leaves
Allocated unchanged, recalculates derived item fields, creates cycle count
header/line records, and creates stock movement rows only for adjusted lines.
No WooCommerce calls, credentials, external APIs, purchase orders, supplier
workflows, allocation, picking, route, or fulfillment workflows are added.

## ADR-015: WooCommerce Product Sync Is Read-Only Against WooCommerce

Decision: Implement WooCommerce product and variation sync as a backend-only,
read-only integration with preview and local-only commit.

Reason: Pongo needs stable mappings between WooCommerce sellable records and
local inventory items before order sync, allocation, picking, or stock writeback
can be safely introduced. Preview lets staff inspect creates, updates, skips,
and conflicts before any local database changes.

Safety: WooCommerce credentials are accepted only by the authenticated backend,
encrypted in PostgreSQL with a backend environment key, and never exposed in
API responses or frontend code. The sync client only
implements read methods. Commit creates or updates local Pongo OS items only,
preserves manual operational fields, stores Woo stock as a snapshot, creates no
stock movements, and never writes WooCommerce products, orders, or stock.

## ADR-016: WooCommerce Order Sync Is Read-Only and Local-Only

Decision: Implement WooCommerce order sync as a backend-only integration with
preview, local order snapshot commit, and local-only auto-allocation for active
open orders.

Reason: Pongo needs imported WooCommerce orders to enter the warehouse workflow
without manual reservation when enough local stock is available. Preview lets
staff inspect unmatched lines, conflicts, and shortages before local order
snapshots are stored, while commit can safely reserve stock locally for
matched, fully available active orders.

Safety: Order sync reads WooCommerce orders only. Preview writes nothing.
Commit creates or updates local `orders` and `order_items` rows, stores sync
run/error history, preserves unmatched/conflict lines for review, and may
auto-allocate active open orders. Auto-allocation increases local Allocated and
creates allocation/audit rows only. It does not create inventory items, pick,
route, fulfill, reduce In Stock, create stock movements, or write WooCommerce
orders/products/stock.

## ADR-017: Allocation Reserves Local Sellable Inventory Only

Decision: Implement Allocation as a local reservation workflow that increases
item Allocated, leaves item In Stock unchanged, recalculates Sellable, updates
local order line allocation quantities, and creates dedicated allocation audit
events.

Reason: Allocation is not a physical stock movement. It reserves inventory for
orders before picking, so overloading stock movements would blur physical stock
changes with reservation state changes.

Safety: Allocation is atomic and cannot make Allocated exceed In Stock or
allocate more than current Sellable. Allocation creates `allocations`,
`allocation_lines`, and `inventory_audit_events` rows, but it does not create
stock movement rows, reduce In Stock, pick items, create routes, fulfill
orders, change WooCommerce order status, update WooCommerce stock/products, or
call WooCommerce write APIs.

## ADR-018: Picking Reduces Local Stock

Decision: Implement Picking as the local stock reduction workflow against
already allocated order quantities. Picking creates `picks`, `pick_lines`,
`stock_movements`, and `inventory_audit_events` rows, updates local order line
picked quantities, tracks stock-reduced quantity, reduces item-location In
Stock and Allocated, and updates order pick status.

Reason: In Pongo's Zenventory-style workflow, the warehouse pick is the moment
stock leaves local on-hand inventory. Completing or fulfilling later should not
remove stock a second time.

Safety: Picking is atomic and cannot pick more than allocated or more than the
remaining quantity to pick. Picking cannot make In Stock or Allocated negative
and cannot leave Allocated greater than In Stock. Picking is idempotent for
scanner commits with an idempotency key. It does not fulfill orders, create
routes, create labels, notify customers, or write WooCommerce order status,
products, or stock.

## ADR-019: Completion Closes Orders Without Stock Reduction

Decision: Implement local order completion as the closing step after picking or
as an explicit complete-without-picking path. Completion marks local orders
completed/closed, releases remaining unpicked allocations when needed, and
creates audit events. Completion never reduces stock.

Reason: Picking already removed stock from local inventory. Completion is an
administrative close of the customer order, not a second inventory movement.
The complete-without-picking path is useful for exceptions and must clearly
record that stock was not reduced.

Safety: Completing a picked order does not reduce stock again. Completing an
unpicked order does not reduce stock and releases remaining local allocation.
Completion creates an audited, allowlisted backend writeback that sets only the
linked WooCommerce order status to `completed`. It does not write WooCommerce
products or stock, does not create routes, does not create shipping labels, does not send
outbound/customer notifications,
and does not add purchase order or supplier workflows.

## ADR-020: Fulfillment Compatibility And Reports Are Read-Only

Decision: Preserve fulfillment endpoints for compatibility and reporting, but
remove fulfillment as the normal stock-reduction step. Fulfillment Report reads
local fulfillment/completion records, and Completed Orders reads local
completed, closed, fulfilled, partially fulfilled, and completed-without-picking
orders.

Reason: Existing records and integrations may still reference fulfillment, but
the warehouse workflow now reduces stock during picking. Reports should explain
what happened without causing new inventory or WooCommerce side effects.

Safety: Fulfillment does not double-reduce stock after picking. Unpicked
fulfillment is blocked instead of silently reducing stock through the old path.
Fulfillment report and completed-order endpoints do not modify item stock,
Allocated, orders, fulfillment records, stock movements, audit events, or
WooCommerce. They do not add route, shipping label, outbound/customer
notification, purchase
order, or supplier workflows.

## ADR-021: WooCommerce Writeback Testing Is Staging-Only And Queued

Decision: Add a local `woo_writeback_queue` foundation for staging-only
WooCommerce writeback tests, limited to simple-product stock, variation stock,
and order-status updates.

Reason: Pongo needs to test real WooCommerce API write paths safely before any
production writeback exists. Preview, queue, approval, dry-run, and allowlisted
operation checks make each proposed write auditable and explicit.

Safety: Credentials remain backend env vars only. The frontend never calls
WooCommerce and never receives keys. DELETE is always blocked. Live send is
blocked unless environment is `staging`, live staging test mode is enabled,
read-only is false, writeback is enabled, dry-run is false, the base URL host
matches the allowed host, the method is `PUT` or `PATCH`, and the operation,
path, and payload fields are allowlisted. Product metadata, customer, coupon,
refund, POST, arbitrary endpoint, and production WooCommerce writebacks remain
disabled.

## ADR-022: Route Creation Is Local Manual Planning

Decision: Build route creation as a local planning foundation that uses
completed local orders only. Eligible candidates are locally completed/closed
orders, including legacy fulfilled compatibility statuses, with no
non-cancelled route. Route preview validates selected orders without writes.
Commit creates a `draft` route and route-stop snapshots, then
list/detail/export/finalize/cancel operate on local route records.

Reason: Pongo needs a route planning surface after local fulfillment, but map
provider selection, route optimization, labels, dispatch, delivery tracking,
outbound/customer notifications, and WooCommerce status writeback are separate
higher-risk
workflows.

Safety: Route creation does not call WooCommerce, maps, geocoding, routing,
shipping label, outbound/customer notification, purchase order, supplier, or
inventory stock
services. It does not change local item In Stock, Allocated, Sellable, On Order,
order status, stock movements, or audit rows. Cancelled routes retain stops for
review while making their orders eligible for future route planning.

## ADR-023: Command Center Is Read-Only Local Operations Data

Decision: Build the dashboard as a read-only Command Center over local records:
items, orders, routes, stock movements, audit events, receipts, cycle counts,
allocations, picks, fulfillments, sync errors, and import jobs.

Reason: Managers need one operational page for health, warnings, and recent
activity without triggering business workflows.

Safety: Dashboard endpoints do not mutate inventory, orders, routes,
WooCommerce, stock movements, or audit rows.

## ADR-024: Remap Is Local Metadata Only

Decision: Build WooCommerce remap as local metadata using `woo_item_mappings`
plus local item Woo ID metadata. Remap preview and commit never call
WooCommerce.

Reason: Staff need a way to recover broken product/variation links while
preserving the backend-only WooCommerce boundary and Pongo OS field ownership.

Safety: Remap does not update WooCommerce, stock, allocation, sellable, picked,
fulfilled, route, or order status quantities. Manual item fields are preserved.

## ADR-025: Route Providers Default To Disabled

Decision: Add route map/geocode/optimization architecture as local endpoints
with disabled/no-op provider behavior by default.

Reason: The UI can now support metadata, stop ordering, coordinate review, and
future provider integration without committing to Google, Mapbox, or another
paid routing provider.

Safety: No provider keys are exposed in frontend responses. No external
geocoding, maps, routing, optimization, WooCommerce, outbound/customer
notification, label, or
delivery tracking calls are made by the current implementation.

## ADR-026: Item Control Center Uses Local Activity Composition

Decision: Build item detail as a local control center assembled from existing
records: item rows, `inventory_item_locations`, stock movements, receipts,
cycle counts, adjustments, allocations, picks, fulfillments, local
orders, and item notes.

Reason: Operators need one place to inspect item state without duplicating
activity into a new event stream.

Safety: Item detail and activity endpoints are read-only except item notes and
metadata-only edit paths. Stock fields must still be changed through receiving,
cycle count, or adjustment workflows. Transfer backend infrastructure may exist,
but transfer UI is hidden from the active frontend workflow.

## ADR-027: Bulk Receiving Is One Local Receipt Session

Decision: Bulk receiving preview validates all rows without writes. Commit
creates one local receipt and one receipt item per valid row, updates
`inventory_item_locations`, recalculates aggregate item stock fields, and
creates stock movements.

Reason: Warehouse receiving needs fast multi-row scanner/cart entry while
preserving stock auditability.

Safety: No WooCommerce calls or writeback. Invalid rows block commit by
default. Stock is changed only through the location inventory service.

## ADR-028: Scanner Workflows Are Keyboard-Input Local Operations

Decision: Treat barcode scanners as keyboard input and expose local scanner
endpoints for inventory lookup, location lookup, receiving, cycle count, and
adjustment. Picking continues to use the existing order scanner. Transfer UI is
hidden from active scanner workflows.

Reason: Pongo can support warehouse devices without hardware-specific
integration or browser plugins.

Safety: Scanner commits are local only. Cycle count requires a reason when the
count differs from system quantity. Transfer and adjustment checks prevent
negative location stock.

## ADR-029: Expanded Reports Are Read-Only

Decision: Build inventory valuation, low stock/reorder, stock movement ledger,
item activity, location utilization, margin by SKU, receiving cost, and
adjustment/damage/loss reports from local tables only.

Reason: Reporting should explain operational data without changing stock,
orders, WooCommerce, or route state.

Safety: All expanded report endpoints are read-only and include CSV export
only.

## ADR-030: Pongo Frontend Design System

Decision: Use centralized CSS variables for Pongo blue `#0f149a`, blue hover
and active states, soft peach backgrounds, white/off-white surfaces, borders,
text colors, and status colors. Primary buttons use Pongo blue; secondary and
action buttons use consistent muted/outline controls.

Reason: The app must feel like a polished standalone Pongo operations system,
not a Zenventory clone or rough scaffold.

Safety: Tables must scroll inside `.table-scroll`; the page/body must not
overflow horizontally. Visible action controls must work, navigate to a real
workflow, or be disabled/removed. Frontend tests run with Vitest and Testing
Library through `npm test -- --run`.

## ADR-031: Pongo Insights Is Read-Only BI

Decision: Add Pongo Insights as a separate sidebar page and backend router.
Pongo-owned dimensions use local `orders`, `order_items`, and `inventory_items`;
unfiltered sales headlines use WooCommerce Analytics revenue statistics.

Reason: Pongo needs business intelligence and forecasting without disturbing the
operational Command Center or introducing WooCommerce writeback risk.

Safety: Insights endpoints are read-only, never expose credentials, never mutate
local stock or orders, and perform only backend WooCommerce GET requests. They
return explicit data quality warnings or empty states when a source is unavailable.

## ADR-032: Dashboard Is Business Home, Inventory Overview Is Operations

Decision: Rename the old operational Dashboard/Command Center to `Inventory
Overview` and add a new default `Dashboard` page for business metrics.

Reason: Pongo needs a business-facing landing page without losing the
operational inventory command center.

Safety: The combined Dashboard and detailed business sections read local order
snapshots. One isolated KPI endpoint reads only verified WooCommerce pagination
totals for active orders; it never writes WooCommerce, never exposes credentials
to the frontend, never substitutes local data on failure, and is blocked from
external access for demo users. The Dashboard does not call geocoding or map
providers, mutate local orders or inventory, or fake missing subscription data.

## ADR-033: Signed Order Webhooks With Durable Staff Events

Decision: Add a disabled-by-default backend receiver at
`POST /api/integrations/woocommerce/webhooks/orders`. It imports authenticated
`order.created` and `order.updated` payloads. It authenticates the exact raw body with
base64 HMAC-SHA256 using a separate secret of at least 32 bytes, verifies the
WooCommerce source host and related delivery headers, enforces a configured body
limit, and accepts WooCommerce's exact unsigned setup ping as a no-op.

Each authenticated JSON delivery is recorded in
`woocommerce_webhook_deliveries` and uniquely identified by webhook ID,
delivery ID, and raw-body SHA-256. Other authenticated topics are audited as
ignored. A delayed supported payload older than or equal to the local order
snapshot is also audited as ignored so it cannot regress newer data. Each
successful supported delivery creates an immutable
`woocommerce_order_events` audit row. The cursor endpoint exposes only
`order_created` rows for the dismissible internal staff notice, so an update is
never mislabeled as a new order.

Updates safely retire removed lines rather than deleting history, release only
unpicked excess allocation after quantity or status changes, and retain a
blocking exception if WooCommerce falls below already picked, fulfilled, or
stock-reduced quantities. Order workflow notes and inventory deallocation
events retain the reconciliation decisions. Each order uses a savepoint so a
failed reconciliation cannot partially mutate it.

Reason: New and changed storefront orders should enter Pongo OS without relying
on an open browser, while retries, duplicate deliveries, configuration mistakes,
and unsupported topics remain observable and safe. A durable delivery ledger
plus immutable event audit works across restarts, retries, and multiple backend
processes; an in-memory queue would not.

The frontend polls the cursor feed every 15 seconds while visible, maintains a
session-only Bell history/unread state, and uses nonzero quick-sync creation
counts as a sync-run-deduplicated fallback notice. Persistent or per-user
acknowledgement remains deferred until staff auth/RBAC exists.

Safety: The receiver is disabled until explicitly configured. The webhook
secret stays in backend environment variables and is never returned or logged.
The ledger stores safe metadata and a hash, not a second raw customer payload.
Webhook import may use the existing audited local auto-allocation path, but it
does not reduce In Stock, create stock movements, write WooCommerce, or send
outbound/customer notifications. Staff notices are local UI feedback only.

## ADR-034: Woo Identity First, CSV Enrichment Second

Decision: Import Woo simple products and purchasable variations into the
existing item/mapping model before applying local Zenventory enrichment. Simple
identity is product ID plus null variation ID; variation identity is parent
product ID plus exact variation ID. Variable parents are non-stock reference
containers. Exact unique SKU is fallback only after authoritative Woo/explicit
mapping checks; names and barcodes never drive catalog sync.

Enrichment is update-only and starts with protected mapping columns. Empty cells
preserve values, `__CLEAR__` is limited to safe local metadata, and expiry is
excluded. Optional opening stock writes audited location balances and defaults
off. Woo refresh owns storefront reference fields; Pongo owns operational
inventory, local enrichment, and history.

Reason: This creates one stable writeback target per sellable Woo record while
preserving richer Pongo/Zenventory data and preventing duplicate variations or
parent stock.

Safety: Preview is mandatory. Import and remap never write WooCommerce. The
existing queue/approval/send architecture is reused; missing, ambiguous,
incomplete, or stale mapping targets fail closed. Only pending/failed rows may
be explicitly revalidated and successful history stays immutable. Local
database reset is a guarded CLI operation, never a public API.

## ADR-035: Serialized, Retry-Safe Stock Mutations

Decision: Pick, unpick, receipt, transfer, and adjustment commits use one
durable request ledger keyed by operation plus idempotency key. The same
request replays its stored response; a changed payload with the same key fails
with HTTP `409`. PostgreSQL transactions take one shared stock/allocation
advisory lock, followed by deterministic `FOR UPDATE` locks on item aggregates
and their item-location rows.

Safety: Database checks independently reject negative stock, negative
allocation, negative sellable, and allocation greater than stock. Woo order
reconciliation uses the same lock path before releasing inventory.

## ADR-036: Open-Order Routes Use Keyless Google Maps Links

Decision: Add a read-only open-order planner above the existing completed-order
route-record workflow. It starts at `5855 99 Street NW, Edmonton, AB`, accepts
1–50 drivers, lists every routable operational open order for explicit staff
selection, and returns incomplete-address orders explicitly. Staff choose either
estimated-time balancing or direction-zone assignment. Estimated-time balancing
minimizes the spread of a deterministic workload estimate based on stop count,
delivery direction, and postal-area transitions. Direction mode assigns North,
South, East, West, and Central to one or more drivers; a driver may own several
directions and a direction may be shared. Postal-code suggestions can be
corrected per order before planning. The planner constructs Google Maps
directions URLs with `api=1`; each delivery link contains at most four stops so
it remains usable with the mobile-browser waypoint limit. Long driver runs are
split into numbered, continuous parts. Staff can open, copy, or natively share
each link.

Reason: Pongo needs a useful iPhone/Android dispatch workflow now without
embedding map credentials in React or introducing a paid routing provider.
The deterministic estimate is available without sharing addresses with a
provider, while Google Maps supplies actual live driving directions only after
a staff member opens a link.

Safety: Planning performs one read-only order query and writes no route, order,
inventory, stock movement, audit, or WooCommerce data. No address is sent to
Google until a staff member opens or shares a generated link. This is not
traffic-aware optimization, and the displayed minutes are explicitly an
estimate rather than a Google travel time. This is also not address validation,
geocoding, dispatch tracking, or proof of delivery. ADR-022 and ADR-025 still
govern saved completed-order route records and disabled paid-provider
integrations.

Amendment (2026-08-11): direction mode now uses the exact ten-zone set `N`,
`S`, `E`, `W`, `NE`, `NW`, `SE`, `SW`, `Central East`, and `Central West`.
Explicit driver assignments are authoritative; uncovered selected orders are
returned as unassigned rather than silently borrowing another zone. The live
planner and completed-order route records are separate subpages. A responsive
in-app overview plots verified coordinates when present and otherwise marks the
declared zone; Google Maps URLs remain the navigation authority.

## ADR-038: Scan Identity and Manual Stock Corrections Fail Safe

Decision: barcode-driven product lookup tries the scanned string and its
single-leading-zero alternate while keeping SKU comparison exact. Multiple
barcode matches return no item. Manual Inventory corrections send an absolute
`new_quantity`, including zero; reason text is optional and the backend supplies
the standard audit reason when blank.

Reason: legacy catalog barcodes are inconsistent about one leading zero, while
physical counts are final facts rather than increments. Centralizing both rules
prevents every scanner and stock-edit screen from implementing its own variant.

Safety: ambiguous scans never guess, final quantity cannot be negative or below
allocated stock, every accepted change still creates adjustment and movement
audit rows, and existing idempotency/locking/writeback behavior is unchanged.

## ADR-039: Subscription Demand Uses an Atomic Read-Only REST Snapshot

Decision: the backend worker reads active WooCommerce subscriptions every 15
minutes through WooCommerce REST and atomically replaces one normalized local
line snapshot only after every page succeeds. Dashboard, Insights, and Sales by
SKU join that snapshot to exact variation/product IDs, then a unique SKU
fallback, and compare official next-renewal quantities with current Pongo
sellable stock.

Reason: the supplied WordPress SQL is useful for manual validation but cannot
provide official upcoming renewal dates and would couple Pongo to Woo's private
database schema. A local snapshot keeps report and page reads fast and stable.

Safety: this integration is read-only, stores no Woo credentials in the
frontend, makes no direct WordPress/MySQL connection, never falls back from a
variation to parent stock, reports unmapped stock as unknown, and preserves the
last complete snapshot after any failed or partial refresh.

## ADR-037: Demo Access Uses an Isolated Mock Database

Decision: authenticate demo accounts in the normal user store, then rebind the
request session to a separately seeded in-memory database before any product
query runs. Demo users retain the full navigation and read surfaces, while only
explicitly non-persisting preview POSTs are allowed.

Reason: one centralized boundary protects every existing and future query
without adding demo filters throughout the application or copying the frontend.

Safety: production rows and integration configuration are never available to a
demo request. All mutations fail with `demo_read_only`; WooCommerce and Google
integration routes fail with `demo_external_access_blocked`. Seed records use
fictional names, `.example.test` emails, and reserved `DEMO-` identifiers.
