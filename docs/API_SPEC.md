# Planned API Specification

This document describes planned backend endpoints. The backend now implements
`/health`, backend-persistent Items CRUD/export/import, backend-persistent
Locations CRUD/export/import, inventory by-location reporting/export, direct
receiving without PO, and the read-only Received Inventory Report. Other workflow routers remain structural
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
- `woo_sync_status`
- `woo_product_id`
- `woo_variation_id`

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

Replaced by the read-only WooCommerce integration endpoints under
`/api/integrations/woocommerce`.

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

## WooCommerce Integration

All WooCommerce integration endpoints are backend-only. The React frontend calls
the Pongo backend and never calls WooCommerce directly. Credentials are read
only from backend environment variables and are never returned in API responses.

Required backend environment variables:
- `WOOCOMMERCE_BASE_URL`
- `WOOCOMMERCE_CONSUMER_KEY`
- `WOOCOMMERCE_CONSUMER_SECRET`
- `WOOCOMMERCE_TIMEOUT_SECONDS`
- `WOOCOMMERCE_PAGE_SIZE`
- `WOOCOMMERCE_ORDER_SYNC_PAGE_SIZE`
- `WOOCOMMERCE_ORDER_SYNC_DEFAULT_STATUSES`

### GET /api/integrations/woocommerce/status

Return safe configuration status.

Response:
- `configured`
- `base_url_present`
- `consumer_key_present`
- `consumer_secret_present`
- `message`

No secret values are returned.

Optional query param:
- `check=true`: performs a safe read-only product request to verify
  connectivity when credentials are configured.

### POST /api/integrations/woocommerce/products/preview

Fetch WooCommerce products and variations through the backend WooCommerce REST
API client and return what would happen locally without database writes.

Request:
- `include_statuses`: defaults to `["publish"]`
- `limit`: defaults to `500`
- `created_by`: defaults to `system`

Preview does not:
- create or update local items
- create stock movements
- write to WooCommerce

Response:
- `configured`
- `total_remote_records`
- `create_count`
- `update_count`
- `matched_count`
- `skipped_count`
- `conflict_count`
- `error_count`
- `warnings`
- `errors`
- `preview_rows`

Preview row fields:
- `remote_type`
- `woo_product_id`
- `woo_variation_id`
- `sku`
- `barcode`
- `description`
- `category`
- `brand`
- `price`
- `regular_price`
- `stock_status`
- `stock_quantity_snapshot`
- `local_item_id`
- `action`
- `status`
- `warnings`
- `errors`

Action values:
- `create`
- `update`
- `match_only`
- `skip`
- `conflict`
- `error`

### POST /api/integrations/woocommerce/products/commit

Fetch products/variations again, validate again, and create/update only local
Pongo OS items. This endpoint never writes to WooCommerce.

Commit behavior:
- Creates one local item for each sellable simple product with a SKU.
- Creates one local item for each sellable variation with a SKU.
- Updates existing items by Woo product/variation IDs, SKU, or Barcode.
- Skips blank-SKU records.
- Skips conflicts.
- Stores sync run history and sync errors.
- Does not create stock movements.
- Does not overwrite local In Stock, Allocated, Warehouse, Inventory Location,
  Default Location, Unit Cost, Par Level, reorder fields, or other manual
  operational fields.
- Stores Woo stock only in `woo_stock_quantity_snapshot`.

### GET /api/integrations/woocommerce/sync-runs

List WooCommerce sync runs.

Filters:
- `sync_type`
- `status`
- `date_from`
- `date_to`

### GET /api/integrations/woocommerce/sync-runs/{id}

Return sync run detail and row-level sync errors.

### POST /api/integrations/woocommerce/orders/preview

Fetch eligible WooCommerce orders through the backend WooCommerce REST API
client and return what would happen locally without database writes.

Request:
- `include_statuses`: defaults to `["processing", "on-hold"]`
- `limit`: defaults to `500`
- `after`, `before`, `modified_after`, `modified_before`: optional WooCommerce date filters
- `created_by`: defaults to `system`

Preview does not:
- create or update local orders
- allocate, reserve, pick, or route order lines
- change item In Stock or Allocated quantities
- create stock movements
- write to WooCommerce

Matching rules for order lines:
- Woo Product ID + Woo Variation ID
- exact SKU
- exact Barcode from order line metadata
- conflict when those identifiers match different local items

Availability is a read-only snapshot:
- `sellable_snapshot = item.In Stock - item.Allocated`
- `available` when sellable covers ordered quantity
- `partial` when some sellable quantity exists but not enough
- `unavailable` when a matched item has no sellable quantity
- `unknown` for unmatched or conflict lines

### POST /api/integrations/woocommerce/orders/commit

Fetch eligible WooCommerce orders again, validate again, and create/update only
local `orders` and `order_items` rows. This endpoint never writes to
WooCommerce and never changes local stock or allocation quantities.

Commit behavior:
- Stores a local order snapshot for eligible open WooCommerce orders.
- Upserts order lines by Woo line item ID.
- Stores unmatched and conflict lines for staff review instead of creating
  inventory items.
- Reuses `woocommerce_sync_runs` with `sync_type = orders`.
- Stores order/line context in `woocommerce_sync_errors` for unmatched and
  conflict rows.

### GET /api/orders/open

List local open orders imported from WooCommerce order sync.

Filters:
- `search`
- `woo_status`
- `availability_status`
- `matched_status`

### GET /api/orders/{id}

Return one local order with line-level match and availability detail.

### GET /api/orders/open/export

Export filtered local open orders as CSV.

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

## Inventory

### GET /api/inventory/export/by-location

Export inventory by warehouse/location as CSV.

Implemented. Uses current item text fields for `Warehouse`,
`Inventory Location`, and `Default Location`; item-location foreign keys are
not globally enforced yet.

Supported query params:
- `warehouse`
- `inventory_location`
- `default_location`
- `category`
- `brand`
- `under_par`
- `non_inventory`

CSV columns are documented in `docs/CSV_COLUMNS.md`.

Calculated fields are recomputed at export time:
- `Sellable = In Stock - Allocated`
- `Under Par = In Stock <= Par Level`
- `Storage Volume = Storage Length * Storage Width * Storage Height`
- `Inventory Value = In Stock * Unit Cost`

### GET /api/inventory/summary/by-location

Return inventory totals grouped by warehouse and inventory location.

Implemented. Supports the same filters as the by-location CSV export.

Each group includes:
- `warehouse`
- `inventory_location`
- `item_count`
- `total_in_stock`
- `total_allocated`
- `total_sellable`
- `total_on_order`
- `total_inventory_value`
- `under_par_count`

## Receiving

### POST /api/receipts/direct/preview

Validate a direct receiving payload without database writes.

Implemented. Preview does not update item stock, create receipts, create
receipt lines, or create stock movements.

Validation rules:
- Receipt warehouse is required.
- Each line must match an existing item by `item_id`, exact SKU, or exact Barcode.
- If SKU and Barcode match different items, the line is invalid.
- Unknown items are rejected; receiving does not auto-create items.
- Each line requires an active location matching warehouse + Location Code or
  warehouse + Location Name.
- Quantity Received must be greater than zero.

### POST /api/receipts/direct/commit

Commit direct receiving without PO.

Implemented. The commit is atomic: if any line is invalid, the full receipt is
rejected and no stock is updated.

On success:
- Creates a `receipts` row with `receipt_type = direct` and `status = posted`.
- Creates receipt line rows.
- Increases item `In Stock`.
- Leaves `Allocated` unchanged.
- Recalculates item Sellable, Under Par, and Storage Volume.
- Creates one stock movement/audit row per received line.

Intentional exclusions:
- No purchase orders.
- No supplier management.
- No WooCommerce calls.
- No cycle count, allocation, picking, route, or fulfillment workflow.
- No weighted average cost update.

### POST /api/receipts

Create a direct receiving session with one or more receipt item rows. Increases location stock and creates stock movement rows.

### GET /api/receipts

List receipts.

### GET /api/receipts/{id}

Return receipt details and item rows.

### GET /api/stock-movements

List stock movement audit rows.

Implemented filters:
- `item_id`
- `sku`
- `barcode`
- `warehouse`
- `inventory_location`
- `movement_type`
- `reference_type`
- `reference_id`
- `date_from`
- `date_to`

## Cycle Count

Cycle Count is implemented as the second stock-changing workflow after Direct
Receiving. It does not call WooCommerce and does not run allocation, picking,
route, fulfillment, purchase order, or supplier workflows.

### POST /api/cycle-counts/preview

Validate a cycle count payload and calculate variances without writing stock
changes.

Implemented behavior:
- Does not update item stock.
- Does not create cycle count rows.
- Does not create stock movements.
- Matches items by `item_id`, exact SKU, or exact Barcode.
- Rejects a line when SKU and Barcode match different existing items.
- Rejects unknown items.
- Requires warehouse.
- Requires an active location when `inventory_location` is provided.
- Requires `inventory_location` for `count_type = full_location`.
- Requires `counted_quantity >= 0`.

Response fields:
- `total_lines`
- `valid_lines`
- `invalid_lines`
- `adjustment_lines`
- `total_positive_variance`
- `total_negative_variance`
- `total_absolute_variance`
- `total_variance_value`
- `errors`
- `warnings`
- `preview_lines`

Preview line fields:
- `line_number`
- `item_id`
- `sku`
- `barcode`
- `description`
- `warehouse`
- `inventory_location`
- `system_quantity`
- `counted_quantity`
- `variance_quantity`
- `unit_cost`
- `variance_value`
- `status`
- `warnings`
- `errors`

### POST /api/cycle-counts/commit

Validate and post a cycle count atomically.

Implemented behavior:
- Rejects the full count if any line is invalid.
- Creates a `cycle_counts` header row with `status = posted`.
- Creates one `cycle_count_lines` row per valid line.
- Updates item `In Stock` to `counted_quantity` only when variance is non-zero.
- Leaves `Allocated` unchanged.
- Recalculates Sellable, Under Par, and Storage Volume.
- Creates stock movement rows only for variance lines.

Stock movement audit fields:
- `movement_type = cycle_count_adjustment`
- `quantity_delta = counted_quantity - system_quantity`
- `previous_in_stock = system_quantity`
- `new_in_stock = counted_quantity`
- `reference_type = cycle_count`
- `reference_id = cycle_count id`
- `reference_number = count_number`

Calculation rules:
- `system_quantity` is captured from current item `In Stock`.
- `variance_quantity = counted_quantity - system_quantity`.
- `variance_value = variance_quantity * unit_cost`.
- Null or blank unit cost is treated as zero.

### GET /api/cycle-counts

List cycle count events.

Implemented filters:
- `status`
- `warehouse`
- `inventory_location`
- `count_type`
- `date_from`
- `date_to`
- `created_by`

### GET /api/cycle-counts/{id}

Return cycle count detail with lines.

### GET /api/cycle-counts/{id}/export

Export one cycle count as CSV.

CSV header order:
- Count Number
- Status
- Created At
- Posted At
- Warehouse
- Inventory Location
- SKU
- Barcode
- Description
- System Quantity
- Counted Quantity
- Variance Quantity
- Unit Cost
- Variance Value
- Notes

### POST /api/cycle-counts/{id}/cancel

Not implemented. The current MVP posts counts immediately and does not persist
draft counts.

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

### GET /api/reports/received-inventory

Return read-only received inventory report rows derived from receipt lines and
receipt headers.

Implemented filters:
- `date_from`
- `date_to`
- `warehouse`
- `inventory_location`
- `sku`
- `barcode`
- `category`
- `brand`
- `receipt_number`
- `reference_number`
- `created_by`

Date filters use receipt `received_at` and fall back to receipt `created_at`
when `received_at` is missing. `date_from` is inclusive on or after that date;
`date_to` is inclusive on or before that date.

Each row includes:
- `receipt_id`
- `receipt_number`
- `receipt_type`
- `status`
- `received_at`
- `created_at`
- `warehouse`
- `inventory_location`
- `default_location`
- `sku`
- `barcode`
- `description`
- `category`
- `brand`
- `quantity_received`
- `unit_cost`
- `total_received_value`
- `reference_number`
- `created_by`
- `line_notes`
- `receipt_notes`

Calculation:
- `total_received_value = quantity_received * unit_cost`
- Blank or null unit cost is treated as zero.

Data source rules:
- Receipt lines are the operational source of truth for received rows.
- Receipt headers supply receipt number, type, status, received date, reference
  number, created by, and notes.
- Item rows enrich category, brand, barcode, and description when a receipt
  line does not already store the value.
- Stock movements remain audit trail data and are not the primary report source.

Current limitation: this report is based on direct receiving records only
because purchase order receiving is not built.

### GET /api/reports/received-inventory/summary

Return totals and grouped summaries for the same filters as
`GET /api/reports/received-inventory`.

Response fields:
- `total_receipts`
- `total_lines`
- `total_quantity_received`
- `total_received_value`
- `unique_skus`
- `unique_locations`
- `date_from`
- `date_to`
- `by_warehouse`
- `by_location`
- `by_sku`

Grouped summary fields:
- `by_warehouse`: warehouse, total lines, total quantity received, total received value.
- `by_location`: warehouse, inventory location, total lines, total quantity received, total received value.
- `by_sku`: SKU, barcode, description, brand, category, total quantity received, total received value, receipt count.

### GET /api/reports/received-inventory/export

Export the received inventory report as CSV using the same filters as the JSON
report.

CSV header order:
- Receipt Number
- Receipt Type
- Status
- Received At
- Warehouse
- Inventory Location
- Default Location
- SKU
- Barcode
- Description
- Category
- Brand
- Quantity Received
- Unit Cost
- Total Received Value
- Reference Number
- Created By
- Line Notes
- Receipt Notes

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
