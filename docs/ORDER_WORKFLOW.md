# Order Workflow

Pongo Inventory OS now follows a Zenventory-style local order workflow:

1. Signed WooCommerce `order.created` and `order.updated` webhooks import and
   reconcile local orders; server-side periodic reconciliation remains the
   recovery path for missed deliveries.
2. Active `processing` orders enter the operational allocation queues. FooSales
   POS orders also enter the same queues when FooSales creates them directly as
   WooCommerce `completed` orders.
3. Processing orders are auto-allocated oldest first by WooCommerce
   `date_created`; equal timestamps use the local order ID as a deterministic
   tie-breaker, and missing dates sort after dated orders.
4. Available stock is reserved even when it can cover only part of an order.
   Fully allocated orders become pick-ready, while unresolved quantities go to
   Allocate for exception handling.
5. Pick Orders is where staff open an allocated order, enter the quantity
   physically picked for each product line, and confirm the pick. Picking
   reduces local stock.
6. Open Orders shows active processing and FooSales POS orders, newest first,
   until staff complete or close the order locally.

The read-only historical import is outside this workflow. It marks newly
discovered past orders as reporting snapshots, so they improve
Insights and Reports without appearing in allocation, picking, completion, or
route queues.

WooCommerce remains the storefront. Completing a Pongo OS order also marks the
linked WooCommerce order `completed` through the guarded backend writeback
queue. Allocation and picking remain local-only, and WooCommerce stock is not
written by this workflow.

## Order Ingestion And Staff Notice

Phase 1 accepts `POST /api/integrations/woocommerce/webhooks/orders` only when
the receiver is enabled, its separate secret is at least 32 bytes, the exact raw
body has a valid base64 HMAC-SHA256 signature, and the source host matches the
configured WooCommerce host allowlist. `order.created` and `order.updated` are
imported. Other authenticated topics are recorded as ignored for audit purposes.

Each authenticated delivery is recorded in
`woocommerce_webhook_deliveries`. The unique webhook ID, delivery ID, and raw
payload SHA-256 tuple makes retries idempotent. The ledger stores safe metadata
and the payload hash, not a second copy of the customer payload.

`GET /api/integrations/woocommerce/webhooks/events` is a cursor feed of
immutable new-order notification rows created by successful `order.created`
transactions. Successful updates also retain an immutable order-event audit row
but are excluded from this staff new-order cursor. The frontend
starts with `initialize=true`, then polls every 15 seconds while visible and
advances through `next_after_id`, draining all pages while `has_more` is true.
It uses later new-order events for a dismissible toast and session-only Bell
history. Update events reconcile the local order immediately but are not
announced as new orders; the browser's local GET refresh then displays the
change. This is not customer messaging and does not send email, SMS, browser
push, or a WooCommerce request.

The backend also runs a periodic, paginated reconciliation across every active
order and recently changed terminal orders. Terminal changes use a
modified-time overlap so a boundary update is safely seen again, and an
advisory lease prevents concurrent workers from running the same pass. The
frontend may refresh local views, but it does not trigger the ingestion job.
Scheduler health and the last durable success/failure are exposed through the
WooCommerce status endpoint and shown globally when operator attention is
required.

A signed `order.created` or `order.updated` payload older than or equal to the matching local order's
`date_modified` snapshot is audited as ignored. It cannot overwrite newer order
data.

## Views

An order can appear in more than one operational view:

- Open Orders: active processing and FooSales POS orders that are not locally completed or closed.
- Allocate: operational orders with unresolved quantities, shortages, unmatched
  lines, conflicts, unavailable location stock, or failed/partial
  auto-allocation. The default view excludes 100% allocated lines.
- Pick Orders: operational orders whose required inventory lines are fully
  allocated. Partially allocated orders remain in Allocate. Fully picked
  orders leave this queue and remain available for audited correction in Open
  Orders.
- Completed Orders: locally completed, closed, fulfilled, or completed-without-picking orders.
- Order History: allocation, pick, and legacy fulfillment/completion records.

Open Orders is for review, export, printing, local completion, and correction.
Its Open Customer Orders workspace follows the Zenventory-style layout with
separate order-number, customer, containing-item, and warehouse filters,
client-side results paging, a horizontally scrollable operational table, bulk
Actions, per-order actions, and a printable customer-order dialog. It does not
show the pick scanner or history panels.

## Auto-Allocation

Order sync runs FIFO auto-allocation after it has stored and matched the current
batch. Fetch and display order may be newest first, but reservation priority is
always oldest `date_created` first. This prevents the newest order in a sync
response from consuming stock owed to an older processing order.

Auto-allocation:
- considers processing orders and completed FooSales POS orders that remain locally active;
- uses `date_created ASC`, then local order ID ASC, with missing dates last;
- uses `inventory_item_locations` as the quantity source of truth;
- ignores inactive locations;
- prefers the default location, then locations with the highest sellable quantity;
- can split a single order line across multiple locations when needed;
- reserves `min(remaining ordered quantity, current sellable quantity)`, so an
  older order receives a partial reservation before a newer order can use the
  same stock;
- increases item-location and aggregate `Allocated`;
- recalculates `Sellable`;
- creates `allocations`, `allocation_lines`, and inventory audit events;
- does not reduce `In Stock`;
- does not create stock movement rows;
- does not write WooCommerce.

If an order cannot be fully auto-allocated, its available quantity remains
reserved and its unresolved quantity is marked with an allocation exception
reason for Allocate. Allocation is FIFO for competing stock, not a global
block: an older shortage for one SKU does not prevent a newer order for a
different available SKU from allocating.

## Allocate Exceptions And Retry

The Allocate page mirrors the operational shortage workflow with Orders and
Items tabs. It reads `GET /api/allocations/exceptions`, defaults to unresolved
processing-order lines only, and shows ordered, allocated, unallocated, picked,
and available quantities. Staff can search by order, item, SKU, or barcode,
filter by ordered date and warehouse, optionally include 100% allocated lines,
and open an audited Update Stock Levels action. Filtering, summaries, and
stable pagination are evaluated in PostgreSQL. The CSV export uses the same
filters but includes every matching line, not only the visible page.
The Items tab returns bounded SQL aggregate rows rather than embedding every
affected order line for a SKU. `View affected orders` opens a separately paged
line drill-down for that exact item (or unmatched line), keeping all records
reachable without allowing a popular product to create an unbounded response.

`POST /api/allocations/auto/commit` reruns the same FIFO allocator manually. It
is safe to rerun: already allocated quantities are preserved and only remaining
eligible quantities are considered.

FIFO reconciliation also runs automatically after:

- manual, quick, or webhook order sync;
- direct, bulk, or scanner receiving;
- standard or scanner stock adjustments;
- standard or scanner cycle-count commits; and
- local completion or a WooCommerce status change that releases an unpicked
  reservation.

Preview endpoints remain read-only and do not trigger allocation.

## WooCommerce Status Changes

`processing` is operational. A `completed` order is also operational when its
payment method starts with `foosales`; this is the POS exception because
FooSales completes Woo orders at the till before Pongo's warehouse workflow.
Other pending, on-hold, cancelled, failed, refunded, completed, and
non-processing snapshots remain reporting history and cannot reserve stock.

When a previously allocated order is synchronized to a non-processing status,
Pongo OS releases its remaining unpicked allocation with deallocation audit
events, preserves any quantity already picked, and reruns FIFO allocation so
the released stock can move to the next eligible processing order. Release
follows the historical allocation location even when that location was later
made inactive; inactive locations remain excluded from new allocation and
picking.

Order updates also reconcile line quantities. Decreases release only unpicked
excess allocation. Lines removed in WooCommerce are retained locally as retired
history with ordered quantity zero. An unpicked product change releases the old
reservation before FIFO allocates the replacement item. If WooCommerce changes
a product or drops a quantity below what was already picked, fulfilled, or
stock-reduced, Pongo preserves the original item history and blocks further
picking with a reconciliation exception. Every decision is
written to the order workflow notes and affected releases create inventory
audit events. Each order is reconciled inside a database savepoint so a failed
line update cannot partially change that order.

## Picking

Picking is the stock reduction point.

The Pick Orders queue mirrors the established warehouse workflow. Its order
rows show order number, source, placed date, customer, city, state, shipping
method, total, SKUs, ordered quantity, allocated quantity, and picked quantity.
The leading arrow opens a focused order sheet with SKU, description, allocated
location, ordered, allocated, already-picked, and editable Picked fields. Staff
may enter any positive quantity up to the server-recommended remaining
allocated quantity or use Mark all allocated. There is no claim step and
barcode scanning is not required by this interface.

Both operational order tables include selectable bulk-action headers:

- Pick Orders: `Pick Selected` commits all remaining allocated quantities for
  selected pick-ready orders; `Unpick Selected` reverses all reversible picked
  quantities for selected orders.
- Open Orders: `Mark as completed`, `Print`, and `Unpick all` operate on the
  selected order rows. Print generates one consolidated local print sheet.

Unpick is local-only and cannot run on completed orders or order lines with
fulfilled quantities. It restores In Stock and Allocated at each original pick
location, reduces order-line picked and stock-reduced quantities, marks the
original pick lines reversed, and creates `unpick_stock_restoration` stock
movements and inventory audit events. Repeating an already reversed unpick is
rejected rather than restoring stock twice. Reversed pick lines are excluded
from remaining location-allocation calculations, so a restored order can be
picked again from its original allocation.

Fully picked orders leave the Pick Orders queue immediately. They remain in
Open Orders until completion, where `Unpick all` can restore them if a
correction is required. Partially picked orders remain in Pick Orders.

Manual pick commit and the retained scanner API:
- validate the line belongs to the selected order;
- validate the quantity does not exceed allocated remaining quantity;
- reduce `inventory_item_locations.in_stock`;
- reduce `inventory_item_locations.allocated`;
- recalculate item-location and aggregate `Sellable`;
- update `order_items.quantity_picked`;
- update `order_items.quantity_stock_reduced`;
- create `picks` and `pick_lines`;
- create `stock_movements` with `movement_type = pick_stock_reduction`;
- create inventory audit events;
- store stock reduction metadata on pick lines when possible.
- keep WooCommerce stock unchanged until the picked order is completed.

Manual, bulk, and scanner pick commits, plus bulk unpick, support a
request-level idempotency key. Replaying the same key and payload returns the
stored result instead of changing stock again; changing the payload returns
HTTP `409`.

Stock mutations share one PostgreSQL transaction gate and then lock affected
item aggregates and item-location rows in deterministic ID order. Pick and
unpick also lock the associated order rows. This prevents simultaneous
receiving, allocation reconciliation, picking, unpick, transfer, or adjustment
requests from calculating against the same stale quantities.

## Completion

Completion closes the local order workflow and sends an audited WooCommerce
order-status writeback to `completed`. The Open Orders action menu exposes one
`Complete order` command. The backend `completion_mode = complete` chooses the
safe local inventory implementation from current server state: fully picked
orders use picked completion; all other orders show a warning in the UI and
complete without reducing unpicked stock.

Completing a picked order:
- marks the order completed/closed locally;
- does not reduce stock again because picking already reduced stock;
- sends the current changed mapped item stock to WooCommerce through the
  audited writeback queue;
- releases any remaining unpicked allocation safely;
- creates a completion audit event.

Completing without picking:
- marks the order completed/closed locally;
- does not reduce stock;
- does not send a WooCommerce stock update;
- releases existing unpicked allocation safely;
- records that the order was completed without picking;
- creates an audit event stating that stock was not reduced.

After either completion path, the backend creates, approves, and sends an
`update_order_status` writeback queue item for the linked WooCommerce order.
Only picked completion also sends inventory stock; unpicked completion never
sends a stock change.
The response includes the queue ID and synchronization status. A failed or
dry-run write remains audited and is surfaced to staff for review; it never
causes a second local stock reduction.

## Legacy Fulfillment Compatibility

Fulfillment endpoints still exist for compatibility and history/reporting. They are no longer the normal stock reduction step.

If fulfillment is called after picking already reduced stock, it can create local fulfillment/completion records and returns a warning that stock was already reduced during picking. It does not double-reduce stock.

If fulfillment is called for an unpicked order, it rejects the request instead of silently using the old stock-decrement path.

## Safety Rules

- WooCommerce credentials stay encrypted in backend PostgreSQL storage; the
  encryption key remains in the backend environment.
- The separate webhook secret stays backend-only and is never exposed in API
  responses or frontend code.
- The frontend never calls WooCommerce directly.
- Completion may update only the linked WooCommerce order status to
  `completed`; it does not update WooCommerce stock or product data.
- Stock-changing local actions create stock movement or audit rows.
- Allocation cannot make allocated greater than in-stock.
- Picking cannot make in-stock or allocated negative.
- Completion never double-reduces stock.
- Routes, labels, outbound/customer notifications, purchase orders, suppliers,
  and auth/RBAC remain out of this workflow chunk. The internal staff
  new-order alert is local UI feedback only.
