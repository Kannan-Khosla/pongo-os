# Planned API Specification

This document describes planned backend endpoints. The backend now implements
`/health`, backend-persistent Items CRUD/export/import, and backend-persistent
Locations CRUD/export/import. Other workflow routers remain structural
placeholders until their modules are built.

## API Rules

- Frontend calls only the Pongo Inventory OS backend.
- Frontend never calls WooCommerce directly.
- WooCommerce credentials live only in backend environment variables.
- Stock-changing endpoints must create stock movement/audit rows.
- WooCommerce stock writeback is disabled until local workflows are stable and explicitly enabled.

## Health

### GET /health

Returns service health and basic build metadata.

Current response:

```json
{
  "status": "ok",
  "service": "pongo-inventory-os"
}
```

## Current Placeholder Routers

These routes are wired for frontend/API structure only. They do not perform
business workflows, external calls, or database mutations yet.

- `GET /api/receipts`
- `GET /api/orders`
- `GET /api/reports`
- `GET /api/routes`

## Items

### GET /api/items

List items with search, category, active/inactive, and include non-inventory filters.

Implemented query params:
- `search`
- `category`
- `warehouse`
- `inventory_location`
- `brand`
- `active`
- `include_non_inventory`

Returns canonical CSV-style field names plus internal display fields such as
`id`, `active`, `nonInventory`, `imageUrl`, `wooProductId`, and
`wooVariationId`.

### GET /api/items/{id}

Return one item, including location stock summary.

### POST /api/items

Create a manual local item. Future behavior may optionally push to WooCommerce, but not in MVP.

Implemented for local Pongo Inventory OS persistence only. SKU is required.
Calculated fields are recomputed before save:
- `Sellable = In Stock - Allocated`
- `Under Par = In Stock <= Par Level`
- `Storage Volume = Storage Length * Storage Width * Storage Height`

### PATCH /api/items/{id}

Update Pongo OS-owned item fields.

Implemented for local Pongo Inventory OS persistence only. Calculated fields are
recomputed before save.

### GET /api/items/export

Export inventory item CSV.

Implemented. Exports filtered rows using the exact canonical inventory CSV
header order from `docs/CSV_COLUMNS.md`. Internal fields are not included.

### POST /api/items/import/preview

Preview a Zenventory-compatible item CSV import.

Implemented. Accepts `multipart/form-data` with a `file` upload. This endpoint
parses and validates the CSV but does not write to the database.

Header rules:
- Canonical column names from `docs/CSV_COLUMNS.md` are required.
- Header whitespace is trimmed.
- Column names are case-sensitive.
- Missing canonical columns reject the file.
- Extra columns are ignored and returned as warnings.

Matching rules:
- SKU exact match is checked first.
- Barcode exact match is checked second when Barcode is present.
- If SKU and Barcode match two different existing items, the row is invalid.

Calculated fields are recomputed during preview:
- `Sellable = In Stock - Allocated`
- `Under Par = In Stock <= Par Level`
- `Storage Volume = Storage Length * Storage Width * Storage Height`

Returns:
- `total_rows`
- `valid_rows`
- `invalid_rows`
- `create_count`
- `update_count`
- `skipped_count`
- `warnings`
- `errors`
- `preview_rows`

### POST /api/items/import/commit

Commit a Zenventory-compatible item CSV import.

Implemented. Accepts the same `multipart/form-data` `file` upload as preview.
The backend revalidates and reparses the file before writing. Valid rows create
or update local Pongo Inventory OS items only. The endpoint does not call
WooCommerce and does not run receiving, cycle count, allocation, picking, or
other stock-changing workflows.

The commit writes an `import_jobs` record plus `import_errors` rows for failed
CSV rows.

Returns:
- `import_job_id`
- `total_rows`
- `created_count`
- `updated_count`
- `skipped_count`
- `failed_count`
- `errors`

### POST /api/items/sync/woocommerce

Trigger backend WooCommerce product and variation sync.

Not implemented yet.

Returns:
- created_count
- updated_count
- skipped_count
- error_count
- errors

### POST /api/items/{id}/remap

Link or relink a local item to a WooCommerce product or variation.

Not implemented yet.

Accepted identifiers:
- Woo Product ID
- Woo Variation ID
- SKU
- Barcode
- Product name

## Import Jobs

### GET /api/import-jobs

List CSV import jobs, newest first.

Implemented for item and location CSV imports.

### GET /api/import-jobs/{id}

Return one import job with row-level errors.

Implemented for item and location CSV imports.

### GET /api/import-jobs/{id}/failed-rows

Download failed rows as CSV.

Implemented. The CSV uses the canonical columns for the import type plus an
`Error Message` column. This is intended for correcting failed import rows and
retrying the import.

## Locations

### GET /api/locations

List warehouse/inventory locations.

Implemented query params:
- `search`
- `warehouse`
- `code`
- `name`
- `zone`
- `aisle`
- `active`

Search covers warehouse, code, name, description, zone, and aisle.

### GET /api/locations/{id}

Return one location.

### POST /api/locations

Create a location.

Implemented for local Pongo Inventory OS persistence only. Required fields:
- `warehouse`
- `code`
- `name`

If a location is marked default, the backend clears other defaults in the same
warehouse.

### PATCH /api/locations/{id}

Update a location.

Implemented for local Pongo Inventory OS persistence only.

### DELETE /api/locations/{id}

Soft delete/deactivate a location by setting `isActive` to false.

### GET /api/locations/export

Export locations CSV.

Implemented. Exports filtered rows using the canonical location CSV header from
`docs/CSV_COLUMNS.md`.

### POST /api/locations/import/preview

Preview a location CSV import.

Implemented. Accepts `multipart/form-data` with a `file` upload. This endpoint
parses and validates the CSV but does not write to the database.

Header rules:
- Canonical location columns from `docs/CSV_COLUMNS.md` are required.
- Header whitespace is trimmed.
- Column names are case-sensitive.
- Missing canonical columns reject the file.
- Extra columns are ignored and returned as warnings.

Matching rules:
- Existing locations match by exact Warehouse + Location Code.
- Missing matches create new locations.

Returns:
- `total_rows`
- `valid_rows`
- `invalid_rows`
- `create_count`
- `update_count`
- `skipped_count`
- `warnings`
- `errors`
- `preview_rows`

### POST /api/locations/import/commit

Commit a location CSV import.

Implemented. Valid rows create or update local location records only. The
endpoint does not change item stock, create stock movements, or run receiving,
cycle count, allocation, picking, route, or WooCommerce workflows.

The commit writes an `import_jobs` record with `import_type = locations` plus
`import_errors` rows for failed CSV rows.

Returns:
- `import_job_id`
- `total_rows`
- `created_count`
- `updated_count`
- `skipped_count`
- `failed_count`
- `warnings`
- `errors`

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
