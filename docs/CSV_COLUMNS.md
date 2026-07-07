# CSV Columns

The inventory CSV column order is canonical and must be preserved in import/export unless the user provides a new real Zenventory CSV header.

The Items module, product import, product export, inventory export, item edit form, and future WooCommerce field mapping must be designed around this inventory CSV structure. Do not rename these columns in CSV import/export output unless a clear internal mapping is documented and approved.

Column source values:
- WooCommerce: synced from WooCommerce later.
- Pongo OS: owned by Pongo Inventory OS.
- calculated: derived by the system.
- manual/CSV: entered by staff or imported from Zenventory-compatible CSV.
- future: planned but not required in first implementation.

## Canonical Inventory Item CSV

Current reference: `docs/CSV_templates_with_data/items.csv`.

Canonical header order:

```csv
Client,SKU,Description,Category,Unit of Measurement,Warehouse,Inventory Location,Default Location,In Stock,Allocated,Sellable,Under Par,On Order,Barcode,Manufacturer,Manufacturer Website,Recommended Retail Price,Sales Price,Unit Cost,Weight,Default Econ Order,Default Lead Time Days,Par Level,Assembly,Serializable,Track Lot,Perishable,Re-Order,Storage Length,Storage Width,Storage Height,Storage Volume,Brand
```

| Order | Column | Source / Ownership | Notes |
| ---: | --- | --- | --- |
| 1 | Client | Pongo OS/manual/CSV | Usually Pongo or a client/account value. |
| 2 | SKU | WooCommerce/CSV | Required unique item identifier. |
| 3 | Description | WooCommerce/CSV | Product or item description/name. |
| 4 | Category | WooCommerce/CSV | Product category. |
| 5 | Unit of Measurement | manual/CSV | Example: EA, bag, case, unit. |
| 6 | Warehouse | manual/CSV/location | Example: Main Warehouse. |
| 7 | Inventory Location | manual/CSV/location | Physical location where stock exists. |
| 8 | Default Location | manual/CSV/location | Primary/default location for the item. |
| 9 | In Stock | CSV/WooCommerce later/location totals | Current physical stock quantity. |
| 10 | Allocated | Pongo OS | Quantity allocated to open orders. |
| 11 | Sellable | calculated | In Stock minus Allocated. |
| 12 | Under Par | calculated | In Stock <= Par Level. |
| 13 | On Order | manual/CSV/future | Kept for future planning even though Pongo does not currently use POs. |
| 14 | Barcode | manual/CSV | Searchable and editable scanner field. |
| 15 | Manufacturer | manual/CSV | Manufacturer name. |
| 16 | Manufacturer Website | manual/CSV | Manufacturer URL. |
| 17 | Recommended Retail Price | manual/CSV | RRP/MSRP field. |
| 18 | Sales Price | WooCommerce/CSV/manual | Editable in Pongo OS for now. |
| 19 | Unit Cost | manual/CSV | Needed for inventory value, receiving, and reports. |
| 20 | Weight | WooCommerce/CSV | Item weight. |
| 21 | Default Econ Order | manual/CSV/future | Reorder planning field. |
| 22 | Default Lead Time Days | manual/CSV | Lead time field. |
| 23 | Par Level | manual/CSV | Used to calculate Under Par. |
| 24 | Assembly | manual/CSV | Boolean. |
| 25 | Serializable | manual/CSV | Boolean. |
| 26 | Track Lot | manual/CSV | Boolean. |
| 27 | Perishable | manual/CSV | Boolean. |
| 28 | Re-Order | manual/CSV | Boolean. |
| 29 | Storage Length | manual/CSV/WooCommerce | Dimension field. |
| 30 | Storage Width | manual/CSV/WooCommerce | Dimension field. |
| 31 | Storage Height | manual/CSV/WooCommerce | Dimension field. |
| 32 | Storage Volume | calculated | Storage Length x Storage Width x Storage Height. |
| 33 | Brand | WooCommerce/CSV/manual | Woo taxonomy/meta or manual override. |

## Inventory Field Split

Item-master fields:
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

Location/stock fields:
- Warehouse
- Inventory Location
- Default Location
- In Stock
- Allocated
- Sellable
- Under Par
- On Order

The current database supports the split through `inventory_items`,
`inventory_locations`, and `inventory_item_locations`. The Items API now stores
the canonical item row persistently in `inventory_items`, including flat
`inventory_location` and `default_location` fields for the current CSV-driven
MVP. Future backend services can map richer CSV imports into normalized
location tables without changing the external CSV contract.

## Product Import

Product import must use the canonical inventory item CSV header above.

Current implementation:
- `POST /api/items/import/preview` validates and previews imports without database writes.
- `POST /api/items/import/commit` creates or updates local item records and stores an import job.
- `GET /api/import-jobs`, `GET /api/import-jobs/{id}`, and `GET /api/import-jobs/{id}/failed-rows` expose import history and failed row downloads.
- `docs/csv-reference/sample-items-import.csv` provides fake sample rows for testing the current format.

Import rules:
- Validate the header row against the canonical column list or a newly supplied real Zenventory header.
- Trim header whitespace, but keep column names case-sensitive.
- Reject files that are missing canonical columns.
- Ignore extra columns and report warnings.
- Match existing items by exact SKU first and exact Barcode second.
- Reject a row when SKU and Barcode match two different existing items.
- Create missing items.
- Update existing items.
- Show a preview before commit.
- Show failed rows.
- Allow failed rows CSV download.

Calculated import fields:
- Sellable is recalculated as `In Stock - Allocated`.
- Under Par is recalculated as `In Stock <= Par Level`.
- Storage Volume is recalculated as `Storage Length x Storage Width x Storage Height`.
- If imported calculated values differ, the calculated values are used and warnings are returned.

Current CSV import is a migration/local item upsert path only. It must not call
WooCommerce, receiving, cycle count, allocation, picking, or route workflows.
Future operational imports that perform stock-changing actions must create stock
movement/audit rows.

## Product Export / Inventory Export

Product export and inventory export must emit only the canonical inventory item CSV columns in the exact order above unless a separate export mode is explicitly added later.

Current implementation: `GET /api/items/export` exports filtered backend rows
using this exact header order.

Do not include frontend-only/internal fields such as:
- id
- imageUrl
- active
- nonInventory
- wooProductId
- wooVariationId

## Received Inventory Report

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| Receipt | Pongo OS | Required | Receipt number such as RCPT-2026-00045. |
| SKU | Pongo OS | Required | Received item SKU. |
| Category | Pongo OS | Optional | Snapshot from item. |
| Description | Pongo OS | Required | Snapshot from item. |
| Quantity | manual | Required | Received quantity. |
| UOM | Pongo OS | Optional | Unit of measurement. |
| Unit Cost Total | calculated | Optional | Quantity * Unit Cost. |
| Quantity Base UOM | calculated | Optional | Normalized quantity. |
| Lot Number | manual | Optional | Receiving detail. |
| Expiration Date | manual | Optional | Receiving detail. |
| PKG Number | manual | Optional | Receiving detail. |
| Item Number | manual | Optional | Receiving detail. |
| Pallet Number | manual | Optional | Receiving detail. |
| Unit Cost | manual | Optional | Entered during receiving. |
| Sales Price | manual | Optional | Optional override. |
| Weight | manual/Pongo OS | Optional | Optional. |
| Brand | Pongo OS | Optional | Snapshot from item. |
| Client | Pongo OS | Optional | Tenant/client label. |
| Received Date | Pongo OS | Required | Receipt date. |
| Warehouse | manual/Pongo OS | Required | Selected warehouse. |
| PO or Receipt Number | Pongo OS | Required | Use receipt number because Pongo does not use POs. |
| Name | Pongo OS | Optional | Receiver or item display name. |

## Order Fulfillment Export

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| CO# | WooCommerce | Required | Woo order number. |
| Client | Pongo OS | Optional | Tenant/client label. |
| SKU | Pongo OS/WooCommerce | Required | Matched item SKU. |
| Ordered Qty | WooCommerce | Required | Ordered quantity. |
| Ordered UOM | Pongo OS | Optional | Unit of measurement. |
| Completed On | Pongo OS/WooCommerce | Optional | Completion timestamp. |
| Unit Cost | Pongo OS | Optional | Item cost snapshot. |
| Unit Cost Total | calculated | Optional | Ordered Qty * Unit Cost. |
| Placed On | WooCommerce | Required | Order date. |
| On Hold | WooCommerce/future | Optional | Hold flag if available. |
| Hold Until | WooCommerce/future | Optional | Hold date if available. |
| Unit Price | WooCommerce | Optional | Order line price. |
| Total Price | calculated/WooCommerce | Optional | Quantity * Unit Price or Woo total. |
| Description | WooCommerce/Pongo OS | Required | Line description. |
| Line # | WooCommerce/Pongo OS | Optional | Order line number. |
| Customer | WooCommerce | Required | Customer name. |
| Shipping Address 1 | WooCommerce | Optional | Address field. |
| Shipping Address 2 | WooCommerce | Optional | Address field. |
| Shipping Address 3 | WooCommerce | Optional | Address field. |
| Shipping City | WooCommerce | Optional | Address field. |
| Shipping State | WooCommerce | Optional | Address field. |
| Shipping Country | WooCommerce | Optional | Address field. |
| Shipping Zip | WooCommerce | Optional | Address field. |
| Shipping Phone | WooCommerce | Optional | Address field. |
| Billing Address 1 | WooCommerce | Optional | Address field. |
| Billing Address 2 | WooCommerce | Optional | Address field. |
| Billing Address 3 | WooCommerce | Optional | Address field. |
| Billing City | WooCommerce | Optional | Address field. |
| Billing State | WooCommerce | Optional | Address field. |
| Billing Country | WooCommerce | Optional | Address field. |
| Billing Zip | WooCommerce | Optional | Address field. |
| Billing Phone | WooCommerce | Optional | Address field. |
| Created By | Pongo OS | Optional | Staff/system user. |
| Brand | Pongo OS/WooCommerce | Optional | Brand snapshot. |
| Tracking Number | WooCommerce/future | Optional | May come from plugin/meta field. |
| Company | WooCommerce | Optional | Company field. |

## SKU/Barcode Order Report

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| SKU | Pongo OS/WooCommerce | Required | Searchable. |
| Barcode | Pongo OS | Optional | Searchable. |
| Description | Pongo OS/WooCommerce | Required | Searchable. |
| Brand | Pongo OS/WooCommerce | Optional | Item brand. |
| Order Number | WooCommerce | Required | Woo order number. |
| Order Date | WooCommerce | Required | Date range filter. |
| Customer | WooCommerce | Required | Customer name. |
| Ordered Qty | WooCommerce | Required | Ordered quantity. |
| Unit Cost | Pongo OS | Optional | Item cost snapshot. |
| Unit Price | WooCommerce | Optional | Order line unit price. |
| Unit Cost Total | calculated | Optional | Ordered Qty * Unit Cost. |
| Total Price | calculated/WooCommerce | Optional | Ordered Qty * Unit Price. |
| Order Status | WooCommerce/Pongo OS | Required | Current local/Woo status. |
| Completed On | WooCommerce/Pongo OS | Optional | Completion date. |

## Location Import

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| Client | manual | Optional | Tenant/client label. |
| Warehouse | manual | Required | Warehouse name/code. |
| Location Code | manual | Required | Unique within warehouse. |
| Location Name | manual | Optional | Display name. |
| Zone | manual | Optional | Physical zone. |
| Aisle | manual | Optional | Physical aisle. |
| Rack | manual | Optional | Physical rack. |
| Shelf | manual | Optional | Physical shelf. |
| Bin | manual | Optional | Physical bin. |
| Is Default | manual | Optional | Boolean. |
| Active | manual | Optional | Boolean. |
