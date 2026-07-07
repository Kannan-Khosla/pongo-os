# WooCommerce Sync Plan

This document describes planned WooCommerce integration behavior. No WooCommerce connection is attempted in this task.

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

Never commit real credentials. Example docs and tests must use placeholders only.

## Read-Only Sync First

The first WooCommerce integration phase is read-only product and variation sync. Do not update live WooCommerce stock until:
- product/variation mapping is stable;
- local item workflows are stable;
- stock movement auditing is verified;
- Pongo explicitly approves stock writeback behavior.

## Product Sync Behavior

Refresh should trigger backend sync. The backend fetches:
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

## Pongo OS-Owned Fields

These fields must not be overwritten by refresh:
- Barcode
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

## Refresh Summary

Refresh should return:
- created_count
- updated_count
- skipped_count
- error_count
- errors

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
