# CSV Columns

Column source values:
- WooCommerce: synced from WooCommerce.
- Pongo OS: owned by Pongo Inventory OS.
- calculated: derived by the system.
- manual: entered by staff.
- future: planned but not required in first implementation.

## Inventory Export

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| Client | Pongo OS | Optional | Tenant/client label. |
| SKU | WooCommerce/Pongo OS | Required | Primary item lookup when present. |
| Description | WooCommerce/Pongo OS | Required | Product or variation name/description. |
| Category | WooCommerce | Optional | Synced category. |
| Unit of Measurement | Pongo OS | Optional | Manual default. |
| Warehouse | Pongo OS | Optional | Default warehouse. |
| In Stock | calculated | Required | Sum of location stock. |
| Allocated | calculated | Required | Sum of allocated stock. |
| Sellable | calculated | Required | In Stock minus Allocated. |
| Under Par | calculated | Required | In Stock <= Par Level. |
| On Order | Pongo OS | Optional | Future/manual. |
| Barcode | Pongo OS | Optional | Scanner-friendly lookup. |
| Manufacturer Website | Pongo OS | Optional | Manual field. |
| Recommended Retail Price | Pongo OS | Optional | Manual field. |
| Sales Price | WooCommerce/Pongo OS | Optional | Woo regular/sale price or manual. |
| Unit Cost | Pongo OS | Optional | Manual or receiving-derived. |
| Weight | WooCommerce/Pongo OS | Optional | Synced when available. |
| Default Econ Order | Pongo OS | Optional | Manual reorder setting. |
| Default Lead Time Days | Pongo OS | Optional | Manual reorder setting. |
| Par Level | Pongo OS | Optional | Manual reorder setting. |
| Assembly | Pongo OS | Optional | Boolean. |
| Serializable | Pongo OS | Optional | Boolean. |
| Track Lot | Pongo OS | Optional | Boolean. |
| Perishable | Pongo OS | Optional | Boolean. |
| Re-Order | Pongo OS | Optional | Boolean. |
| Storage Length | WooCommerce/Pongo OS | Optional | Synced dimensions or manual. |
| Storage Width | WooCommerce/Pongo OS | Optional | Synced dimensions or manual. |
| Storage Height | WooCommerce/Pongo OS | Optional | Synced dimensions or manual. |
| Storage Volume | calculated | Optional | Length * Width * Height. |
| Brand | WooCommerce/Pongo OS | Optional | Woo taxonomy/meta or manual override. |

## Inventory Export by Location

Same as Inventory Export, plus:

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| Inventory Location | Pongo OS | Required | Physical location code/name. |
| Default Location | Pongo OS | Optional | Indicates default item location. |

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

## Product Import

| Column | Source | Required | Notes |
| --- | --- | --- | --- |
| SKU | manual | Required | Used to create or update item. |
| Barcode | manual | Optional | Scanner lookup. |
| Description | manual | Required | Item description. |
| Category | manual | Optional | Category. |
| Brand | manual | Optional | Manual brand override. |
| Manufacturer | manual | Optional | Manufacturer name. |
| Manufacturer Website | manual | Optional | URL. |
| Unit Cost | manual | Optional | Cost. |
| Sales Price | manual | Optional | Price. |
| Recommended Retail Price | manual | Optional | RRP. |
| Weight | manual | Optional | Weight. |
| Storage Length | manual | Optional | Dimension. |
| Storage Width | manual | Optional | Dimension. |
| Storage Height | manual | Optional | Dimension. |
| Par Level | manual | Optional | Reorder setting. |
| Woo Product ID | manual | Optional | For remap/import. |
| Woo Variation ID | manual | Optional | For variation remap/import. |
| Active | manual | Optional | Boolean. |

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
