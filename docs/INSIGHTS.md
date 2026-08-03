# Pongo Insights

Pongo Insights is the read-only business intelligence page for Pongo Inventory
OS. It is separate from the operational Command Center dashboard.

## Dashboards

The Insights sidebar page renders these tabbed dashboards:

- Executive Overview
- Orders & Revenue
- Customer Metrics
- Customer Segmentation
- Product & SKU Metrics
- Subscriptions
- Subscription Products
- Inventory Forecasting
- Coupons & Promotions
- Payment Health
- Geography & Delivery
- Product Affinity
- Reorder Forecast

Each tab loads its own `/api/insights/*` endpoint on demand. The frontend does
not load all dashboards on first render.

## Data Sources

Insights uses local tables for customer, product, inventory, payment, geography,
forecasting, and drill-down detail:

- `orders`
- `order_items`
- `inventory_items`
- local WooCommerce order snapshot fields already stored on orders and lines

For unfiltered Executive Overview and Orders & Revenue date ranges, the backend
reads WooCommerce Analytics revenue statistics so order count, gross/net sales,
returns, coupons, tax, shipping, units, AOV, and time-series totals match the
WooCommerce Analytics screen. Filtered product/customer views continue to use
local order snapshots because WooCommerce's aggregate endpoint cannot apply
Pongo-owned inventory dimensions. The frontend never receives credentials or
calls WooCommerce directly, and Insights never writes WooCommerce or local data.

## Metrics

Implemented first-pass metrics include:

- revenue, gross sales, net sales, AOV, discounts, shipping, tax, units sold
- daily revenue and order trends
- customer counts, repeat rate, lifetime value, dormancy, and reorder candidates
- RFM-style customer segments
- SKU units, revenue, estimated cost, estimated margin, current stock, and demand
- deterministic inventory forecast from recent local order demand
- coupon performance when local coupon lines exist in stored Woo payloads
- payment method success/failure grouping and duplicate failed-to-success pattern detection
- geography by shipping/billing city and postal code
- product affinity from orders with two or more SKUs

Forecasting is deterministic only. No ML model is used.

Orders without a customer email are still included in every order, revenue,
unit, product, and customer total. Customer identity falls back from a nonzero
Woo customer ID to phone/name/postal details and finally the local order ID, so
anonymous POS orders are not collapsed into one customer or discarded.

The UI defaults to the last completed calendar month and provides instant last
month, two-month, three-month, year, comparison, sales-per-day, and
sales-per-week presets. Custom start and end dates remain available.

## Data Quality Warnings

Endpoints return `data_quality` warnings instead of crashing when source data is
missing. Current warnings include `limited_order_history`,
`missing_unit_cost`, `missing_refund_data`, `woo_analytics_unavailable`,
`missing_coupon_data`, `missing_subscription_data`, and
`missing_shipping_postal_code`.

Subscriptions and subscription products return clean empty states until local
WooCommerce Subscriptions snapshots are added.

Coupon, payment, shipping, address, customer, and refund fields are used only
when present in synced local WooCommerce payloads. Missing fields produce data
quality warnings instead of fabricated metrics.

## CSV Exports

CSV export endpoints are implemented for:

- `/api/insights/orders-revenue/export`
- `/api/insights/customer-metrics/export`
- `/api/insights/product-sku/export`
- `/api/insights/reorder-forecast/export`
- `/api/insights/geography/export`

Tabs without export support do not render fake export buttons.

## Safety

Insights is read-only:

- no WooCommerce writes
- no WooCommerce frontend calls
- no credentials in API responses
- no customer notifications
- no local stock mutations
- no order status updates
- no stock movements are created by Insights
