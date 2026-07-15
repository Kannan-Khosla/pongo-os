# Database Schema Plan

This document describes the PostgreSQL tables for Pongo Inventory OS.
The initial SQLAlchemy models and Alembic migration were scaffolded in
`backend/` on July 7, 2026. Direct receiving and cycle count are the current
stock-changing workflows; WooCommerce product and order sync are read-only
against WooCommerce.

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
- Revision `20260707_0005` adds cycle count header and line tables.
- Revision `20260707_0006` adds WooCommerce item sync metadata and sync run
  history tables.
- Revision `20260707_0007` adds WooCommerce order sync snapshot fields to
  `orders`, `order_items`, and order/line context fields on sync errors.
- Revision `20260707_0008` adds allocation headers, allocation lines, and
  inventory audit events for local allocation reservations.
- Revision `20260707_0013` promotes `inventory_item_locations` to the
  operational stock source, extends workflow lines with item-location
  references, extends stock movements with location before/after fields, and
  adds inventory transfer and stock adjustment tables.

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
- woo_product_type
- woo_permalink
- woo_status
- woo_manage_stock
- woo_stock_status
- woo_stock_quantity_snapshot
- woo_last_synced_at
- woo_sync_status
- woo_sync_error
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

WooCommerce sync rules:
- `woo_product_id` stores the WooCommerce product ID.
- `woo_variation_id` stores the WooCommerce variation ID for variations and is
  null for simple products.
- `woo_stock_quantity_snapshot` stores WooCommerce stock as read-only sync
  metadata only.
- Pongo OS `in_stock` remains the operational source of truth and is not
  overwritten by WooCommerce product sync.
- Manual fields such as Warehouse, Inventory Location, Default Location,
  Allocated, On Order, Unit Cost, Par Level, reorder flags, and location stock
  are not overwritten by WooCommerce product sync.

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

Purpose: Operational stock split by item and location. Item aggregate stock
fields are cached totals recalculated from active rows in this table.

Fields:
- id
- inventory_item_id
- location_id
- client
- warehouse
- inventory_location
- location_code
- location_name
- is_default_location
- in_stock
- allocated
- sellable
- on_order
- par_level
- under_par
- active
- created_at
- updated_at

Relationships:
- Belongs to `inventory_items`.
- Belongs to `inventory_locations`.

Calculated fields:
- sellable = in_stock - allocated.
- under_par = in_stock <= row par_level, falling back to item par level.

Rules:
- A SKU may exist in multiple physical locations.
- Receiving, cycle count, allocation, picking, and fulfillment compatibility resolve a
  specific item-location row.
- Picking reduces stock and allocated quantity from the resolved row.
- Fulfillment compatibility does not double-reduce stock after picking.
- Transfers move stock between item-location rows.
- Adjustments require an explicit type and reason.
- Active row totals must reconcile to `inventory_items` aggregate fields.

Index/uniqueness suggestions:
- Unique `(inventory_item_id, location_id)`.
- Index `warehouse`, `inventory_location`, and `is_default_location`.

## stock_movements

Purpose: Immutable stock audit trail for every stock-changing action.

Fields:
- id
- inventory_item_id
- inventory_location_id
- inventory_item_location_id
- from_inventory_location_id
- to_inventory_location_id
- sku
- barcode
- movement_type
- quantity_change
- old_stock
- new_stock
- warehouse
- inventory_location
- from_warehouse
- from_inventory_location
- to_warehouse
- to_inventory_location
- old_location_stock
- new_location_stock
- old_item_stock
- new_item_stock
- movement_group_id
- movement_source
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
- cycle_count_adjustment
- allocation
- deallocation
- pick
- fulfillment
- transfer_out
- transfer_in
- adjustment_increase
- adjustment_decrease
- damage
- loss
- correction
- manual_adjustment
- order_allocation
- order_pick
- pick_stock_reduction
- order_completion
- import_update
- woocommerce_sync

Relationships:
- Belongs to `inventory_items`.
- Optionally belongs to `inventory_locations`.
- References receipts, orders, imports, or counts through `reference_type` and `reference_id`.

## inventory_transfers

Purpose: Local transfer header for moving stock between item-location rows.

Fields:
- id
- transfer_number
- status
- from_warehouse
- from_inventory_location
- to_warehouse
- to_inventory_location
- notes
- created_by
- committed_at
- cancelled_at
- created_at
- updated_at

## inventory_transfer_lines

Purpose: Transfer line snapshots.

Fields:
- id
- transfer_id
- inventory_item_id
- sku
- barcode
- description
- quantity
- from_inventory_item_location_id
- to_inventory_item_location_id
- from_warehouse
- from_inventory_location
- to_warehouse
- to_inventory_location
- notes
- created_at
- updated_at

## stock_adjustments

Purpose: Explicit local stock correction/damage/loss/found/manual adjustment
header.

Fields:
- id
- adjustment_number
- status
- adjustment_type
- reason
- notes
- created_by
- committed_at
- cancelled_at
- created_at
- updated_at

## stock_adjustment_lines

Purpose: Adjustment line snapshots.

Fields:
- id
- adjustment_id
- inventory_item_id
- inventory_item_location_id
- sku
- barcode
- description
- warehouse
- inventory_location
- old_quantity
- new_quantity
- quantity_change
- unit_cost
- notes
- created_at
- updated_at

Index suggestions:
- Index `inventory_item_id`, `inventory_location_id`, `sku`, `barcode`, `movement_type`, `reference_type`, `reference_id`, and `created_at`.

## cycle_counts

Purpose: Cycle count header for physical inventory counts. Cycle Count is the
second stock-changing workflow after Direct Receiving.

Fields:
- id
- count_number
- status
- warehouse
- inventory_location
- count_type
- notes
- created_by
- created_at
- updated_at
- posted_at

Status values:
- draft
- posted
- cancelled

Current MVP behavior:
- Counts post immediately with `status = posted`.
- Draft cancellation is not implemented yet.

Count type values:
- full_location
- selected_items

Rules:
- `count_number` is generated as `CC-YYYYMMDD-NNNN`.
- Warehouse is required.
- Inventory Location is required for `full_location`.
- Inventory Location is optional for `selected_items`.
- If Inventory Location is provided, it must match an active location by
  Warehouse + Location Code or Warehouse + Location Name.

Relationships:
- Has many `cycle_count_lines`.

Index suggestions:
- Unique `count_number`.
- Index `status`, `warehouse`, `inventory_location`, `count_type`,
  `created_by`, and `posted_at`.

## cycle_count_lines

Purpose: Item rows counted during a cycle count.

Fields:
- id
- cycle_count_id
- item_id
- sku
- barcode
- description
- warehouse
- inventory_location
- system_quantity
- counted_quantity
- variance_quantity
- unit_cost
- variance_value
- notes
- created_at
- updated_at

Relationships:
- Belongs to `cycle_counts`.
- Belongs to `inventory_items`.

Calculation rules:
- system_quantity = item In Stock at preview/commit time.
- variance_quantity = counted_quantity - system_quantity.
- variance_value = variance_quantity * unit_cost.
- Counted quantity must be greater than or equal to zero.
- Unit Cost is captured from the item and defaults to zero when blank.

Commit behavior:
- A line is created for every valid count line.
- Item In Stock is updated to Counted Quantity only when variance is non-zero.
- Allocated is unchanged.
- Sellable, Under Par, and Storage Volume are recalculated.
- A stock movement row is created only for non-zero variance lines with
  `movement_type = cycle_count_adjustment`,
  `reference_type = cycle_count`, and the cycle count id/number.

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

## Received Inventory Report

Purpose: Read-only audit/report view for inventory received through direct
receiving.

Implementation:
- No report table is created.
- `GET /api/reports/received-inventory`,
  `GET /api/reports/received-inventory/summary`, and
  `GET /api/reports/received-inventory/export` generate report rows from
  transactional receipt data.
- `receipt_items` are the primary source for received lines, SKU, description,
  category, brand, quantity received, unit cost, line notes, warehouse, and
  default location.
- `receipts` provide receipt number, receipt type, status, received date,
  reference number, created by, and receipt notes.
- `inventory_items` enrich barcode, category, brand, and description when a
  receipt line does not already store those values.
- `inventory_locations` enrich the inventory location code when the receipt
  line stores a location foreign key.
- `stock_movements` remain the immutable audit trail and are not the primary
  report source.

Calculation:
- total_received_value = quantity_received * unit_cost.
- Null or blank unit cost is treated as zero.

Current limitation:
- The report currently reflects direct receiving records only because purchase
  order receiving is not built.

## orders

Purpose: Local snapshot of eligible WooCommerce orders. Order sync imports
WooCommerce `processing`, `on-hold`, and `pending` orders by default into local
rows for review and workflow. Active open orders can be auto-allocated locally
when enough location-level sellable stock exists. Order sync does not pick,
route, fulfill, reduce In Stock, or write back to WooCommerce.

Fields:
- id
- woo_order_id
- woo_order_number
- woo_status
- local_status
- currency
- customer_id
- customer_email
- customer_first_name
- customer_last_name
- customer_phone
- billing_summary
- shipping_summary
- payment_method
- payment_method_title
- subtotal
- discount_total
- shipping_total
- tax_total
- total
- date_created
- date_modified
- date_paid
- date_completed
- sync_status
- sync_error
- last_synced_at
- order_number
- customer_name
- placed_on
- completed_on
- status
- allocation_status
- pick_status
- completion_status
- auto_allocation_status
- completed_without_picking
- completed_at
- closed_at
- picked_at
- allocation_exception_reason
- workflow_notes
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
- Index `woo_order_number`, `woo_status`, `local_status`, `customer_id`,
  `date_created`, `date_modified`, `sync_status`, `last_synced_at`, legacy
  `order_number`, `status`, `allocation_status`, `pick_status`,
  `completion_status`, `auto_allocation_status`, completion timestamps, and
  `placed_on`.

## order_items

Purpose: Local order line snapshots matched to inventory items where possible.
Unmatched and conflict lines are intentionally stored for staff review.

Fields:
- id
- order_id
- woo_order_item_id
- woo_product_id
- woo_variation_id
- inventory_item_id
- line_number
- sku
- barcode
- description
- name
- quantity_ordered
- quantity_allocated
- quantity_picked
- quantity_stock_reduced
- stock_reduced_at
- quantity_fulfilled
- ordered_qty
- ordered_uom
- allocated_qty
- picked_qty
- fulfilled_qty
- unit_cost
- unit_price
- line_subtotal
- line_total
- line_tax
- matched_status
- allocation_status
- pick_status
- allocation_exception_reason
- availability_status
- sellable_snapshot
- shortage_quantity
- sync_status
- sync_error
- unit_cost_total
- total_price
- brand
- status
- created_at
- updated_at

Relationships:
- Belongs to `orders`.
- Optionally belongs to `inventory_items`.

Read-only order sync rules:
- Matching uses Woo product/variation IDs, exact SKU, and exact Barcode.
- Conflicts are stored as `matched_status = conflict`.
- Missing local matches are stored as `matched_status = unmatched`; order sync
  does not create inventory items.
- `quantity_allocated`, `quantity_picked`, `quantity_stock_reduced`,
  `quantity_fulfilled`, legacy `allocated_qty`, legacy `picked_qty`, and legacy
  `fulfilled_qty` are preserved during order sync.
- `sellable_snapshot = inventory_items.in_stock - inventory_items.allocated`
  at sync time.
- `shortage_quantity = max(quantity_ordered - sellable_snapshot, 0)`.
- Order sync can auto-allocate active orders by increasing local Allocated and
  creating allocation/audit rows. It does not update `inventory_items.in_stock`
  or create stock movements.

## allocations

Purpose: Local allocation header for reserving sellable inventory against open
orders. Allocation is between Open Orders and Picking.

Fields:
- id
- allocation_number
- status
- allocation_type
- order_id
- woo_order_id
- woo_order_number
- auto_allocated
- allocation_source
- notes
- created_by
- posted_at
- cancelled_at
- created_at
- updated_at

Status values:
- posted
- draft (reserved for future preview persistence)
- cancelled (reserved for future cancellation/reversal)

Allocation type values:
- single_order
- batch

Rules:
- `allocation_number` format is `AL-YYYYMMDD-NNNN`.
- Current commit creates posted allocations directly.
- Auto-allocation creates the same records with `auto_allocated = true` and
  `allocation_source = auto`.
- Allocation does not write WooCommerce and does not reduce In Stock.

## allocation_lines

Purpose: Line-level allocation audit and reservation snapshot.

Fields:
- id
- allocation_id
- order_id
- order_line_id
- item_id
- sku
- barcode
- description
- warehouse
- inventory_location
- quantity_ordered
- quantity_previously_allocated
- quantity_to_allocate
- quantity_allocated_after
- in_stock_before
- allocated_before
- sellable_before
- allocated_after
- sellable_after
- shortage_quantity
- auto_allocated
- allocation_source
- status
- notes
- created_at
- updated_at

Rules:
- `quantity_to_allocate` must be greater than zero.
- `quantity_to_allocate` cannot exceed remaining unallocated order quantity.
- `quantity_to_allocate` cannot exceed current item Sellable.
- Allocation cannot make item Allocated exceed item In Stock.

Line status values:
- allocated
- partial
- skipped
- conflict
- error

## picks

Purpose: Local pick header for recording operational picking progress against
already allocated order lines. Picking is the local stock reduction step before
local completion.

Fields:
- id
- pick_number
- status
- pick_type
- order_id
- woo_order_id
- woo_order_number
- notes
- created_by
- posted_at
- cancelled_at
- created_at
- updated_at

Status values:
- posted
- cancelled (reserved for future cancellation/reversal)

Pick type values:
- single_order
- batch

Rules:
- `pick_number` format is `PK-YYYYMMDD-NNNN`.
- Current commit creates posted picks directly.
- Picking does not write WooCommerce.
- Picking reduces item-location and aggregate In Stock.
- Picking reduces item-location and aggregate Allocated.
- Picking creates `pick_stock_reduction` stock movement rows.

## pick_lines

Purpose: Line-level pick audit and progress snapshot.

Fields:
- id
- pick_id
- order_id
- order_line_id
- item_id
- sku
- barcode
- description
- warehouse
- inventory_location
- quantity_ordered
- quantity_allocated
- quantity_previously_picked
- quantity_to_pick
- quantity_stock_reduced
- stock_movement_id
- stock_reduced_at
- idempotency_key
- quantity_picked_after
- remaining_to_pick
- status
- notes
- created_at
- updated_at

Rules:
- `quantity_to_pick` must be greater than zero.
- `quantity_to_pick` cannot exceed `quantity_allocated`.
- `quantity_to_pick` cannot exceed `quantity_allocated - quantity_picked`.
- `quantity_stock_reduced` cannot exceed picked or allocated quantity.
- `quantity_picked_after = quantity_previously_picked + quantity_to_pick`.
- `remaining_to_pick = quantity_allocated - quantity_picked_after`.
- `idempotency_key` prevents replayed scanner commits from reducing stock a
  second time.

Line status values:
- picked
- partial
- skipped
- conflict
- error

## fulfillments

Purpose: Local legacy fulfillment/completion header for compatibility and
history. Picking now removes stock from local physical inventory; fulfillment
does not double-reduce stock after picking.

Fields:
- id
- fulfillment_number
- status
- fulfillment_type
- order_id
- woo_order_id
- woo_order_number
- notes
- created_by
- posted_at
- cancelled_at
- created_at
- updated_at

Status values:
- posted
- cancelled (reserved for future cancellation/reversal)

Fulfillment type values:
- single_order
- batch

Rules:
- `fulfillment_number` format is `FL-YYYYMMDD-NNNN`.
- Current commit creates posted fulfillments directly.
- Normal picked-order fulfillment creates compatibility records only because
  stock was already reduced during picking.
- Unpicked fulfillment is blocked by the service rather than silently reducing
  stock through the old path.
- Fulfillment does not write WooCommerce.
- Fulfillment does not create routes, shipping labels, purchase orders, supplier
  records, or customer notifications.

## fulfillment_lines

Purpose: Line-level legacy fulfillment/completion audit snapshot.
Fulfillment Report uses this table as its primary source and enriches rows from
`fulfillments`, local `orders`, local `order_items`, and `inventory_items`.
Completed Orders export uses local `orders` and `order_items`. No additional
reporting tables are required.

Fields:
- id
- fulfillment_id
- order_id
- order_line_id
- item_id
- sku
- barcode
- description
- warehouse
- inventory_location
- quantity_ordered
- quantity_allocated
- quantity_picked
- quantity_previously_fulfilled
- quantity_to_fulfill
- quantity_fulfilled_after
- remaining_to_fulfill
- in_stock_before
- allocated_before
- sellable_before
- in_stock_after
- allocated_after
- sellable_after
- status
- notes
- created_at
- updated_at

Rules:
- `quantity_to_fulfill` must be greater than zero.
- `quantity_to_fulfill` cannot exceed `quantity_picked - quantity_fulfilled`.
- `quantity_to_fulfill` cannot exceed current item In Stock.
- `quantity_to_fulfill` cannot exceed current item Allocated.
- Fulfillment does not double-reduce stock already reduced by picking.
- Normal picked-order fulfillment creates no stock movement rows.

Line status values:
- fulfilled
- partial
- skipped
- conflict
- error

## inventory_audit_events

Purpose: Audit local inventory and order workflow state changes. Allocation uses
this table because it changes Allocated and Sellable while leaving In Stock
unchanged. Picking uses it alongside `pick_stock_reduction` stock movements to
capture before/after allocated and sellable values. Completion and fulfillment
compatibility use it for local close/history events.

Fields:
- id
- item_id
- sku
- barcode
- event_type
- quantity_delta
- previous_in_stock
- new_in_stock
- previous_allocated
- new_allocated
- previous_sellable
- new_sellable
- warehouse
- inventory_location
- reference_type
- reference_id
- reference_number
- notes
- created_by
- created_at

Allocation audit rules:
- `event_type = allocate`
- `quantity_delta = quantity_to_allocate`
- `previous_in_stock = new_in_stock`
- `new_allocated = previous_allocated + quantity_to_allocate`
- `new_sellable = previous_in_stock - new_allocated`
- `reference_type = allocation`
- `reference_id = allocations.id`
- `reference_number = allocations.allocation_number`

Picking audit rules:
- `event_type = pick`
- `quantity_delta = quantity_to_pick`
- `previous_in_stock = new_in_stock`
- `previous_allocated = new_allocated`
- `previous_sellable = new_sellable`
- `reference_type = pick`
- `reference_id = picks.id`
- `reference_number = picks.pick_number`

Fulfillment audit rules:
- `event_type = fulfill`
- `quantity_delta = -quantity_to_fulfill`
- `new_in_stock = previous_in_stock - quantity_to_fulfill`
- `new_allocated = previous_allocated - quantity_to_fulfill`
- `new_sellable = new_in_stock - new_allocated`
- `reference_type = fulfillment`
- `reference_id = fulfillments.id`
- `reference_number = fulfillments.fulfillment_number`

Current limitation:
- Allocation, pick, and fulfillment cancellation/reversal are documented as
  future work.
- WooCommerce write-back, routing, shipping labels, outbound/customer
  notifications, purchase
  orders, and supplier workflows are not implemented yet.

## routes

Purpose: Local delivery route header for manually planned completed orders.

Current behavior:
- Routes are created from local orders with `local_status = fulfilled` or
  `partially_fulfilled`.
- Routes are local-only and do not call WooCommerce, maps, geocoding,
  optimization, shipping label, outbound/customer notification, or inventory
  stock services.
- Route cancellation keeps route stops for review/audit and makes the order
  eligible for future route planning.

Fields:
- id
- route_number
- status: `draft`, `finalized`, or `cancelled`
- route_name
- route_date
- driver_name
- vehicle_name
- notes
- start_address
- end_address
- total_stops
- total_distance
- estimated_duration
- created_by
- finalized_at
- cancelled_at
- created_at
- updated_at

Relationships:
- Has many `route_stops`.

Index suggestions:
- Index `route_number`, `route_date`, `status`, `driver_name`,
  `vehicle_name`, `created_by`, `finalized_at`, and `cancelled_at`.

Notes:
- `start_address`, `end_address`, `total_distance`, and `estimated_duration`
  are retained for future provider-backed route optimization but are not
  populated by the current route creation foundation.

## route_stops

Purpose: Stop snapshots generated from completed local orders.

Fields:
- id
- route_id
- order_id
- stop_sequence
- woo_order_id
- woo_order_number
- stop_number
- customer_name
- customer_email
- customer_phone
- shipping_summary
- delivery_notes
- local_status
- stop_status
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
- Belongs to `orders`.

Index suggestions:
- Index `route_id`, `order_id`, `stop_sequence`, `stop_number`,
  `woo_order_id`, `woo_order_number`, `customer_email`, `local_status`,
  `stop_status`, and `optimized_sequence`.

Notes:
- Route stops snapshot Woo/customer/shipping/local-status fields at route
  creation time so CSV exports remain stable even if the source order later
  changes.
- `latitude`, `longitude`, `geocode_status`, `geocode_provider`,
  `geocode_error`, `internal_notes`, and `optimized_sequence` support local
  map payloads plus future provider-backed geocoding/optimization. Providers
  are disabled by default and no external calls are made by current tests or
  local UX.

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

## woocommerce_sync_runs

Purpose: Track WooCommerce product/variation REST sync, order REST sync, and
signed webhook order-import commits to the local Pongo OS database. These are
local database operations and do not imply a WooCommerce write.

Fields:
- id
- sync_type
- status
- started_at
- completed_at
- created_by
- total_remote_records
- created_count
- updated_count
- matched_count
- skipped_count
- conflict_count
- error_count
- notes

Current usage:
- Product/variation commit creates one run with `sync_type = products`.
- Order commit creates one run with `sync_type = orders`.
- A processed phase-1 `order.created` webhook creates one order sync run and
  links it from `woocommerce_webhook_deliveries.sync_run_id`.
- Sync runs represent local database sync only; they do not represent writes to
  WooCommerce.

Relationships:
- Has many `woocommerce_sync_errors`.
- Can be referenced by `woocommerce_webhook_deliveries`.

## woocommerce_sync_errors

Purpose: Row-level sync errors, conflicts, unmatched rows, and skipped records
from WooCommerce product and order sync commits.

Fields:
- id
- sync_run_id
- remote_order_id
- remote_line_item_id
- remote_product_id
- remote_variation_id
- sku
- barcode
- error_message
- raw_payload
- created_at

Relationships:
- Belongs to `woocommerce_sync_runs`.

Safety:
- Raw payloads must not contain credentials. The sync service stores normalized
  preview row details, not request URLs or secrets.

## woocommerce_webhook_deliveries

Purpose: Durable receipt, idempotency, audit, and internal staff-event source
for signed WooCommerce webhook deliveries. Added by Alembic revision
`20260710_0018_woocommerce_order_webhooks.py`, which follows
`20260709_0017_order_workflow_zenventory.py`.

Fields:
- id
- delivery_id
- webhook_id
- payload_sha256
- topic
- resource
- event
- source_host
- woo_order_id
- local_order_id
- sync_run_id
- processing_status
- created_order
- attempt_count
- error_message
- received_at
- processed_at
- updated_at

Relationships:
- `local_order_id` optionally references `orders.id` after a delivery imports or
  finds the local order.
- `sync_run_id` optionally references `woocommerce_sync_runs.id` for the local
  order import performed by that delivery.

Identity and replay rules:
- Unique `(webhook_id, delivery_id, payload_sha256)` through
  `uq_woo_webhook_delivery_identity`.
- `payload_sha256` is the lowercase SHA-256 digest of the exact raw body.
- A replay of a terminal row increments `attempt_count` and does not repeat
  order import, allocation, or the staff new-order event.
- The same delivery ID with a different payload hash is a distinct auditable
  row rather than being silently deduplicated.

Processing status values:
- `received`
- `processed`
- `processed_with_errors`
- `ignored`
- `failed`

Phase-1 behavior:
- Only authenticated `order.created` can import an order and set
  `created_order = true` when a new local `orders` row was created.
- A delayed `order.created` payload older than or equal to the matching local
  `orders.date_modified` snapshot is stored as `ignored`; it cannot regress the
  order or produce a staff event.
- Other authenticated topics are stored with `processing_status = ignored` and
  do not mutate orders.
- Setup pings do not create a row.
- A successful delivery that creates a new local order also creates one
  immutable `woocommerce_order_events` row in the same transaction.
- Failed, ignored, stale, duplicate, and already-local deliveries create no
  event outbox row. A failed delivery that later succeeds gets its event ID only
  at the successful commit.

Safety:
- The table does not store the webhook secret, REST API credentials, request
  headers, or a second copy of the raw customer payload.
- `error_message` is a bounded safe processing summary, not a credential or raw
  payload log.
- A webhook may trigger the existing audited local auto-allocation path but
  does not write WooCommerce, reduce local In Stock, or create a stock movement.
- Staff feed rows are local UI notification data only; no outbound/customer
  notification is sent.

Indexes:
- Index `delivery_id`, `webhook_id`, `payload_sha256`, `topic`, `resource`,
  `event`, `source_host`, `woo_order_id`, `local_order_id`, `sync_run_id`,
  `processing_status`, `created_order`, `received_at`, `processed_at`, and
  `updated_at`.

## woocommerce_order_events

Purpose: Immutable staff-notification outbox for successfully committed new
orders from the signed webhook. Added by Alembic revision
`20260710_0019_woocommerce_order_event_outbox.py` after the delivery ledger.

Fields:
- id
- webhook_delivery_id
- local_order_id
- woo_order_id
- event_type
- created_at

Relationships and identity:
- `webhook_delivery_id` uniquely references
  `woocommerce_webhook_deliveries.id`.
- `local_order_id` references `orders.id`.
- One successful new-order delivery can publish at most one event.

Cursor rules:
- `GET /api/integrations/woocommerce/webhooks/events` pages by this table's
  immutable `id`, not by the mutable delivery processing row.
- `latest_event_id` is the informational maximum event ID.
- `next_after_id` is the safe exclusive consumer cursor.
- `initialize = true` returns no events and seeds the cursor at the current
  event high-water mark.
- `has_more = true` requires another page request.
- PostgreSQL import and feed high-water reads share a transaction advisory lock
  so event IDs become visible in commit order.

Safety:
- This table stores no customer payload, signature, secret, or request headers.
- Order/customer display fields are read from the linked local order only when
  the internal staff feed is requested.

Indexes:
- Unique `webhook_delivery_id`.
- Index `local_order_id`, `woo_order_id`, `event_type`, and `created_at`.

## woo_item_mappings

Purpose: Track local-only WooCommerce product/variation to Pongo OS item remap
metadata.

Fields:
- id
- item_id
- woo_product_id
- woo_variation_id
- woo_sku
- woo_name
- mapping_source
- confidence
- active
- note
- created_at
- updated_at

Current usage:
- Remap preview/commit manages this table through
  `/api/integrations/woocommerce/remap/*`.
- Commit deactivates prior active mappings for the same Woo product/variation
  and creates a new active local mapping.
- Commit may update local item Woo ID metadata but does not overwrite manual
  fields or inventory quantities.

Safety:
- Local-only.
- No WooCommerce API writes.
- No local stock, allocation, picked, fulfilled, route, or order status
  mutations.

## ui_saved_views

Purpose: Store global saved filters, visible columns, and sort preferences for
operator pages while auth/RBAC is delayed.

Fields:
- id
- view_key
- name
- page
- filters_json
- columns_json
- sort_json
- is_default
- created_by
- created_at
- updated_at

Current usage:
- Items page saved views.

## item_notes

Purpose: Lightweight item notes for the Item Detail Control Center.

Fields:
- id
- inventory_item_id
- note
- note_type
- created_by
- created_at
- updated_at

Relationships:
- Belongs to `inventory_items`.

## scanner_sessions and scanner_events

Purpose: Track scanner workflow sessions/events for local debugging and
warehouse audit context.

`scanner_sessions` fields:
- id
- session_type
- status
- reference_type
- reference_id
- created_by
- completed_at
- created_at
- updated_at

`scanner_events` fields:
- id
- scanner_session_id
- session_type
- scan_input
- matched_entity_type
- matched_entity_id
- result_status
- message
- quantity
- warehouse
- inventory_location
- created_at

## Receipt Extensions

Receipts now include optional session fields:
- source
- committed_at
- cancelled_at

Receipt items now include:
- line_status
- scan_input

Bulk receiving uses `receipt_type = bulk` and `status = committed`.
Direct receiving remains compatible with existing direct receipt behavior.

## Pongo Insights Schema Impact

Pongo Insights adds no new tables or columns in the current implementation.
It reads existing local `orders`, `order_items`, and `inventory_items` records
and returns empty states or data quality warnings when optional WooCommerce
snapshot fields such as refunds, coupon lines, subscriptions, or address fields
are not available.

## woo_writeback_queue

Purpose: Local staging-only queue for explicit WooCommerce writeback testing.
Rows are created from previewed payloads and do not imply a WooCommerce request
was sent.

Fields:
- id
- operation_type
- entity_type
- entity_id
- woo_entity_id
- woo_product_id
- woo_variation_id
- woo_order_id
- payload_json
- status
- environment
- dry_run
- allowed_host
- requested_by
- approved_by
- preview_json
- response_json
- error_message
- created_at
- approved_at
- sent_at
- updated_at

Allowed operation types:
- `update_product_stock`
- `update_variation_stock`
- `update_order_status`

Safety:
- live sends require staging live-test mode, dry-run off, approval, exact host
  match, and allowlisted operation/path/payload guards
- production writeback is not enabled
- DELETE is not supported
- arbitrary endpoint writes are not supported
- customer, coupon, refund, and product metadata writes are not supported
- credentials remain backend environment variables only
