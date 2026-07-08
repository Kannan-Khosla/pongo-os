# WooCommerce Sync Plan

This document describes WooCommerce integration behavior. The current
implementation supports read-only product/variation sync and read-only open
order sync through the backend only.

## System Roles

- WooCommerce remains the storefront and customer-facing product/order system.
- Pongo Inventory OS is the operational inventory layer.
- Pongo Inventory OS syncs WooCommerce data into PostgreSQL.
- The React frontend reads from the Pongo backend/database only.
- The frontend must never call WooCommerce directly.

## Credentials

Required backend environment variables:
- `WOOCOMMERCE_BASE_URL`
- `WOOCOMMERCE_CONSUMER_KEY`
- `WOOCOMMERCE_CONSUMER_SECRET`
- `WOOCOMMERCE_TIMEOUT_SECONDS`
- `WOOCOMMERCE_PAGE_SIZE`
- `WOOCOMMERCE_ORDER_SYNC_PAGE_SIZE`
- `WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES`

Never commit real credentials. Example docs and tests must use placeholders only.

## Read-Only Sync First

The first WooCommerce integration phases are read-only product/variation sync
and read-only order sync. Do not update live WooCommerce stock or order statuses
until:
- product/variation mapping is stable;
- local item workflows are stable;
- stock movement auditing is verified;
- Pongo explicitly approves stock writeback behavior.

## Product Sync Behavior

Implemented endpoints:
- `GET /api/integrations/woocommerce/status`
- `POST /api/integrations/woocommerce/products/preview`
- `POST /api/integrations/woocommerce/products/commit`
- `GET /api/integrations/woocommerce/sync-runs`
- `GET /api/integrations/woocommerce/sync-runs/{id}`

Refresh/preview/commit are backend-only. The backend fetches:
- simple products;
- variable products;
- all variations for variable products.

Every simple product creates or updates one `inventory_items` row.

## Variation Sync Behavior

Every WooCommerce variation creates or updates one `inventory_items` row. Parent variable products are not sellable stock units unless WooCommerce exposes them as a simple sellable product.

Example:
- Dog Food Can 100g -> one item
- Dog Food Can 200g -> one item
- Dog Food Can 500g -> one item

## WooCommerce-Owned Fields

Expected to sync into the local database:
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
  when the local Barcode is currently blank.

Woo stock rule:
- WooCommerce stock quantity is stored only as `woo_stock_quantity_snapshot`.
- Local Pongo OS `In Stock` is not overwritten by WooCommerce product sync.

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
- `POST /api/integrations/woocommerce/orders/preview`
- `POST /api/integrations/woocommerce/orders/commit`
- `GET /api/orders/open`
- `GET /api/orders/{id}`
- `GET /api/orders/open/export`

Order sync pulls eligible WooCommerce orders into local `orders` and
`order_items` tables. The default open statuses are `processing` and `on-hold`,
configured through `WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES`.

Order sync is read-only against WooCommerce:
- no WooCommerce order status writes;
- no WooCommerce product or stock writes;
- no local item stock changes;
- no local allocation quantity changes;
- no stock movements;
- no receiving, cycle count, fulfillment, or route workflow side effects.

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
- Fetches eligible orders.
- Returns order and line actions, match statuses, availability snapshots, and
  warnings/errors.
- Does not write local orders or order lines.

Commit:
- Fetches eligible orders again.
- Creates or updates local order/order line snapshots only.
- Stores sync run history with `sync_type = orders`.
- Stores sync errors for unmatched, conflict, and skipped rows.
- Does not allocate, pick, reserve, route, fulfill, update item stock, or write
  WooCommerce.

## Allocation After Order Sync

Allocation is a local Pongo OS workflow after WooCommerce order sync. It uses
local `orders`, `order_items`, and `inventory_items` only.

Allocation:
- previews recommended reservation quantities without writing data;
- increases local item Allocated on commit;
- leaves local item In Stock unchanged;
- recalculates Sellable as In Stock minus Allocated;
- updates local order line `quantity_allocated`;
- creates local `allocations`, `allocation_lines`, and
  `inventory_audit_events` rows;
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not pick, route, fulfill, create shipping labels, or notify customers.

Order sync should preserve existing local allocation quantities when refreshing
the local order snapshot.

## Picking After Allocation

Picking is a local Pongo OS workflow after allocation. It uses local `orders`,
`order_items`, `inventory_items`, `picks`, `pick_lines`, and
`inventory_audit_events` only.

Picking:
- previews recommended pick quantities from already allocated order lines;
- rejects unallocated, unmatched, conflict, unknown item, overpicked, and fully
  picked lines;
- updates local order line `quantity_picked` and legacy `picked_qty` on commit;
- leaves local item In Stock unchanged;
- leaves local item Allocated unchanged;
- leaves local item Sellable unchanged;
- creates local `picks`, `pick_lines`, and `inventory_audit_events` rows;
- records pick audit events with unchanged previous/new stock, allocated, and
  sellable values;
- does not call WooCommerce;
- does not update WooCommerce order status, products, or stock;
- does not route, fulfill, create shipping labels, or notify customers.

Order sync should preserve existing local picked quantities when refreshing the
local order snapshot.

## Fulfillment After Picking

Fulfillment is a local Pongo OS workflow after picking. It uses local `orders`,
`order_items`, `inventory_items`, `fulfillments`, `fulfillment_lines`,
`stock_movements`, and `inventory_audit_events` only.

Fulfillment:
- previews recommended fulfillment quantities from already picked order lines;
- rejects unpicked, unmatched, conflict, unknown item, overfulfilled, and fully
  fulfilled lines;
- updates local order line `quantity_fulfilled` and legacy `fulfilled_qty` on
  commit;
- reduces local item In Stock by the fulfilled quantity;
- reduces local item Allocated by the fulfilled quantity;
- recalculates local item Sellable and Under Par;
- creates local `fulfillments`, `fulfillment_lines`, `stock_movements`, and
  `inventory_audit_events` rows;
- creates stock movements with `movement_type = fulfill_order`;
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
  notifications;
- does not change local item In Stock, Allocated, Sellable, On Order, stock
  movements, inventory audit events, order item quantities, or order status.

## Stock Update Safety

Stock-changing local actions must always create stock movement rows. WooCommerce stock updates should remain disabled or queued until read-only sync and local workflows are stable. When enabled, stock writeback must happen through the backend only and should include retry/error logging.

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

## Current Chunk Safety Boundary

The Items Control Center, bulk receiving, scanner workflows, and expanded
reports do not add WooCommerce writeback.

Current behavior:
- Frontend still never calls WooCommerce directly.
- WooCommerce credentials remain backend environment variables only.
- Bulk receiving and scanner receiving update local `inventory_item_locations`
  and create local stock movements only.
- Cycle count, transfer, and adjustment scanner commits are local stock
  workflows only.
- Expanded reports read local tables only.
- Local remap search in Items is candidate search only; actual remap remains
  local metadata and does not call WooCommerce.

Future writeback remains intentionally delayed until read-only sync, local
workflows, audit trails, and operator review rules are stable.
