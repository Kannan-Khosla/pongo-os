# UI Reference

## Current Admin Upgrade

- Phase 1 is a surgical UI polish pass on the existing React/Vite frontend. It
  should preserve current routing, page linking, frontend logic, and backend API
  behavior rather than becoming a full rewrite.
- Frontend design tokens now use Pongo blue `#0f149a` as the primary color and
  soft peach surfaces/accent backgrounds. The old teal/coral look should not be
  extended.
- Shared polish classes cover buttons, tables, forms, filters, and state
  surfaces, including `.btn-*`, `.table-card`, `.table-scroll`, `.data-table`,
  `.form-card`, `.field`, `.input`, `.select`, `.filter-card`, `.action-bar`,
  `.table-empty`, and `.status-pill`.
- Tables must be contained by `.table-scroll`; body-level horizontal overflow
  is a regression.
- Buttons follow primary, muted, action, icon, and disabled states. No fake
  visible buttons: an action must work, navigate to a real page/workflow, or be
  disabled/removed.
- Reports render one selected report panel at a time, with the report selector
  separate from the active report table.
- Scanner uses a warehouse console layout: segmented modes, prominent scan
  input, recent scan panel, and result panel.
- Dashboard is now the Command Center with live local backend data, inventory
  health cards, order operation cards, route cards, data quality warnings,
  recent activity, and quick actions.
- Settings separates WooCommerce operations into Connection, Sync & Mapping,
  and Writeback routes while preserving existing preview/commit safeguards.
- Connection shows the current authorized WooCommerce host. Replacing it
  requires an explicit confirmation when the entered store URL differs, and
  verification must succeed before the host is saved.
- Connection feedback reports only the current check/save request. Historical
  catalog or order sync failures stay in Sync & Mapping and its run history.
- Settings uses document scrolling. Tables may scroll horizontally, but panels
  do not own nested vertical scrollbars; long writeback queues are paginated.
- Orders includes scanner-style Pick Orders controls for SKU/barcode entry.
- Orders now follows a Zenventory-style sidebar sub-navigation pattern instead
  of showing all workflows on one page. The Orders children are Open Orders,
  Allocate, Pick Orders, Completed Orders, and Order History.
- Open Orders owns the queue, filters, table, order detail, and local completion
  actions only. Pick Scanner is only shown in Pick Orders. Allocation, pick, and
  legacy fulfillment/completion history sections are shown in Order History.
- Reports includes SKU Orders Report with summary, filters, table, and CSV
  export.
- Routes includes metadata editing, stop reordering, stop notes/coordinates,
  map payload status, and disabled provider controls for geocode/optimization.

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
- Pongo blue `#0f149a` for primary actions, active navigation, focus states,
  and important headers.
- Soft peach (`#FCE9D9`, `#FFF3EC`, or similar) only as a restrained secondary
  accent or quiet background surface.
- White table-heavy content area.
- Dense operational tables.
- Laptop/desktop-first responsive behavior.
- Barcode scanner input-friendly screens.

Avoid:
- Zenventory logos, mascots, protected assets, or exact visual identity.
- Reintroducing dominant teal/coral styling.
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
- Item Master and Inventory search as the operator types, with live local
  suggestions showing product name, brand/category, SKU, and barcode. Search
  terms are matched independently across item identifiers and metadata; SKU
  prefix matches rank first.
- Grouped table: Warehouse, Inventory Location, Item Count, In Stock, Allocated,
  Sellable, On Order, Inventory Value, Under Par Count.
- Export CSV calls the backend inventory-by-location export.
- Location Stock table lists item-location rows with SKU, description,
  warehouse, location, In Stock, Allocated, and Sellable.
- Inventory now uses sidebar subpages instead of top tabs: All Inventory,
  Inventory by Location, Low Stock, Expiring Stock, Par Level, and Stock
  Movements. Transfer UI is hidden and is not part of the active frontend
  workflow.
- Location inventory rows expose metadata edit, stock adjustment, and movement
  actions. These call backend Pongo OS APIs only and never call WooCommerce.

## Locations

Pongo Locations screen:
- Page title: Locations.
- Tabs: Add Location, All Locations, Location Stock.
- All Locations is real for MVP; Add Location opens the location form. Location
  Stock now maps to the Inventory by Location subpage and local stock
  adjustment operations.
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
- Import and reconcile orders through signed backend `order.created` and
  `order.updated` webhooks, with backend periodic REST reconciliation retained
  for missed deliveries.
- Show active orders whose latest stored WooCommerce status is `processing`.
- Show active order review and completion controls only.
- Do not show route, shipping label, PO, supplier, outbound/customer
  notification, or WooCommerce writeback actions.

Current Pongo Open Orders page:
- Dedicated order-number, customer, containing-item, and warehouse filters.
- The table contains Actions, Order Number, Placed On, Customer, City, Ship Via,
  Order Total, SKU, Ordered, Picked, and row selection.
- Orders render directly in the page flow without a nested table scroller or
  card/modal wrapper. Narrow viewports convert rows to inline order cards.
- The first-column icon menu is portaled above page overflow and contains View
  order, Edit order, Print order, Complete order, Unpick, and View timeline.
  Complete warns when the order has not been fully picked.
- View order opens the accessible printable customer-order detail dialog.
- Safety copy states that Open Orders is for review and completion. Picking
  happens in Pick Orders; completion also marks the linked WooCommerce order
  completed through the backend writeback queue.

Global internal new-order notice:
- Reads the backend webhook event cursor and does not call WooCommerce.
- Uses `initialize=true` to establish the initial cursor without a stale notice,
  then polls globally every 2 seconds while visible.
- Advances through `next_after_id` and drains pages while `has_more=true`; the
  global `latest_event_id` is informational and is not used to skip pages.
- Shows one polite, atomic, dismissible staff notice for later new-order events.
- Provides View Open Orders and Dismiss actions without moving keyboard focus.
- Keeps a session-only header Bell history and unread badge. Opening the history
  marks current alerts read; Escape, Close, and View Open Orders close it.
- Uses a nonzero quick-sync `created_count` as a fallback alert and deduplicates
  repeated results by sync-run identity.
- Replayed/duplicate deliveries do not display another notice.
- This is local staff UI feedback, not email, SMS, browser push, or customer
  notification.

Current Allocation UI:
- Allocate is a processing-order exception workflow for unresolved quantities,
  shortages, unmatched lines, conflicts, unavailable location stock, and
  failed/partial auto-allocation.
- FIFO priority is oldest WooCommerce `date_created` first, then local order ID;
  missing order dates sort last. Partial available stock is reserved before a
  newer order can use it.
- Fully allocated lines are hidden by default and can be included with the
  `Include 100% allocated items in list` checkbox.
- Summary cards show Orders Waiting, Exception Lines, Units Unallocated, Stock
  Available, and Out of Stock. A failed-allocation alert links staff back to the
  shortage workspace.
- Orders and Items tabs present the same unresolved lines by order or aggregated
  item. The Items view shows SKU/barcode, description, affected orders,
  ordered, allocated, unallocated, picked, available, and reason. The Orders
  view adds order number, placed date, and customer.
- Filters support item/order/SKU/barcode, ordered date range, and Ship From.
- The row action menu contains View affected orders, Update stock levels, and
  Allocate available stock. Update Stock Levels creates an audited stock
  adjustment and automatically reruns FIFO allocation.
- Refresh, Export Results, and Run FIFO Allocation are working actions.
- Allocation History remains in Order History.

Current Picking UI:
- Pick Orders lists processing orders only after every required inventory line
  is fully allocated. Partially allocated orders remain in Allocate. The
  scanner appears only after staff selects an order.
- Preview Pick runs a local backend preview for the selected order.
- Preview summary cards: Orders, Lines, Pickable, Partial, Skipped, Qty Pick.
- Preview table columns: Order, SKU, Barcode, Description, Warehouse, Location,
  Ordered, Allocated, Previously Picked, Remaining To Pick, Recommended,
  Picked After, Status, Warnings, Errors.
- Commit Pick posts a local pick, reduces local In Stock and Allocated at the
  allocated item-location rows, creates `pick_stock_reduction` stock movements,
  refreshes Open Orders, Items, Inventory summary, and Pick History.
- Pick History moved to Order History.
- Pick UI does not write WooCommerce, route, create shipping labels, create
  purchase orders, or notify customers.

Current Fulfillment/Completion UI:
- Fulfillment is no longer a primary Orders sidebar page.
- Open Orders exposes Complete and Complete Without Picking actions.
- Completed Orders shows locally closed orders, including picked completions
  and completed-without-picking exceptions.
- Order History shows allocation history, pick history, and legacy
  fulfillment/completion history.
- Legacy fulfillment endpoints remain for compatibility and do not
  double-reduce stock after picking.

Current Settings WooCommerce Order Sync section:
- Shows default REST sync statuses `processing, on-hold, pending`.
- Provides Preview Order Sync and Commit Order Sync controls.
- Preview displays order and line-level match/availability rows.
- Commit creates/updates local order snapshots and attempts safe local
  FIFO auto-allocation for active processing orders. It never writes
  WooCommerce.
- Shows webhook enabled/configured state and the last safe delivery summary, but
  never shows or edits `WOOCOMMERCE_WEBHOOK_SECRET`.
- Explains that created/updated webhooks are the primary order path and backend
  periodic reconciliation covers missed deliveries.

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
- Allocation is exception handling. Active processing orders are auto-allocated
  oldest `date_created` first during order sync and whenever stock becomes
  available through receiving, adjustment, cycle count, or an allocation
  release.
- Available quantities are reserved partially. Only unresolved quantities stay
  in Allocate, and only fully allocated orders enter the default Pick queue.
- Match order items by Woo product ID, Woo variation ID, SKU, or barcode.
- Show shortages clearly.
- Do not build complex allocation rules or delivery stages.
- Every allocation must create allocation records and audit rows. Allocation
  does not reduce In Stock or create stock movement rows.

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
- Only active `processing` orders with all required inventory lines fully
  allocated enter the default pick queue.
- Must support barcode/SKU scan.
- Staff opens an allocated order, scans SKU/barcode, and the system matches to an order line.
- Show ordered, allocated, picked, and remaining quantity.
- Prevent overpicking.
- Current foundation supports backend pick preview/commit and scanner commit
  for selected allocated orders.
- Picking reduces local In Stock and Allocated, recalculates Sellable, creates
  stock movement/audit rows, and tracks Remaining To Pick.
- Completion happens after picking from Open Orders. WooCommerce writeback,
  shipping, and routing remain separate future work.

## Fulfillment / Completion

Pongo Fulfillment:
- Fulfillment is legacy compatibility/history, not the normal stock reduction
  step.
- Complete picked local orders from Open Orders after picking reduces stock.
- Complete unpicked local orders only with explicit confirmation that stock is
  not reduced.
- Show ordered, allocated, picked, stock reduced, fulfilled, and completion
  state.
- Prevent double stock reduction after picking.
- Completion updates only the linked WooCommerce order status to `completed`
  through the audited backend queue; it does not update WooCommerce stock.
- Route planning, shipping labels, outbound/customer notifications, purchase
  orders, and supplier workflows remain separate future phases.

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
- Show WooCommerce integration row with last product sync, last order sync,
  webhook enabled/configured state, last webhook delivery, and error status.
- Do not expose credentials in the frontend.
- Credential editing, if ever needed, should be handled with backend environment variables or secure deployment settings, not plain frontend forms.

Current Pongo Settings > WooCommerce Product Sync:
- Shows configuration status without exposing secret values.
- Shows Base URL, Consumer Key, and Consumer Secret as present/missing only.
- Buttons: Check Connection, Preview Product Sync, Commit Product Sync.
- Safety copy states that sync is read-only against WooCommerce and only
  creates/updates local Pongo OS items.
- Preview summary cards: Total Remote Records, Create, Update, Matched,
  Skipped, Conflicts, Errors.
- Preview table columns: Action, Remote Type, Woo Product ID, Woo Variation ID,
  SKU, Barcode, Description, Category, Brand, Price, Stock Status, Woo Stock
  Snapshot, Local Item ID, Warnings, Errors.
- Sync Run History table shows Started At, Completed At, Sync Type, Status,
  Total Records, Created, Updated, Matched, Skipped, Conflicts, Errors, and
  Created By.
- Commit is disabled when WooCommerce is not configured, preview has not run,
  or preview has conflicts/errors.
- The frontend calls only Pongo backend endpoints and never calls WooCommerce
  directly.

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

Current Fulfillment Report:
- Appears on the Reports page as a read-only section.
- Summary cards show Total Fulfillments, Total Orders, Total Lines, Total
  Quantity Fulfilled, Total Fulfilled Value, Unique SKUs, and Unique Locations.
- Filters: Date From, Date To, Warehouse, Inventory Location, SKU, Barcode,
  Category, Brand, Fulfillment Number, Woo Order Number, Customer Email, Local
  Status, and Created By.
- Actions: Apply Filters, Clear Filters, Refresh, Export CSV.
- Main table shows fulfillment number, posted date, Woo order number, local
  status, customer, warehouse, inventory location, SKU, barcode, description,
  category, brand, quantity fulfilled, unit cost, fulfilled value, stock
  before/after, allocated before/after, and created by.
- Grouped summaries show fulfillment totals by Location and by SKU.
- Completed Orders section on Orders shows fulfilled and partially fulfilled
  local orders with summary cards, filters, and CSV export.
- Report endpoints do not modify inventory, allocated quantities, orders,
  WooCommerce, routes, shipping labels, or customer notifications.

## Routes

No route screenshot was present. Routes use the global Pongo admin shell and
the same dense operational table language as Orders, Reports, and Fulfillment.

Current behavior:
- `Live Planner` and `Completed Routes` are separate route subpages.
- Select the operational open orders being delivered from the default Pongo
  warehouse starting point.
- Choose 1–50 drivers and optionally add a return leg.
- Balance deterministic estimated time or explicitly assign any of ten zones:
  N, S, E, W, NE, NW, SE, SW, Central East, and Central West.
- Never add an unselected zone; show uncovered orders as unassigned.
- Review every driver assignment and every order excluded for a missing
  address.
- Plot all assigned stops in a responsive overview with total driver minutes,
  parallel finish estimate, stop counts, driver colors, and per-stop Google
  Maps navigation. Ungeocoded stops are visibly placed in their direction zone.
- Open or share mobile-safe Google Maps direction links; long routes continue
  in numbered parts.
- Show eligible completed local orders with shipping/customer snapshots.
- Filter candidates by status, customer email, Woo order number, and search.
- Select orders to include as route stops.
- Enter route date, route name, driver, vehicle, and notes.
- Preview selected stops before saving.
- Create a local draft route.
- List route history.
- View route stop detail.
- Export one route CSV.
- Finalize or cancel a local route.

Safety / not yet built:
- Do not expose map provider keys in frontend code.
- Keyless Google Maps URLs are allowed; do not call map, geocoding, or paid
  route-optimization APIs.
- Do not update WooCommerce.
- Do not change local inventory quantities.
- Do not add shipping labels, delivery tracking, or outbound/customer
  notifications.

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

## Current Items Page

Items now has:
- Rich filters for search, SKU, barcode, category, brand, warehouse, location,
  active status, stock status, Woo mapping status, and non-inventory inclusion.
- Image-aware table rows.
- Clickable SKU/description cells that open the Item Detail Control Center.
- Column visibility controls.
- Saved item views.
- Shared bulk selection and audited metadata editing on Item Master, All
  Inventory, Inventory by Location, Low Stock, and Par Level tables. The editor
  supports brands, categories, additive tags, locations, unit costs/prices,
  planning fields, dimensions, and handling flags; unique identifiers and
  stock quantities are not offered.
- Local remap candidate search that does not write WooCommerce.

Item Detail Control Center tabs:
- Overview
- Stock by Location
- Activity
- History
- Edit

Stock quantities are visible in item detail but not directly editable there.
Quantity changes must use receiving, cycle count, or adjustment.

## Current Receiving Page

Receiving now has tabs:
- Direct Receiving
- Bulk Receiving Session
- Receipt History

Bulk Receiving Session includes:
- Large scan/search input.
- Quantity default.
- Warehouse and location selectors.
- Unit cost.
- Optional lot, expiration, pallet, package, item number, sales price, weight,
  and notes fields.
- Multi-row receiving cart.
- Preview and commit actions.
- Receipt number and CSV export after commit.

## Current Scanner Page

Scanner modes:
- Inventory Lookup
- Location Lookup
- Receiving
- Cycle Count
- Picking link/support
- Adjustment

Scanner inputs keep a keyboard-first workflow. No hardware-specific
integration is required. The Scanner Console is optional utility space; the
primary scanner behavior is global search ergonomics. Anywhere staff are in a
SKU/barcode/search filter field, scanning and pressing Enter should run that
page's normal search/apply action.

## Current Expanded Reports

Reports page now includes an Expanded Reports section with:
- Inventory Valuation
- Low Stock / Reorder
- Stock Movement Ledger
- Item Activity
- Location Utilization
- Margin by SKU
- Receiving Cost
- Adjustment / Damage / Loss

Each report provides filters, summary cards, table rows, refresh, CSV export,
empty states, and error states.

## Current Insights Page

Insights is a separate sidebar page titled `Pongo Insights`; it does not replace
the Command Center.

Insights uses:
- horizontally scrollable dashboard tabs;
- compact filters for date, brand, category, SKU, customer, city, and payment;
- white KPI cards on soft peach panels;
- lightweight trend bars instead of a heavy chart dependency;
- table cards with contained horizontal scrolling;
- small data quality warning cards;
- CSV export buttons only on tabs with implemented export endpoints.

Dashboard tabs load on demand and cache loaded responses during the session.

## Current Dashboard And Inventory Overview

`Dashboard` is the default home page and contains the business snapshot:
- KPI cards for today's orders, revenue, new customers, returning customers,
  subscription orders, and AOV.
- Open Orders customer table.
- Upcoming Subscriptions list or a soft missing-data empty state.
- Today's Orders Map with city-level markers and city count cards.
- Revenue comparison bars for current period versus previous month.
- Data quality warnings when local snapshots are incomplete.

`Inventory Overview` is the renamed operational command center. It keeps the
existing inventory health, order operations, route cards, warnings, recent
activity, and quick actions.
