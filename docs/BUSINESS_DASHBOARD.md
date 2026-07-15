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
- `GET /api/business-dashboard/subscriptions`
- `GET /api/business-dashboard/revenue-comparison`
- `GET /api/business-dashboard/order-map`

The combined endpoint returns all sections needed for the initial Dashboard
page load.

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

## Subscriptions

If local subscription snapshots are not available, the Dashboard returns an
empty subscription section and a data quality warning. It does not fake
subscription products, renewal dates, or subscription counts.

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

The Business Dashboard uses local snapshots only:

- no WooCommerce writes
- no frontend WooCommerce calls
- no live geocoding provider calls
- no committed map/geocode credentials
- no inventory mutations
- no order mutations
- no customer notifications
- no fake data
