# WooCommerce Sync Plan

This document describes WooCommerce integration behavior. The current
implementation supports a read-only product and variation sync foundation
through the backend only.

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

Never commit real credentials. Example docs and tests must use placeholders only.

## Read-Only Sync First

The first WooCommerce integration phase is read-only product and variation sync. Do not update live WooCommerce stock until:
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

Order sync pulls eligible WooCommerce orders into local `orders` and `order_items` tables. Eligibility depends on confirmed WooCommerce statuses. Order items are matched to inventory items by Woo product ID, Woo variation ID, SKU, or barcode.

## Stock Update Safety

Stock-changing local actions must always create stock movement rows. WooCommerce stock updates should remain disabled or queued until read-only sync and local workflows are stable. When enabled, stock writeback must happen through the backend only and should include retry/error logging.
