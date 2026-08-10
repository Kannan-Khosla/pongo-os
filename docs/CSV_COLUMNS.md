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

Synthetic reference: `docs/csv-reference/sample-items-import.csv`.

Canonical header order:

```csv
Client,SKU,Description,Category,Unit of Measurement,Warehouse,Inventory Location,Default Location,In Stock,Allocated,Sellable,Under Par,On Order,Barcode,Manufacturer,Manufacturer Website,Recommended Retail Price,Sales Price,Unit Cost,Weight,Default Econ Order,Default Lead Time Days,Par Level,Assembly,Serializable,Track Lot,Perishable,Re-Order,Storage Length,Storage Width,Storage Height,Storage Volume,Brand,Tags
```

| Order | Column | Source / Ownership | Notes |
| ---: | --- | --- | --- |
| 1 | Client | Pongo OS/manual/CSV | Usually Pongo or a client/account value. |
| 2 | SKU | WooCommerce/CSV | Required unique item identifier. |
| 3 | Description | WooCommerce/CSV | Legacy CSV field containing the product title. The UI labels this as Product Title; Woo long descriptions are not imported or displayed. |
| 4 | Category | WooCommerce/CSV | Product category. |
| 5 | Unit of Measurement | manual/CSV | Example: EA, bag, case, unit. |
| 6 | Warehouse | manual/CSV/location | Example: Main Warehouse. |
| 7 | Inventory Location | manual/CSV/location | Physical location where stock exists. |
| 8 | Default Location | manual/CSV/location | Primary/default location for the item. |
| 9 | In Stock | audited stock workflows/location totals | Retained in the canonical format, but ordinary metadata import never commits it. |
| 10 | Allocated | Pongo OS | Retained in the canonical format; allocation is automatic and ordinary imports never commit it. |
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
| 34 | Tags | Pongo OS/CSV/manual | Optional comma-separated item labels. Bulk tagging adds labels without removing existing ones. |

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

The primary item-import contract is backend-generated and outcome-specific; it
does not require users to reshape every file into the legacy canonical export.
See `docs/ITEM_IMPORTS.md`.

- Add-new and update-details templates contain approved item metadata only.
- Starting inventory has a separate five-column template: `SKU`,
  `Starting quantity`, `Warehouse`, `Inventory location`, `Reference note`.
- On hand, Allocated, Sellable/Available, Under Par, On Order, and Storage Volume
  are not valid metadata-import destinations. They are protected, derived, or
  workflow-owned values.
- Source columns are matched through normalized labels and documented aliases;
  users can confirm, change, ignore, and save those mappings.
- Existing item updates match by SKU only. Barcode uniqueness is validated but
  is not an update fallback.
- Blank update cells preserve current values by default. An explicit preview
  option can clear nullable metadata fields.
- Starting inventory is rejected when the item already has stock, allocation,
  or any movement history.
- Override stock levels requires SKU and In stock; Reference note is optional.
  A standard full inventory export may be uploaded without deleting its extra
  columns. Warehouse and Inventory Location are ignored after distinct location
  rows are summed into one exact non-negative total per SKU. Matching totals and
  unknown SKUs are skipped, all matched changes commit atomically, and
  Allocated/Sellable remain system-managed.

Compatibility endpoints `/api/items/import/preview` and
`/api/items/import/commit` still accept the canonical legacy header above. They
remain a migration compatibility surface; the Items UI uses persisted previews
under `/api/items/import/previews`.

## Product Export / Inventory Export

The standard product and inventory export emits the canonical inventory item
CSV columns in the exact order above. A separate editable export mode uses the
Update item details schema so its output can be safely re-imported.

Current implementation: `GET /api/items/export` exports filtered backend rows
using this exact header order. Adding `editable=true` preserves the same filters
but emits only update-safe metadata columns; it never includes stock quantities
or movement fields.

The guided import workspace separately provides an editable current-stock CSV
for audited exact quantity overrides. Keeping metadata and stock outcomes
separate prevents a routine product-detail import from mutating inventory.

Do not include frontend-only/internal fields such as:
- id
- imageUrl
- active
- nonInventory
- wooProductId
- wooVariationId

## Inventory Export by Location

Current implementation: `GET /api/inventory/export/by-location` emits a
warehouse/location-oriented CSV using current item text fields.

Canonical header order:

```csv
Warehouse,Inventory Location,Default Location,SKU,Barcode,Description,Category,Brand,In Stock,Allocated,Sellable,Under Par,On Order,Par Level,Unit Cost,Inventory Value,Weight,Storage Length,Storage Width,Storage Height,Storage Volume,Manufacturer,Manufacturer Website,Client,Unit of Measurement,Recommended Retail Price,Sales Price,Default Econ Order,Default Lead Time Days,Assembly,Serializable,Track Lot,Perishable,Re-Order
```

Calculated export fields:
- Sellable = In Stock - Allocated
- Under Par = In Stock <= Par Level
- Storage Volume = Storage Length x Storage Width x Storage Height
- Inventory Value = In Stock x Unit Cost

Current limitation:
- Warehouse, Inventory Location, and Default Location are flat item text fields
  for this export.
- Item-to-location foreign keys are not globally enforced yet.

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

The location CSV column order is canonical for the Locations module import and
export foundation.

Canonical header order:

```csv
Warehouse,Location Code,Location Name,Description,Zone,Aisle,Rack,Shelf,Bin,Default,Active
```

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| Warehouse | manual | Required | Warehouse name/code. |
| Location Code | manual | Required | Unique within warehouse. |
| Location Name | manual | Required | Display name. |
| Description | manual | Optional | Human-readable location notes. |
| Zone | manual | Optional | Physical zone. |
| Aisle | manual | Optional | Physical aisle. |
| Rack | manual | Optional | Physical rack. |
| Shelf | manual | Optional | Physical shelf. |
| Bin | manual | Optional | Physical bin. |
| Default | manual | Optional | Boolean. Defaults to false when blank. |
| Active | manual | Optional | Boolean. |

Current implementation:
- `GET /api/locations/export` exports filtered backend rows with this exact header.
- `POST /api/locations/import/preview` validates and previews imports without database writes.
- `POST /api/locations/import/commit` creates or updates local location records and stores an import job.
- `docs/csv-reference/sample-locations-import.csv` provides fake sample rows for testing the current format.

Location import matching rules:
- Trim header whitespace, but keep column names case-sensitive.
- Reject files that are missing canonical columns.
- Ignore extra columns and report warnings.
- Match existing locations by exact Warehouse + Location Code.
- Create a new location when no match is found.
- Update the existing location when a match is found.

Location boolean fields:
- Default
- Active

Accepted boolean values:
- true / false
- yes / no
- 1 / 0
- Y / N

Relationship to item fields:
- Item CSV fields `Warehouse`, `Inventory Location`, and `Default Location`
  remain flat strings for now.
- The Locations module provides clean warehouse/location master data for future
  receiving, cycle count, stock-by-location, and export-by-location workflows.
- Foreign keys from item CSV fields to `inventory_locations` are intentionally
  not enforced yet.

## Woo-Mapped Item Enrichment CSV

The separate enrichment export begins with protected columns in this exact
order: `Pongo Item ID`, `Woo Product ID`, `Woo Variation ID`, `Woo Mapping
Type`, and `Woo Mapping Status`.

Editable local columns follow: `SKU`, `Description` (the legacy CSV name for
Product Title), `Category`, `Unit of
Measurement`, `Barcode`, `Brand`, `Manufacturer`, `Manufacturer Website`,
`Recommended Retail Price`, `Sales Price`, `Unit Cost`, `Weight`,
`Warehouse`, `Inventory Location`, `Default Location`, `In Stock`, `On
Order`, `Par Level`, `Default Econ Order`, `Default Lead Time Days`,
`Assembly`, `Serializable`, `Re-Order`, `Storage Length`, `Storage Width`,
`Storage Height`, and `Active`. Expiry is not exported or required.

Rows match by Pongo Item ID, exact Woo product/variation identity, unique SKU,
then unique barcode. Variations require both parent and variation IDs.
Conflicting identifiers reject the row and enrichment never creates an item.
Empty cells preserve values. `__CLEAR__` applies only to approved local optional
metadata and cannot clear mapping identity, SKU, history, writeback identity, or
sync metadata.

`Import opening stock` defaults off, in which case `In Stock` is ignored with
a warning. When enabled, nonnegative stock requires active warehouse/location
records and a safe history-free item. Commit updates
`inventory_item_locations`, writes an `opening_balance_import` movement, and
recalculates cached In Stock and Sellable. Imported Sellable/Under Par are never
trusted, and the same opening-stock file cannot be applied twice.
