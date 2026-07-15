# Pongo Insights

Pongo Insights is the read-only business intelligence page for Pongo Inventory
OS. It is separate from the operational Command Center dashboard and reads local
Pongo OS data only.

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

Insights uses local tables:

- `orders`
- `order_items`
- `inventory_items`
- local WooCommerce order snapshot fields already stored on orders and lines

The frontend never calls WooCommerce. The Insights backend does not call
WooCommerce and does not write WooCommerce products, orders, statuses, or stock.
When staging WooCommerce sync is configured, Insights reads the local staging
product/order/customer/address snapshots after sync commit. It still does not
call WooCommerce directly.

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

## Data Quality Warnings

Endpoints return `data_quality` warnings instead of crashing when source data is
missing. Current warnings include `limited_order_history`,
`missing_customer_email`, `missing_unit_cost`, `missing_refund_data`,
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
