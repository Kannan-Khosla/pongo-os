# UI Reference

This document describes UI style, screens, and workflows for Pongo Inventory OS.
It is the visual reference for frontend work, not a source of business logic.
The current React admin shell implements the global layout and placeholder
pages only; real inventory data and workflow behavior are added in later phases.

Screenshots inspected from `docs/ui-reference/pongo-os/`:
- `items-page.png`
- `indvidual-item.png`
- `list-inventory.png`
- `list-all-inventory.png`
- `receicving-without-po-screen1.png`
- `cycle-count.png`
- `oprn-orders.png`
- `allocate-orders.png`
- `pick-orders.png`
- `customer_order_search.png`
- `systems-settings.png`
- `woo-commerce0integration.png`

The screenshots show Zenventory workflows and visual patterns. Use them only as layout and workflow inspiration. Do not copy Zenventory branding, logo, exact assets, or protected visual identity.

## Global Layout

The reference uses a desktop-first, table-heavy admin layout:
- Dark left sidebar with large icon navigation and expandable sections.
- Coral/orange top header for warehouse context, user controls, alerts, and overflow actions.
- White main content area.
- Dark teal secondary tab bars.
- Dark teal table action/header bands.
- Light grey filter areas and table header rows.
- Material-style controls: raised buttons, circular icon buttons, dropdowns, filter icons, radio buttons, toggles, checkboxes, pagination arrows, and table action menus.
- Wide operational tables with horizontal scroll when needed.
- Repeated pattern of page title, filters/actions, result count, pagination, table, and row actions.

Pongo Inventory OS should keep this operational density but apply Pongo branding rather than Zenventory branding.

## Pongo UI Style Decision

Use:
- Pongo branding.
- Clean internal admin dashboard style.
- Dark teal sidebar.
- Coral/orange primary action color.
- White table-heavy content area.
- Dense operational tables.
- Laptop/desktop-first responsive behavior.
- Barcode scanner input-friendly screens.

Avoid:
- Zenventory logos, mascots, protected assets, or exact visual identity.
- Marketing-page composition.
- Supplier, purchasing, purchase order, or complex warehouse modules unless requested later.

## Reference Sidebar Structure

The reference sidebar shows:
- Dashboard
- Purchasing
- Receiving
- Inventory
- Orders
- Quick Issue
- Reports
- Admin
- Help

Expanded reference subsections include items such as Receive With PO, Receive Without PO, Warehouse Transfer, Put Items Away, Cycle Count, Open Orders, Allocate, Pick, Ready to Ship, Ship, Dispatched, Returns, Company, Items, Suppliers, Customers, Users, Warehouses, System, and Billing.

## Pongo Sidebar Structure to Build

Use only Pongo's needed modules:
- Dashboard
- Items
- Inventory
- Locations
- Receiving
- Orders
- Cycle Count
- Reports
- Routes
- Settings

Do not build supplier management, purchasing, purchase orders, supplier portals, ready-to-ship/ship/dispatched/returns stages, or complex order stages unless requested later.

## Dashboard

Reference dashboard screenshot was not present in the inspected folder, but the target dashboard should follow the same admin layout.

Planned elements:
- Summary cards for core operational totals.
- Dashboard chart area.
- Widget area for work queues or exceptions.
- Announcement/card area.

Pongo MVP:
- Dashboard may be placeholder until inventory and order data exists.
- Placeholder should still use the global shell, sidebar, coral header, and white content area.
- Current shell shows summary cards for Orders, Items, Low Stock, and Received
  Today, plus a placeholder activity chart and operations widgets panel.

## Admin Items

Reference: `items-page.png`.

This is the closest reference for the Pongo Items module.

Reference structure:
- Top tabs: New Item, All Items, Categories, Commodities.
- Search field.
- Category filter.
- Active/inactive radio buttons.
- Include Non-Inventory checkbox.
- Import and Export actions in the upper right.
- Search and Clear buttons.
- Result count and pagination.
- Dark teal table action band with Actions dropdown.
- Grey table header row.
- Items table with edit icon, image, SKU, description, category, UOM, unit cost, sales price, recommended retail price, and row checkbox/actions.

Pongo Items screen:
- Page title: Items.
- Tabs: New Item, All Items, Categories, Commodities.
- All Items is real for MVP; New Item opens the item form. Categories and
  Commodities may remain placeholders.
- Items must be driven by the canonical Zenventory-compatible CSV columns in
  `docs/CSV_COLUMNS.md`.
- Search should support SKU, barcode, description, category, brand,
  manufacturer, warehouse, and inventory location.
- Filters: search, category, warehouse, inventory location, brand,
  active/inactive, include non-inventory.
- Actions: Refresh, Remap, Import, Export, Clear.
- Refresh triggers backend WooCommerce sync later.
- Remap links local items to WooCommerce products or variations later.
- Import opens a CSV modal that previews and commits the canonical
  Zenventory-compatible item CSV through the Pongo backend only.

Pongo Items table columns:
- Edit action
- Image
- Client
- SKU
- Description
- Category
- Unit of Measurement
- Warehouse
- Inventory Location
- Default Location
- In Stock
- Allocated
- Sellable
- Under Par
- On Order
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
- Active status

## Item Details

Reference: `indvidual-item.png`.

Reference structure:
- Top tabs: Basic, Units, Warehouse, Supplier, Variants, Integration Mappings, Timeline.
- Basic form laid out in columns.
- Left column fields: SKU, barcode, description, manufacturer website, category, base UOM, default unit cost, sales price, recommended retail price, safety stock, weight.
- Large image upload area with Add Image button.
- Checkbox stack: kit, assembly, non-inventory, serializable, perishable, track lot, active.
- Notes field.
- Footer actions: Save Changes, Clone, Return to Items.

Pongo Item Details:
- Build Basic tab first using all canonical CSV fields.
- Tabs: Basic, Units, Warehouse, Variants, Integration Mappings, and Timeline.
  Non-Basic tabs may remain placeholders.
- Do not build Supplier tab unless supplier management is explicitly requested later.
- Include Woo Product ID and Woo Variation ID in Integration Mappings when that placeholder becomes real.
- Pongo-owned fields must remain editable even after WooCommerce refresh.
- WooCommerce-owned fields should be visually distinguished or read-only where appropriate once sync exists.

## Inventory List

References: `list-inventory.png`, `list-all-inventory.png`.

Reference structure:
- Top tab bar: In Stock, All Inventory, Location View, Supplier View, Low Stock, Expiring Stock, Par Level, Kits, Assembly, Warehouses.
- Filters: category, warehouse, brand, search.
- Actions: Import, Export Report, Export Results.
- Search and Reset buttons.
- Result count and pagination.
- Inventory table with image, SKU, category, description, UOM, in stock, allocated, sellable, par level, unit cost, actions, and row checkboxes.
- Circular row icon actions and product image placeholders.

Pongo Inventory tabs:
- List Inventory
- All Inventory
- Location View
- Low Stock
- Expiring Stock
- Par Level

Do not build Supplier View, Kits, or Assembly unless requested later.

Pongo Inventory columns:
- Image
- SKU
- Category
- Description
- UOM
- In Stock
- Allocated
- Sellable
- Par Level
- Unit Cost
- Warehouse
- Inventory Location when in location view
- Actions

Current Pongo Inventory page:
- Shows summary cards for Total Items, Total In Stock, Total Sellable, Total
  Inventory Value, and Under Par Items.
- Filters: warehouse, inventory location, default location, category, brand,
  and under-par status.
- Grouped table: Warehouse, Inventory Location, Item Count, In Stock, Allocated,
  Sellable, On Order, Inventory Value, Under Par Count.
- Export CSV calls the backend inventory-by-location export.

## Locations

Pongo Locations screen:
- Page title: Locations.
- Tabs: Add Location, All Locations, Location Stock.
- All Locations is real for MVP; Add Location opens the location form. Location
  Stock remains a placeholder until stock-by-location workflows are built.
- Filters: search, warehouse, zone, aisle, active/inactive.
- Actions: Add Location, Import, Export, Clear.
- Import opens a CSV modal that previews and commits the canonical location CSV
  through the Pongo backend only.

Pongo Locations table columns:
- Edit action
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

Pongo Location Details:
- Required fields: Warehouse, Location Code, Location Name.
- Optional fields: Description, Zone, Aisle, Rack, Shelf, Bin.
- Status toggles: Default and Active.
- If a location is marked Default, the backend keeps only one default in the
  same warehouse.

## Receiving Without PO

Reference: `receicving-without-po-screen1.png`.

For Pongo, this becomes Direct Receiving without PO.

Reference structure:
- Page title: New Delivery.
- Stepper: Create Receipt, Select Items, Accept Delivery.
- Add New Item SKU/barcode input.
- Search icon.
- Green plus add button.
- One-to-one scanning toggle.
- Receiving item table.
- Next button.
- Delivered and total summaries.

Reference receiving table columns:
- Image
- SKU
- Vendor Code
- PKG #
- Item #
- Unit Cost
- UOM
- Expires
- Lot No
- Delivered Qty
- Pallet #
- Destination/location
- Total

Pongo Direct Receiving:
- Page title can be New Delivery or Receive Stock.
- Search/add input must be scanner-friendly and focused by default when practical.
- Staff scans barcode or enters SKU.
- Staff enters quantity received, unit cost, warehouse, inventory location, and optional receipt details.
- Destination should map to Pongo inventory location.
- Submit must eventually create receipt, receipt item rows, location stock updates, and stock movement/audit rows.
- Do not add purchase order receiving.

Current Pongo Direct Receiving page:
- Header fields: Warehouse, Reference Number, Notes.
- Line fields: SKU/barcode scanner input, readonly description, inventory
  location, quantity received, unit cost, notes, remove line.
- Buttons: Add Line, Preview Receiving, Commit Receiving, Reset Form.
- Preview shows line status, previous stock, new stock, total quantity, and
  estimated value without writing data.
- Commit posts the full receipt only when all lines are valid.
- Receipt History table shows posted direct receiving sessions.
- Recent Stock Movements table shows the audit trail.

## Cycle Count

Reference: `cycle-count.png`.

Reference structure:
- Tabs: Overview, New Cycle Count.
- Left panel titled Choose Location(s) for Cycle Count.
- Search for item/location.
- Location tree/list with folder icons and expandable rows.
- Selected Locations panel.
- Save button.
- Cycle Count Location History table.
- History columns: Location Name, Items, Total Value, Last Completed Count.
- Plus icon row actions.

Pongo Cycle Count:
- Must support scan/search by SKU or barcode.
- Must support location-based counting.
- Staff selects location, scans/searches item, sees current stock, enters counted stock, and sees difference.
- Submit must eventually create stock movement/audit row.

Current Pongo Cycle Count page:
- Header fields: Warehouse, Inventory Location, Count Type, Notes.
- Count Type options: Selected Items and Full Location.
- Inventory Location is optional for selected item counts and required by the
  backend for full location counts.
- Line fields: SKU/barcode scanner input, readonly description, system
  quantity, counted quantity, notes, remove line.
- Buttons: Add Line, Preview Count, Post Count, Reset Form.
- Preview calls the backend and shows total lines, adjustment lines, positive
  variance, negative variance, absolute variance, variance value, and per-line
  system/count/variance details without writing data.
- Post Count is disabled when preview has invalid lines.
- Successful posting updates local item stock through the backend, creates
  cycle count lines, and creates stock movement/audit rows only for non-zero
  variance lines.
- Cycle Count History shows count number, status, warehouse, inventory
  location, count type, total lines, adjustment lines, created/posted dates, and
  created by.
- Clicking a count number loads a basic detail panel with counted lines.
- Export CSV is available from history and detail.
- Line notes are optional in the current MVP.
- WooCommerce stock updates, purchase orders, supplier workflows, allocation,
  picking, route, and fulfillment workflows are not included.

## Open Orders

Reference: `oprn-orders.png`.

Reference structure:
- Page title: Open Customer Orders.
- Filters: order number, customer, containing item, ship from.
- Actions: Import, Export, Refresh.
- Search and Clear buttons.
- Result count and pagination.
- Orders table with filter band and Actions dropdown.

Reference table columns:
- Order Number
- Alerts
- Tags
- Order Source
- Placed On
- Account Number
- Company
- Customer
- City
- State
- Zip
- Ship Via
- Ship From
- Order Total
- SKU

Pongo Open Orders:
- Order source is WooCommerce.
- Pull eligible WooCommerce orders later through backend sync.
- Show order number, customer, placed on, WooCommerce status, total items, total quantity, allocation status, ship from, city/state/zip, order total, SKU summary, and action to allocate.

## Allocate Orders

Reference: `allocate-orders.png`.

Reference structure:
- Filters: item, order source, ordered date start/end, ship from.
- Include 100% allocated items checkbox.
- Export Results action.
- Tabs: Orders and Items.
- Pagination and Actions dropdown.

Reference Items table columns:
- SKU
- Description
- Client
- Ordered
- Allocated
- Unallocated
- Picked
- Available

Pongo Allocate Orders:
- Allocation only needs to check sellable stock and allocate when available.
- Match order items by Woo product ID, Woo variation ID, SKU, or barcode.
- Show shortages clearly.
- Do not build complex allocation rules or delivery stages.
- Every allocation must eventually create audit/stock movement records.

## Pick Orders

Reference: `pick-orders.png`.

Reference structure:
- Page title: Order Picking.
- Filters: order number and containing item.
- Options: only show fully allocated, include part allocated, include unallocated items on pick list.
- Print options: both printed and not printed, only printed, only not printed.
- Search button.
- Result count and pagination.
- Table with play/start icon row action.

Reference table columns:
- Order Number
- Alerts
- Tags
- Order Source
- Placed On
- Company
- Customer
- City
- State
- Ship Via
- Order Total
- SKU
- Ordered
- Picked
- Allocated
- Location

Pongo Pick Orders:
- Must support barcode/SKU scan.
- Staff opens an allocated order, scans SKU/barcode, and the system matches to an order line.
- Show ordered, allocated, picked, and remaining quantity.
- Prevent overpicking.
- Complete order when all items are picked.
- Completion can later update WooCommerce order status through backend API.

## Order Search

Reference: `customer_order_search.png`.

Reference structure:
- Advanced search form with many fields such as order number, customer, order reference, ship from, ship-to name/company, tracking number, created/shipped dates, containing item, expiration date, serial number, lot number, account number, project number, created by, and internal note.
- Export Results action.
- Only Open Customer Orders checkbox.
- Dark teal filter/table action band below the search form.

Pongo:
- Build later as order search/reporting, not MVP critical.
- Keep search fields focused on WooCommerce order number, customer, SKU/barcode/containing item, date range, order status, and location/ship-from.

## System Settings

Reference: `systems-settings.png`.

Reference structure:
- Top settings tabs: Basic Settings, Units, Integrations, Import Data, Automation Rules, Templates, Shipping, My Lists, Tags, Communication, Lexicon, Warehouses Assignments, Work Queue.
- Dense settings layout with text fields, dropdowns, radio buttons, and toggles.
- Toggle-heavy operational configuration.

Pongo:
- Only basic settings are needed later.
- Do not build broad warehouse/order/purchasing settings until they are needed.
- Settings should eventually include safe configuration for WooCommerce sync status, feature flags, and operational defaults.

## Integrations

Reference: `woo-commerce0integration.png`.

Reference structure:
- Page title: Manage Integration Engines.
- Tab grouping such as Marketplace, Amazon, Shipping, Accounting, Zapier, WTS.
- Integration table row for WooCommerce.
- Columns: Integration Engine, Warehouse, Initialized, Last Processed, Enabled.
- Add Marketplace button.
- Row expansion/action affordance.

Pongo:
- Build a Settings > Integrations page later for WooCommerce connection status.
- Show WooCommerce integration row with last product sync, last order sync, enabled/disabled, and error status.
- Do not expose credentials in the frontend.
- Credential editing, if ever needed, should be handled with backend environment variables or secure deployment settings, not plain frontend forms.

## Reports

Reports should follow the table-heavy pattern:
- Filter area at top.
- Export Results / Export Report actions.
- Result count and pagination.
- CSV-first output.

Required Pongo reports:
- Inventory Export
- Inventory Export by Location
- Received Inventory Report
- Order Fulfillment Export
- SKU/Barcode Order Report

Current Pongo Reports page:
- The first report tab is Received Inventory.
- Summary cards show Total Receipts, Total Lines, Total Quantity Received,
  Total Received Value, Unique SKUs, and Unique Locations.
- Filters: Date From, Date To, Warehouse, Inventory Location, SKU, Barcode,
  Category, Brand, Receipt Number, Reference Number, and Created By.
- Actions: Apply Filters, Clear Filters, Refresh, Export CSV.
- Main table columns: Receipt Number, Received At, Warehouse, Inventory
  Location, SKU, Barcode, Description, Category, Brand, Quantity Received, Unit
  Cost, Total Received Value, Reference Number, and Created By.
- Grouped summary shows Warehouse, Inventory Location, Total Lines, Total
  Quantity Received, and Total Received Value.
- The report is read-only and currently reflects direct receiving records only
  because purchase order receiving is not built.

## Routes

No route screenshot was present. Routes should still use the global shell.

Planned behavior:
- Select route date.
- Show eligible WooCommerce orders with shipping addresses.
- Select orders to include.
- Create route stops.
- Show stops on map.
- Optimize stop sequence through backend provider abstraction.
- Save route.

Do not expose map provider keys in frontend code.

## Frontend Build Priority

When frontend implementation begins, build in this order:
1. Global layout and sidebar
2. Items page
3. Item detail page
4. Inventory list
5. Receiving without PO
6. Cycle count
7. Open orders
8. Allocate orders
9. Pick orders
10. Reports
11. Routes

## Implementation Guardrails

- Do not build the frontend from this task.
- Do not scaffold React from this task.
- Do not implement business logic from this task.
- Use screenshots as workflow/layout references only.
- Keep Pongo Inventory OS standalone and Pongo-branded.
- Keep scanner-facing workflows fast, focused, and keyboard-friendly.
