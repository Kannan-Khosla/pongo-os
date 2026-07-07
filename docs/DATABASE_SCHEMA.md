# Database Schema Plan

This document describes the PostgreSQL tables for Pongo Inventory OS.
The initial SQLAlchemy models and Alembic migration were scaffolded in
`backend/` on July 7, 2026. Direct receiving is now the first stock-changing
workflow; WooCommerce sync and other stock workflows are not implemented yet.

Implementation notes:
- Models live under `backend/app/models/`.
- The initial Alembic revision is `backend/alembic/versions/20260707_0001_initial_schema.py`.
- The item CSV persistence revision is `backend/alembic/versions/20260707_0002_item_csv_fields.py`.
- `barcode` is indexed but not globally unique.
- `DATABASE_URL=postgresql://...` remains valid in environment files; the backend normalizes it to the modern `psycopg` SQLAlchemy driver internally.
- The Items module uses the canonical Zenventory-compatible inventory CSV column order documented in `docs/CSV_COLUMNS.md`.
- Items are backend-persistent through `GET/POST/PATCH /api/items` and
  `GET /api/items/export`.
- Locations are backend-persistent through `GET/POST/PATCH/DELETE
  /api/locations`, `GET /api/locations/export`, and location CSV
  preview/commit endpoints.
- Revision `20260707_0002` adds flat item fields needed for the current
  CSV-canonical Items API: `inventory_location`, `default_location`, and
  `non_inventory`.
- Revision `20260707_0004` adds direct receiving fields to receipts, receipt
  items, and stock movements.

## Canonical CSV Mapping

The current Items module is driven by the inventory CSV columns in
`docs/CSV_COLUMNS.md`. Future import/export and WooCommerce sync work must
preserve that external column order unless the user provides a new real
Zenventory CSV header.

Item-master fields map primarily to `inventory_items`:
- Client
- SKU
- Description
- Category
- Unit of Measurement
- Barcode
- Manufacturer
- Manufacturer Website
- Recommended Retail Price
- Sales Price
- Unit Cost
- Weight
- Default Econ Order
- Default Lead Time Days
- Par Level
- Assembly
- Serializable
- Track Lot
- Perishable
- Re-Order
- Storage Length
- Storage Width
- Storage Height
- Storage Volume
- Brand

Location/stock fields map through `inventory_item_locations`, with location
metadata in `inventory_locations`:
- Warehouse
- Inventory Location
- Default Location
- In Stock
- Allocated
- Sellable
- Under Par
- On Order

The frontend and backend Items API keep these fields flat to match CSV import
and export. Backend services can later normalize richer location workflows into
`inventory_locations` and `inventory_item_locations` without changing the
external CSV contract.

## inventory_items

Purpose: Item master data. Every WooCommerce simple product and every WooCommerce variation maps to one row.

Fields:
- id
- client
- woo_product_id
- woo_variation_id
- sku
- barcode
- description
- category
- unit_of_measurement
- warehouse
- inventory_location
- default_location
- in_stock
- allocated
- sellable
- under_par
- on_order
- manufacturer
- manufacturer_website
- recommended_retail_price
- sales_price
- unit_cost
- weight
- default_econ_order
- default_lead_time_days
- par_level
- assembly
- serializable
- track_lot
- perishable
- reorder
- storage_length
- storage_width
- storage_height
- storage_volume
- brand
- image_url
- active
- non_inventory
- source
- created_at
- updated_at

Relationships:
- Has many `inventory_item_locations`.
- Has many `stock_movements`.
- Can be referenced by `receipt_items` and `order_items`.

Calculated fields:
- sellable = in_stock - allocated
- under_par = in_stock <= par_level
- storage_volume = storage_length * storage_width * storage_height
- inventory_value = in_stock * unit_cost

Index/uniqueness suggestions:
- Unique `(client, sku)` when SKU is present and confirmed unique.
- Unique `(woo_product_id, woo_variation_id)` for linked WooCommerce items.
- Index `barcode`, `description`, `category`, `active`, and `brand`.

## inventory_locations

Purpose: Physical location master data.

Fields:
- id
- client
- warehouse
- location_code
- location_name
- description
- zone
- aisle
- rack
- shelf
- bin
- is_default
- active
- created_at
- updated_at

API field names:
- `warehouse`
- `code` maps to `location_code`
- `name` maps to `location_name`
- `isDefault` maps to `is_default`
- `isActive` maps to `active`

Location CSV fields:
- Warehouse
- Location Code
- Location Name
- Description
- Zone
- Aisle
- Rack
- Shelf
- Bin
- Default
- Active

Relationships:
- Has many `inventory_item_locations`.
- Has many `stock_movements`.

Index/uniqueness suggestions:
- Unique `(client, warehouse, location_code)`.
- Index `warehouse`, `zone`, and `active`.

## inventory_item_locations

Purpose: Stock split by item and location.

Fields:
- id
- inventory_item_id
- location_id
- warehouse
- inventory_location
- is_default_location
- in_stock
- allocated
- sellable
- on_order
- created_at
- updated_at

Relationships:
- Belongs to `inventory_items`.
- Belongs to `inventory_locations`.

Calculated fields:
- sellable = in_stock - allocated.

Index/uniqueness suggestions:
- Unique `(inventory_item_id, location_id)`.
- Index `warehouse`, `inventory_location`, and `is_default_location`.

## stock_movements

Purpose: Immutable stock audit trail for every stock-changing action.

Fields:
- id
- inventory_item_id
- inventory_location_id
- sku
- barcode
- movement_type
- quantity_change
- old_stock
- new_stock
- warehouse
- inventory_location
- reference_number
- unit_cost
- reason
- notes
- reference_type
- reference_id
- created_by
- created_at

Movement type values:
- receive_direct
- direct_receiving
- cycle_count
- manual_adjustment
- order_allocation
- order_pick
- order_completion
- import_update
- woocommerce_sync

Relationships:
- Belongs to `inventory_items`.
- Optionally belongs to `inventory_locations`.
- References receipts, orders, imports, or counts through `reference_type` and `reference_id`.

Index suggestions:
- Index `inventory_item_id`, `inventory_location_id`, `sku`, `barcode`, `movement_type`, `reference_type`, `reference_id`, and `created_at`.

## receipts

Purpose: Direct receiving session header. Pongo does not use purchase orders.

Fields:
- id
- receipt_number
- receipt_type
- status
- client
- warehouse
- reference_number
- created_by
- received_by
- received_date
- received_at
- notes
- created_at
- updated_at

Relationships:
- Has many `receipt_items`.

Index/uniqueness suggestions:
- Unique `receipt_number`.
- Index `client`, `warehouse`, and `received_date`.

Direct receipt number format:
- `DR-YYYYMMDD-NNNN`, for example `DR-20260707-0001`.

## receipt_items

Purpose: Item rows received in a receipt session.

Fields:
- id
- receipt_id
- inventory_item_id
- inventory_location_id
- sku
- category
- description
- quantity
- uom
- quantity_base_uom
- unit_cost
- unit_cost_total
- sales_price
- weight
- brand
- client
- lot_number
- expiration_date
- pkg_number
- item_number
- pallet_number
- warehouse
- default_location
- quantity_received
- received_date
- po_or_receipt_number
- name
- notes
- created_at

Relationships:
- Belongs to `receipts`.
- Belongs to `inventory_items`.
- Belongs to `inventory_locations`.

Calculated fields:
- unit_cost_total = quantity * unit_cost.

Direct receiving behavior:
- Direct receiving creates one receipt row with `receipt_type = direct` and
  `status = posted`.
- Every successful received line creates one receipt item row and one stock
  movement row.
- Item In Stock is increased; Allocated is unchanged.
- Sellable, Under Par, and Storage Volume are recalculated on the item.
- Unit Cost on the receipt line and stock movement does not overwrite item Unit
  Cost in this phase.

## orders

Purpose: Local copy of eligible WooCommerce orders.

Fields:
- id
- woo_order_id
- order_number
- customer_name
- customer_email
- placed_on
- completed_on
- status
- allocation_status
- shipping_address_1
- shipping_address_2
- shipping_address_3
- shipping_city
- shipping_state
- shipping_country
- shipping_zip
- shipping_phone
- billing_address_1
- billing_address_2
- billing_address_3
- billing_city
- billing_state
- billing_country
- billing_zip
- billing_phone
- company
- tracking_number
- raw_woo_payload
- created_at
- updated_at

Relationships:
- Has many `order_items`.
- Can be referenced by `route_stops`.

Index/uniqueness suggestions:
- Unique `woo_order_id`.
- Index `order_number`, `status`, `allocation_status`, and `placed_on`.

## order_items

Purpose: Local order line items matched to inventory items.

Fields:
- id
- order_id
- woo_order_item_id
- inventory_item_id
- line_number
- sku
- barcode
- description
- ordered_qty
- ordered_uom
- allocated_qty
- picked_qty
- unit_cost
- unit_price
- unit_cost_total
- total_price
- brand
- status
- created_at
- updated_at

Relationships:
- Belongs to `orders`.
- Optionally belongs to `inventory_items`.

Calculated fields:
- unit_cost_total = ordered_qty * unit_cost.
- total_price = ordered_qty * unit_price.

## routes

Purpose: Delivery route header.

Fields:
- id
- route_name
- route_date
- status
- start_address
- end_address
- total_stops
- total_distance
- estimated_duration
- created_by
- created_at
- updated_at

Relationships:
- Has many `route_stops`.

Index suggestions:
- Index `route_date`, `status`, and `created_by`.

## route_stops

Purpose: Stops generated from order shipping addresses.

Fields:
- id
- route_id
- order_id
- stop_number
- customer_name
- address_1
- address_2
- city
- state
- country
- zip
- phone
- latitude
- longitude
- optimized_sequence
- notes
- created_at
- updated_at

Relationships:
- Belongs to `routes`.
- Optionally belongs to `orders`.

Index suggestions:
- Index `route_id`, `order_id`, `stop_number`, and `optimized_sequence`.

## import_jobs

Purpose: Track CSV imports.

Current usage: item and location CSV commits create one `import_jobs` row with
`import_type = items` or `import_type = locations`. Preview does not write
import job rows.

Fields:
- id
- file_name
- import_type
- total_rows
- successful_rows
- failed_rows
- status
- created_by
- created_at
- completed_at

Relationships:
- Has many `import_errors`.

API usage:
- `GET /api/import-jobs` lists jobs.
- `GET /api/import-jobs/{id}` returns a job and row-level errors.
- `GET /api/import-jobs/{id}/failed-rows` downloads failed rows as CSV.

Index suggestions:
- Index `import_type`, `status`, `created_by`, and `created_at`.

## import_errors

Purpose: Row-level errors for CSV imports.

Current usage: item and location CSV commits store invalid rows here. The raw
row keeps the canonical CSV column values so failed rows can be downloaded,
fixed, and retried. For location imports, `sku` and `barcode` are left null.

Fields:
- id
- import_job_id
- row_number
- sku
- barcode
- error_message
- raw_row
- created_at

Relationships:
- Belongs to `import_jobs`.

Index suggestions:
- Index `import_job_id`, `row_number`, `sku`, and `barcode`.
