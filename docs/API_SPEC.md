# Planned API Specification

This document describes planned backend endpoints. It is documentation only; no API routes are implemented yet.

## API Rules

- Frontend calls only the Pongo Inventory OS backend.
- Frontend never calls WooCommerce directly.
- WooCommerce credentials live only in backend environment variables.
- Stock-changing endpoints must create stock movement/audit rows.
- WooCommerce stock writeback is disabled until local workflows are stable and explicitly enabled.

## Health

### GET /health

Returns service health and basic build metadata.

## Items

### GET /api/items

List items with search, category, active/inactive, and include non-inventory filters.

### GET /api/items/{id}

Return one item, including location stock summary.

### POST /api/items

Create a manual local item. Future behavior may optionally push to WooCommerce, but not in MVP.

### PATCH /api/items/{id}

Update Pongo OS-owned item fields.

### GET /api/items/export

Export inventory item CSV.

### POST /api/items/sync/woocommerce

Trigger backend WooCommerce product and variation sync.

Returns:
- created_count
- updated_count
- skipped_count
- error_count
- errors

### POST /api/items/{id}/remap

Link or relink a local item to a WooCommerce product or variation.

Accepted identifiers:
- Woo Product ID
- Woo Variation ID
- SKU
- Barcode
- Product name

## Locations

### GET /api/locations

List warehouse/inventory locations.

### POST /api/locations

Create a location.

### PATCH /api/locations/{id}

Update a location.

### POST /api/locations/import

Import preset locations from CSV.

### GET /api/locations/export

Export locations CSV.

## Receiving

### POST /api/receipts

Create a direct receiving session with one or more receipt item rows. Increases location stock and creates stock movement rows.

### GET /api/receipts

List receipts.

### GET /api/receipts/{id}

Return receipt details and item rows.

### GET /api/reports/received-inventory

Export/report received inventory data.

## Cycle Count

### POST /api/cycle-counts

Submit a count for an item/location. Requires reason when the difference is not zero. Creates a stock movement row.

### GET /api/cycle-counts

List cycle count events.

## Orders

### POST /api/orders/sync/woocommerce

Sync eligible WooCommerce orders into the local database.

### GET /api/orders/open

List open orders eligible for allocation.

### GET /api/orders/allocated

List allocated orders ready for picking.

### POST /api/orders/{id}/allocate

Allocate sellable stock to an order. Records allocation and stock movement/audit rows.

### GET /api/orders/{id}/pick

Return order picking detail.

### POST /api/orders/{id}/pick-scan

Record a SKU/barcode scan for an allocated order item. Prevents overpicking.

### POST /api/orders/{id}/complete

Complete a picked order locally and update WooCommerce order status to completed through the backend WooCommerce REST client.

## Reports

### GET /api/reports/inventory

Inventory export.

### GET /api/reports/inventory-by-location

Inventory export grouped by item/location.

### GET /api/reports/fulfillment

Order fulfillment export.

### GET /api/reports/sku-orders

SKU/barcode order report with search by SKU, barcode, description, and date range.

## Routes

### GET /api/routes

List routes.

### POST /api/routes

Create route from selected orders.

### GET /api/routes/{id}

Return route with stops.

### POST /api/routes/{id}/optimize

Optimize stop sequence through a backend route provider abstraction.
