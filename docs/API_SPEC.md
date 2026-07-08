# API Specification

This document describes the current Pongo Inventory OS backend API plus planned
future boundaries. The backend implements health, Command Center dashboard,
Items, item import/export, Locations, inventory by-location reporting/export,
Stock by Location v2, inventory transfers, stock adjustments, direct receiving,
received inventory reporting, cycle counts, read-only
WooCommerce product and order sync, local WooCommerce remap metadata, open
orders, allocations, scanner-style picks, fulfillments, completed orders, SKU
Orders reporting, and local-only route creation/management.

## API Rules

- Frontend calls only the Pongo Inventory OS backend.
- Frontend never calls WooCommerce directly.
- WooCommerce credentials live only in backend environment variables.
- Stock-changing endpoints must create stock movement/audit rows.
- WooCommerce stock writeback is disabled until local workflows are stable and explicitly enabled.
- Route map/geocoding/optimization providers are disabled unless configured
  backend-side. Provider endpoints must never expose secrets.

## Current API Groups

- `GET /health`
- Dashboard: `/api/dashboard`, `/api/dashboard/summary`, `/api/dashboard/activity`, `/api/dashboard/warnings`
- Items and item CSV import/export: `/api/items`, `/api/items/import/*`
- Import jobs: `/api/import-jobs`
- Locations and location CSV import/export: `/api/locations`
- Inventory reports/exports: `/api/inventory`
- Location inventory: `/api/inventory/locations`, `/api/inventory/locations/export`
- Inventory transfers: `/api/inventory/transfers`
- Stock adjustments: `/api/inventory/adjustments`
- Receipts/direct receiving: `/api/receipts`
- Reports: `/api/reports/received-inventory`, `/api/reports/fulfillments`, `/api/reports/sku-orders`
- Cycle counts: `/api/cycle-counts`
- WooCommerce read-only product sync: `/api/integrations/woocommerce/products/*`
- WooCommerce read-only order sync: `/api/integrations/woocommerce/orders/*`
- WooCommerce local remap: `/api/integrations/woocommerce/remap/*`
- Orders: `/api/orders/open`, `/api/orders/completed`, `/api/orders/{id}`
- Allocations: `/api/allocations`
- Picks and scanner picks: `/api/picks`
- Fulfillments: `/api/fulfillments`
- Routes: `/api/routes`

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

## Compatibility Note

`GET /api/reports` remains a lightweight module index response. Workflow report
endpoints are implemented under specific report paths.

## Dashboard

### GET /api/dashboard

Returns Command Center data from local records only:
- inventory health cards
- order operations cards
- route cards
- recent activity
- data quality warnings

Aliases:
- `GET /api/dashboard/summary`
- `GET /api/dashboard/activity?limit=25`
- `GET /api/dashboard/warnings`

Dashboard endpoints are read-only.

## WooCommerce Local Remap

These endpoints never call or write WooCommerce. They only manage local mapping
metadata and local item Woo ID metadata.

- `GET /api/integrations/woocommerce/remap/candidates`
- `POST /api/integrations/woocommerce/remap/preview`
- `POST /api/integrations/woocommerce/remap/commit`
- `GET /api/integrations/woocommerce/remap/mappings`
- `POST /api/integrations/woocommerce/remap/deactivate`

Remap preserves manual Pongo OS item fields and does not change stock,
allocated, sellable, picked, fulfilled, or order status quantities.

## Pick Scanner

Scanner-style picking is additive on top of the existing pick commit service:

- `GET /api/picks/orders/{order_id}/scanner`
- `POST /api/picks/orders/{order_id}/scan/preview`
- `POST /api/picks/orders/{order_id}/scan/commit`

Scanner commit increments local picked quantity only through the existing pick
audit path. It does not reduce `In Stock`, reduce `Allocated`, change
`Sellable`, or write WooCommerce.

## SKU Orders Report

- `GET /api/reports/sku-orders`
- `GET /api/reports/sku-orders/summary`
- `GET /api/reports/sku-orders/export`

This report is read-only over local order snapshots.

## Route Local Management

Local route management now includes:
- `PATCH /api/routes/{route_id}`
- `POST /api/routes/{route_id}/stops/reorder`
- `PATCH /api/routes/{route_id}/stops/{stop_id}`
- `GET /api/routes/{route_id}/map`
- `POST /api/routes/{route_id}/geocode/preview`
- `POST /api/routes/{route_id}/geocode/commit`
- `POST /api/routes/{route_id}/optimize/preview`
- `POST /api/routes/{route_id}/optimize/commit`

Map/geocoding/optimization endpoints are provider-architecture endpoints. They
do not expose keys and default to disabled/no-op behavior unless backend
provider configuration is explicitly added later.

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

### GET /api/items/{id}/locations

List stock-location rows for one item. These rows are the operational source for
`In Stock`, `Allocated`, `Sellable`, and `On Order`.

### POST /api/items/{id}/locations

Create or activate an item-location row. This endpoint changes location
metadata only; stock quantities must be changed through receiving, cycle count,
fulfillment, transfer, or adjustment workflows.

### PATCH /api/items/{id}/locations/{item_location_id}

Update item-location metadata such as default flag, active flag, labels, and par
level. This endpoint does not directly change stock.

## Stock by Location v2

- `GET /api/inventory/locations`
- `GET /api/inventory/locations/export`
- `POST /api/inventory/transfers`
- `GET /api/inventory/transfers`
- `GET /api/inventory/transfers/{id}`
- `POST /api/inventory/adjustments`
- `GET /api/inventory/adjustments`
- `GET /api/inventory/adjustments/{id}`

Transfers and adjustments are local-only. They create stock movements and keep
item aggregate totals reconciled with active item-location rows. They do not
write WooCommerce.

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
- The legacy product export header that omits `Manufacturer` and uses
  `Default Lead Time (Days)` is accepted; `Manufacturer` is defaulted blank and
  lead time is normalized to `Default Lead Time Days`.
- Comma-delimited and tab-delimited item import files are accepted.
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

### GET /api/orders/completed

Read-only list of local orders whose `local_status` is `fulfilled` or
`partially_fulfilled`.

Filters:
- `local_status`
- `date_from`
- `date_to`
- `customer_email`
- `woo_order_number`
- `sku`
- `barcode`
- `search`

Rows include Woo order identifiers/status, local status, customer name/email,
order total, order dates, line count, fulfilled line count, total ordered,
allocated, picked, fulfilled, remaining to fulfill, and fulfilled value.

### GET /api/orders/completed/export

Export completed/partially completed order lines as CSV using the same filters.

CSV header order:
- Woo Order Number
- Woo Order ID
- Woo Status
- Local Status
- Customer Name
- Customer Email
- Order Total
- Line SKU
- Line Barcode
- Line Name
- Quantity Ordered
- Quantity Allocated
- Quantity Picked
- Quantity Fulfilled
- Remaining To Fulfill
- Fulfillment Status
- Fulfilled Value
- Date Created
- Date Modified

## Allocations

Allocation reserves local Pongo OS sellable inventory for local open orders.
Allocation is local-only: it does not write WooCommerce, reduce In Stock, pick
orders, create routes, fulfill orders, or send notifications.

### POST /api/allocations/preview

Preview allocation recommendations for one or more local open orders.

Request:
- `order_ids`: local order IDs
- `lines`: optional explicit order line quantities
- `allocation_strategy`: `available_first` for the current MVP
- `allow_partial`
- `created_by`
- `notes`

Preview response includes:
- `total_orders`
- `total_lines`
- `allocatable_lines`
- `partial_lines`
- `skipped_lines`
- `conflict_lines`
- `total_quantity_to_allocate`
- `total_shortage_quantity`
- `preview_orders`

Preview does not update items, order lines, allocations, audit events, stock
movements, or WooCommerce.

### POST /api/allocations/commit

Commit allocation after revalidating all selected lines.

Commit behavior:
- Creates a posted allocation header and allocation lines.
- Increases local item `Allocated`.
- Leaves local item `In Stock` unchanged.
- Recalculates item `Sellable` and `Under Par`.
- Updates local order line `quantity_allocated`.
- Leaves `quantity_picked` unchanged.
- Updates local order status to `open`, `partially_allocated`, or `allocated`.
- Creates `inventory_audit_events` rows with `event_type = allocate`.
- Does not create stock movement rows because allocation does not change
  physical stock.
- Never writes WooCommerce.

Atomicity:
- Commit revalidates current item sellable quantity and remaining order
  quantity.
- Requested quantity cannot exceed remaining order quantity.
- Requested quantity cannot exceed current item Sellable.
- Allocation cannot make item Allocated exceed item In Stock.
- When `allow_partial` is false, any non-fully-allocatable selected line rejects
  the entire commit.

### GET /api/allocations

List allocation history.

Filters:
- `status`
- `allocation_type`
- `order_id`
- `woo_order_id`
- `woo_order_number`
- `date_from`
- `date_to`
- `created_by`

### GET /api/allocations/{id}

Return allocation header, lines, and audit event references.

### GET /api/allocations/{id}/export

Export one allocation as CSV.

CSV columns:
`Allocation Number`, `Status`, `Created At`, `Posted At`,
`Woo Order Number`, `Order ID`, `SKU`, `Barcode`, `Description`, `Warehouse`,
`Inventory Location`, `Quantity Ordered`, `Previously Allocated`,
`Quantity Allocated`, `Allocated After`, `In Stock Before`,
`Sellable Before`, `Sellable After`, `Shortage Quantity`, `Line Status`,
`Notes`.

## Picks

Picking records operational progress against already allocated local order
lines. Picking is local-only: it does not write WooCommerce, reduce local
`In Stock`, reduce local `Allocated`, create routes, fulfill orders, or send
notifications.

### POST /api/picks/preview

Preview pick recommendations for one or more allocated local orders.

Request:
- `order_ids`: local order IDs
- `lines`: optional explicit order line quantities
- `pick_strategy`: `allocated_first` for the current MVP
- `allow_partial`
- `created_by`
- `notes`

Preview response includes:
- `total_orders`
- `total_lines`
- `pickable_lines`
- `partial_lines`
- `skipped_lines`
- `conflict_lines`
- `total_quantity_to_pick`
- `warnings`
- `errors`
- `preview_orders`

Line preview includes ordered quantity, allocated quantity, previously picked
quantity, remaining to pick, recommended pick quantity, picked-after quantity,
warehouse, inventory location, and pick status.

Preview does not update items, order lines, picks, audit events, stock
movements, or WooCommerce.

### POST /api/picks/commit

Commit picking after revalidating all selected lines.

Commit behavior:
- Creates a posted pick header and pick lines.
- Updates local order line `quantity_picked` and legacy `picked_qty`.
- Leaves local order line `quantity_allocated` unchanged.
- Leaves item `In Stock`, `Allocated`, and `Sellable` unchanged.
- Updates local order status to `partially_picked` or `picked` when applicable.
- Creates `inventory_audit_events` rows with `event_type = pick`; previous and
  new stock/allocation/sellable values are identical because picking is not a
  stock movement.
- Does not create stock movement rows.
- Never writes WooCommerce.

Atomicity:
- Commit revalidates remaining quantity to pick.
- Requested quantity cannot exceed allocated quantity.
- Requested quantity cannot exceed allocated minus already picked.
- When `allow_partial` is false, any non-fully-pickable selected line rejects
  the entire commit.

### GET /api/picks

List pick history.

Filters:
- `status`
- `pick_type`
- `order_id`
- `woo_order_id`
- `woo_order_number`
- `date_from`
- `date_to`
- `created_by`

### GET /api/picks/{id}

Return pick header, lines, and audit event references.

### GET /api/picks/{id}/export

Export one pick as CSV.

CSV columns:
`Pick Number`, `Status`, `Created At`, `Posted At`, `Woo Order Number`,
`Order ID`, `SKU`, `Barcode`, `Description`, `Warehouse`,
`Inventory Location`, `Quantity Ordered`, `Quantity Allocated`,
`Previously Picked`, `Quantity Picked`, `Picked After`, `Remaining To Pick`,
`Line Status`, `Notes`.

## Fulfillments

Fulfillment/completion records the local operational moment when picked items
are completed and removed from physical available inventory. Fulfillment is
local-only: it does not write WooCommerce, update WooCommerce order status,
update WooCommerce stock/products, create routes, create shipping labels, send
notifications, create purchase orders, or add supplier workflows.

### POST /api/fulfillments/preview

Preview fulfillment recommendations for one or more picked local orders.

Request:
- `order_ids`: local order IDs
- `lines`: optional explicit order line quantities
- `fulfillment_strategy`: `picked_first` for the current MVP
- `allow_partial`
- `created_by`
- `notes`

Preview response includes:
- `total_orders`
- `total_lines`
- `fulfillable_lines`
- `partial_lines`
- `skipped_lines`
- `conflict_lines`
- `total_quantity_to_fulfill`
- `warnings`
- `errors`
- `preview_orders`

Line preview includes ordered, allocated, picked, previously fulfilled,
remaining to fulfill, recommended fulfill quantity, fulfillment status, current
item In Stock, Allocated, Sellable, warehouse, and inventory location.

Preview does not update item quantities, order lines, fulfillment records,
fulfillment lines, stock movements, audit events, or WooCommerce.

### POST /api/fulfillments/commit

Commit fulfillment after revalidating all selected lines.

Commit behavior:
- Creates a posted fulfillment header and fulfillment lines.
- Updates local order line `quantity_fulfilled` and legacy `fulfilled_qty`.
- Reduces local item `In Stock` by fulfilled quantity.
- Reduces local item `Allocated` by fulfilled quantity.
- Recalculates item `Sellable` and `Under Par`.
- Updates local order status to `partially_fulfilled` or `fulfilled`.
- Creates `stock_movements` rows with `movement_type = fulfill_order`.
- Creates `inventory_audit_events` rows with `event_type = fulfill`.
- Never writes WooCommerce.

Atomicity:
- Commit revalidates remaining quantity to fulfill.
- Requested quantity cannot exceed picked quantity.
- Requested quantity cannot exceed allocated quantity.
- Requested quantity cannot exceed current item In Stock.
- Requested quantity cannot exceed current item Allocated.
- Fulfillment cannot make In Stock or Allocated negative.
- Fulfillment cannot leave Allocated greater than In Stock.
- When `allow_partial` is false, any non-fully-fulfillable selected line rejects
  the entire commit.

Stock movement rows:
- `movement_type = fulfill_order`
- `quantity_delta`/`quantity_change` is negative
- `previous_in_stock`/`old_stock` is item In Stock before fulfillment
- `new_in_stock`/`new_stock` is item In Stock after fulfillment
- `reference_type = fulfillment`
- `reference_id = fulfillments.id`
- `reference_number = fulfillment_number`

Audit event rows:
- `event_type = fulfill`
- `quantity_delta` is negative
- previous/new In Stock, Allocated, and Sellable are captured
- `reference_type = fulfillment`
- `reference_id = fulfillments.id`
- `reference_number = fulfillment_number`

### GET /api/fulfillments

List fulfillment history.

Filters:
- `status`
- `fulfillment_type`
- `order_id`
- `woo_order_id`
- `woo_order_number`
- `date_from`
- `date_to`
- `created_by`

### GET /api/fulfillments/{id}

Return fulfillment header, lines, stock movement references, and audit event
references.

### GET /api/fulfillments/{id}/export

Export one fulfillment as CSV.

CSV columns:
`Fulfillment Number`, `Status`, `Created At`, `Posted At`,
`Woo Order Number`, `Order ID`, `SKU`, `Barcode`, `Description`, `Warehouse`,
`Inventory Location`, `Quantity Ordered`, `Quantity Allocated`,
`Quantity Picked`, `Previously Fulfilled`, `Quantity Fulfilled`,
`Fulfilled After`, `Remaining To Fulfill`, `In Stock Before`,
`Allocated Before`, `Sellable Before`, `In Stock After`, `Allocated After`,
`Sellable After`, `Line Status`, `Notes`.

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

List local open/allocated/picked orders in the operational order queue.
Line-level responses include `quantity_allocated`, `quantity_picked`,
`quantity_fulfilled`, `remaining_to_allocate`, `remaining_to_pick`,
`remaining_to_fulfill`, `picking_status`, `fulfillment_status`,
`shortage_quantity`, and `local_sellable`.

### GET /api/orders/allocated

Future endpoint. The current MVP uses `GET /api/orders/open` plus `/api/picks`
preview/commit.

### POST /api/orders/{id}/allocate

Future endpoint. The current MVP uses `/api/allocations/preview` and
`/api/allocations/commit`.

### GET /api/orders/{id}/pick

Future endpoint. The current MVP uses `GET /api/orders/{id}` plus
`/api/picks` detail.

### POST /api/orders/{id}/pick-scan

Future scanner endpoint. The current MVP supports pick preview and commit
against allocated quantities only.

### POST /api/orders/{id}/complete

Future fulfillment endpoint. Not implemented. Picking does not mark orders
fulfilled and does not update WooCommerce order status.

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

### GET /api/reports/fulfillments

Read-only fulfillment/completed-order line report. Uses `fulfillment_lines` as
the primary source and enriches rows from `fulfillments`, local `orders`, local
`order_items`, and `inventory_items`. It does not use WooCommerce and does not
modify inventory or order state.

Filters:
- `date_from`
- `date_to`
- `warehouse`
- `inventory_location`
- `sku`
- `barcode`
- `category`
- `brand`
- `fulfillment_number`
- `woo_order_number`
- `woo_order_id`
- `customer_email`
- `local_status`
- `created_by`

Date filters use `fulfillments.posted_at` and fall back to
`fulfillments.created_at` when posted time is missing.

Calculation:
- `fulfilled_value = quantity_fulfilled * unit_cost`
- blank unit cost is treated as zero

### GET /api/reports/fulfillments/summary

Return totals and grouped summaries for the same filters as the fulfillment
report. Groupings include warehouse, location, SKU, and order.

### GET /api/reports/fulfillments/export

Export the fulfillment report as CSV using the same filters as the JSON report.

CSV header order:
- Fulfillment Number
- Status
- Posted At
- Created At
- Woo Order Number
- Woo Order ID
- Local Status
- Customer Name
- Customer Email
- Warehouse
- Inventory Location
- SKU
- Barcode
- Description
- Category
- Brand
- Quantity Ordered
- Quantity Allocated
- Quantity Picked
- Quantity Fulfilled
- Previously Fulfilled
- Remaining To Fulfill
- Unit Cost
- Fulfilled Value
- In Stock Before
- Allocated Before
- Sellable Before
- In Stock After
- Allocated After
- Sellable After
- Created By
- Line Notes
- Fulfillment Notes

### GET /api/reports/inventory

Inventory export.

### GET /api/reports/inventory-by-location

Inventory export grouped by item/location.

### GET /api/reports/fulfillment

Order fulfillment export.

### GET /api/reports/sku-orders

SKU/barcode order report with search by SKU, barcode, description, and date range.

## Routes

Route creation is local-only. These endpoints do not call WooCommerce, maps,
geocoding, routing, shipping label, notification, inventory stock, or stock
movement services.

Eligible route candidates are local orders with `local_status = fulfilled` or
`local_status = partially_fulfilled` that are not already assigned to a
non-cancelled route.

### GET /api/routes/candidates

List completed local orders that can be placed onto a route.

Query filters:
- `local_status`
- `customer_email`
- `woo_order_number`
- `search`

Response includes order/customer/shipping snapshots, fulfilled line count,
fulfilled quantity, and a warning when an order is only partially fulfilled.

### POST /api/routes/preview

Validate selected local order IDs before route creation.

Request body:
- `route_date`
- `route_name`
- `driver_name`
- `vehicle_name`
- `order_ids`
- `created_by`
- `notes`

Preview returns valid/invalid stop rows in the selected order. Preview does not
write database rows and does not mutate orders or inventory.

### POST /api/routes/commit

Create a local draft route and route stops from selected valid completed orders.
Commit revalidates selected orders before writing. If any selected order is
invalid, no route is created.

Commit writes:
- `routes`
- `route_stops`

Commit does not update WooCommerce order status, products, or stock. It does
not change local order status, item In Stock, Allocated, Sellable, On Order, or
stock movements.

### GET /api/routes

List local routes.

Query filters:
- `status`
- `route_date`
- `date_from`
- `date_to`
- `driver_name`
- `vehicle_name`
- `search`

### GET /api/routes/{route_id}

Return a route with route stops.

### GET /api/routes/{route_id}/export

Export one route as CSV with route and stop snapshots.

### POST /api/routes/{route_id}/finalize

Mark a draft route finalized locally. This does not dispatch, notify, label,
track delivery, or update WooCommerce.

### POST /api/routes/{route_id}/cancel

Mark a route cancelled locally. Stops remain for audit/review, and the orders
become eligible for a future route because cancelled routes are ignored by the
candidate filter.

Not implemented yet:
- route optimization
- geocoding
- maps
- delivery tracking
- customer notifications

## Items Control Center And Bulk Operations

Implemented endpoints:
- `GET /api/items/search`
- `GET /api/items/{id}/detail`
- `GET /api/items/{id}/activity`
- `GET /api/items/{id}/history?section=...`
- `GET /api/items/{id}/receipts`
- `GET /api/items/{id}/cycle-counts`
- `GET /api/items/{id}/adjustments`
- `GET /api/items/{id}/transfers`
- `GET /api/items/{id}/allocations`
- `GET /api/items/{id}/picks`
- `GET /api/items/{id}/fulfillments`
- `GET /api/items/{id}/orders`
- `GET /api/items/{id}/stock-movements`
- `GET/POST/PATCH/DELETE /api/items/{id}/notes`
- `POST /api/items/bulk/preview`
- `POST /api/items/bulk/commit`

Bulk edit allows metadata fields only. It blocks direct updates to stock fields,
Woo IDs, and Woo stock snapshots.

## UI Saved Views

Implemented endpoints:
- `GET /api/ui/saved-views?page=items`
- `POST /api/ui/saved-views`
- `PATCH /api/ui/saved-views/{id}`
- `DELETE /api/ui/saved-views/{id}`

Saved views are global/system-scoped until auth/RBAC is added.

## Bulk Receiving

Implemented endpoints:
- `POST /api/receipts/bulk/preview`
- `POST /api/receipts/bulk/commit`
- `GET /api/receipts/{id}/detail`
- `GET /api/receipts/{id}/export`

Bulk commit creates one `receipts` row, one `receipt_items` row per valid
line, updates `inventory_item_locations`, recalculates item aggregate stock
fields, and creates one stock movement per committed line. Preview is read-only.

## Scanner Workflows

Implemented endpoints:
- `GET /api/scanner/inventory/lookup`
- `GET /api/scanner/location/lookup`
- `POST /api/scanner/receiving/scan/preview`
- `POST /api/scanner/receiving/scan/commit`
- `POST /api/scanner/cycle-count/preview`
- `POST /api/scanner/cycle-count/commit`
- `POST /api/scanner/transfers/preview`
- `POST /api/scanner/transfers/commit`
- `POST /api/scanner/adjustments/preview`
- `POST /api/scanner/adjustments/commit`

Scanner endpoints treat hardware scanners as keyboard input. Stock-changing
scanner commits are local only and create stock movement/audit records through
the existing stock services.

## Expanded Reports

Implemented read-only row, summary, and CSV export endpoints:
- `/api/reports/inventory-valuation`
- `/api/reports/low-stock`
- `/api/reports/stock-movement-ledger`
- `/api/reports/item-activity`
- `/api/reports/location-utilization`
- `/api/reports/margin-by-sku`
- `/api/reports/receiving-cost`
- `/api/reports/adjustments`

Each report also supports `/summary` and `/export`.
