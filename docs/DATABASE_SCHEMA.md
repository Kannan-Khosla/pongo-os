# Database Schema Plan

This document describes planned PostgreSQL tables. It is documentation only; no SQLAlchemy models or Alembic migrations are implemented yet.

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
- zone
- aisle
- rack
- shelf
- bin
- is_default
- active
- created_at
- updated_at

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
- unit_cost
- reason
- reference_type
- reference_id
- created_by
- created_at

Movement type values:
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
- client
- warehouse
- received_by
- received_date
- notes
- created_at

Relationships:
- Has many `receipt_items`.

Index/uniqueness suggestions:
- Unique `receipt_number`.
- Index `client`, `warehouse`, and `received_date`.

Receipt number format:
- `RCPT-YYYY-NNNNN`, for example `RCPT-2026-00045`.

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
- received_date
- po_or_receipt_number
- name
- created_at

Relationships:
- Belongs to `receipts`.
- Belongs to `inventory_items`.
- Belongs to `inventory_locations`.

Calculated fields:
- unit_cost_total = quantity * unit_cost.

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

Index suggestions:
- Index `import_type`, `status`, `created_by`, and `created_at`.

## import_errors

Purpose: Row-level errors for CSV imports.

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
