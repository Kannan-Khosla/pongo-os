# Business Dashboard

The `Dashboard` page is now the default home page for Pongo Inventory OS. It is
the business/customer/order dashboard, while `Inventory Overview` is the renamed
operational command center.

## Pages

- `Dashboard`: business snapshot for orders, revenue, customers,
  subscriptions, and geography.
- `Inventory Overview`: operational inventory health, work queues, exceptions,
  recent activity, and quick actions.

## Backend Endpoints

Read-only endpoints:

- `GET /api/business-dashboard`
- `GET /api/business-dashboard/today`
- `GET /api/business-dashboard/open-orders`
- `GET /api/business-dashboard/woocommerce-open-orders`
- `GET /api/business-dashboard/subscriptions`
- `GET /api/business-dashboard/revenue-comparison`
- `GET /api/business-dashboard/order-map`

The combined endpoint returns all sections needed for the initial Dashboard
page load. PostgreSQL calculates counts, revenue, units, customer cohorts, and
daily comparisons with aggregate queries; the API no longer loads the complete
order and line history into application memory. The map query is limited to the
selected business day, and the open-order card returns at most the 200 newest
rows while its displayed total remains the exact full open-order count.
Subscription processing reads the latest complete local active-subscription
snapshot. Results are versioned in
PostgreSQL and reused until an order, stock, allocation, receipt, pick,
fulfillment, or movement changes the source version.
When the source changes, an existing verified snapshot is returned immediately
while the worker refreshes it. The combined endpoint and all detailed sections
remain local-only. The separate `woocommerce-open-orders` endpoint performs
one backend-only, paged WooCommerce read for `processing` (up to 100 rows) and
returns sanitized order rows plus authoritative `X-WP-Total` and
`X-WP-TotalPages` values. It joins nullable existing local order IDs without
creating snapshots. Its failure is isolated from the rest of the Dashboard and
never falls back to a local count.

## Metric Definitions

Today's orders are local order snapshots whose placed or created date matches
the selected date.

Today's revenue uses local order totals when available, otherwise line totals.

New customers today are customer identities whose first known local order date
is today. Returning customers today are customer identities with an order today
and at least one earlier local order. Email is the preferred identity.

Revenue comparison defaults to month-to-date versus the same day range in the
previous month, for example July 1-8 versus June 1-8.

Open orders are local order snapshots with open-style statuses such as
`open`, `processing`, `on-hold`, `pending`, `allocated`, or picking states.
Completed, failed, cancelled, and refunded statuses are excluded.

The first KPI, `Open Orders`, is deliberately separate. It is the live
WooCommerce total and sanitized list for `processing` orders only, with its own
loading and unavailable states. More than 100 orders are disclosed through
`total_pages`; callers can request subsequent pages. Demo accounts receive an
isolated mock list/count derived from the same mock rows and never construct a
WooCommerce client.

## Subscriptions

The worker refreshes active subscriptions from the read-only WooCommerce
Subscriptions REST endpoint every 15 minutes. Each line stores Woo product and
variation identity, SKU, quantity, and Woo's official next-payment date; a
failed or partial fetch leaves the last complete snapshot intact.

The Dashboard shows renewals due in the next 30 days with current Pongo
`In Stock` and `Sellable` quantities. A product is `At risk` when units due in
the next 30 days exceed current sellable stock. Unmapped or unavailable stock
is reported as unknown, never zero. If no successful snapshot exists, the
section remains empty with a data-quality warning.

## Geography And Map Behavior

The Dashboard groups today's orders by local shipping or billing city. Exact
coordinates are used only if already stored locally. Without exact coordinates,
known nearby cities use city-level approximate coordinates and markers are
flagged with `approximate=true`.

Supported approximate cities:

- Edmonton
- Sherwood Park
- Leduc
- St. Albert
- Beaumont
- Spruce Grove
- Fort Saskatchewan

Unknown cities remain unplotted and are counted in the map summary.

## Safety

The Business Dashboard uses local snapshots for every section except the
explicit live WooCommerce open-order KPI:

- no WooCommerce writes
- no direct WordPress/MySQL connection
- no frontend WooCommerce calls
- no local fallback when the live WooCommerce count is unavailable
- no live geocoding provider calls
- no committed map/geocode credentials
- no inventory mutations
- no order mutations
- no customer notifications
- no fake data

The live Dashboard GET remains read-only. Opening a remote-only row is an
explicit `POST /api/orders/woocommerce/{woo_order_id}/reconcile`; changing a
status is a separate reasoned and idempotent status-action POST documented in
`API_SPEC.md` and `ORDER_WORKFLOW.md`.
