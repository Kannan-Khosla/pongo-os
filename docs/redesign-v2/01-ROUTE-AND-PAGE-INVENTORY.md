# Route and page inventory

## Scope and state notation

The current hash parser exposes **29 route patterns**, including two dynamic detail patterns. Most data pages implement loading, empty, error, and success states locally; the matrix calls out exceptions. `TableShell` generally contains wide tables with horizontal scrolling, but the fixed 280 px application sidebar has no responsive replacement.

| State | Meaning in the current frontend |
| --- | --- |
| L | Loading strip or pending button state |
| E | Empty table row, empty panel, or placeholder page |
| R | API/validation error surface |
| S | Success strip, summary, or toast |
| C | Confirmation before stock, mapping, route, pick, or completion mutations |

## Route matrix

| Current destination | Component | Purpose and data | Primary / secondary actions | Search, filters, tables, forms | States | Current UX concern → v2 opportunity |
| --- | --- | --- | --- | --- | --- | --- |
| `#dashboard` | `BusinessDashboardPage` | Daily orders, revenue, customers, subscriptions, city geography, data quality | Refresh / inspect business cards | Six KPIs; open-order table; subscription list; approximate map; revenue bars | L/E/R | Competes with Inventory Overview and buries urgency → one Command Center with role-aware lanes |
| `#inventory-overview` | `CommandCenterPage` | Inventory health, order operations, routes, warnings, activity | Refresh / quick links to workflows | 20 metric cards; warning and activity tables | L/E/R | Large undifferentiated metric field → exception-first operational overview |
| `#insights` | `InsightsPage` | 13 BI views covering revenue, customers, products, subscriptions, forecasts, geography, affinity | Refresh; export supported tabs | Date, brand, category, SKU, customer, city, payment filters; summary, trend and table | L/E/R | 13 horizontally scrolling tabs and universal filter form → domain subnav + contextual filters |
| `#items` | `ItemsList` | Item master, Woo mappings, saved views, bulk edit | Import mappings; refresh; remap; bulk edit; import/export | SKU/barcode/title search; category, brand, stock, status; configurable table | L/E/R/S | Eight peer actions and nested controls → command bar with one primary action and overflow |
| `#/items/new` | `ItemDetail` | Create a manual item | Save / return | Multi-section canonical item form | R/S | Long form with little progress/context → section index and sticky save summary |
| `#/items/categories` | `StandardPage` | Reserved taxonomy destination | None | Placeholder table | E | Looks implemented but is not → label as unavailable or remove until supported |
| `#/items/commodities` | `StandardPage` | Reserved taxonomy destination | None | Placeholder table | E | Same as categories → explicit future-state treatment |
| `#/items/:id` | `ItemDetail` | Edit item metadata | Save; clone; return | Identity, stock-adjacent metadata, dimensions and flags | R/S | Dedicated route duplicates item drawer treatment → shared detail workspace pattern |
| `#inventory`, `#/inventory/all` | `InventoryPage` + `AllInventoryTable` | Consolidated stock across items and locations | Update changed stock; update all; row edit/stock/location/movements/orders | Scanner-style search; category and brand; 11-column table | L/E/R/S/C | High-risk sync buttons dominate every inventory view → safety action in scoped utility area |
| `#/inventory/by-location` | `InventoryByLocationView` | Stock grouped by warehouse/location with value | Row edit, adjust, movements | Shared search/filters; group summaries and 10-column tables | L/E/R/S | Repeats a full table per location → location index + selected-location split view |
| `#/inventory/low-stock` | `LowStockTable` | Under-par items and reorder suggestions | Edit; adjust stock; movements | Shared search/filters; 11 columns | L/E/R/S | Exception severity is text/numbers only → ranked risk, days-left and guided resolution |
| `#/inventory/expiring` | `ExpiringStockView` | Future lot-expiry view | None | Empty state only | E | Route is present without data workflow → honest capability marker |
| `#/inventory/par-level` | `ParLevelTable` | Reorder thresholds and suggested quantities | Edit product; par; stock; movements | Shared search/filters; 12 columns; par modal | L/E/R/S | Threshold editing detached from demand context → inline side sheet with forecast context |
| `#/inventory/movements` | `InventoryMovementsView` | Audited stock ledger | Filter; export; view item | Movement type, warehouse, location, dates; 14 columns | L/E/R | Audit trail is visually identical to operational tables → immutable-ledger styling and event detail |
| `#locations` | `LocationsList` | Physical location master | Add; clear; import; export | Search, warehouse, zone, aisle, status; 12 columns | L/E/R | Dense master data with disabled pagination → hierarchy/tree + selected location summary |
| `#/locations/new` | `LocationDetail` | Create physical location | Save / return | Identity, physical position, default/active | R/S | Form lacks hierarchy preview → live path preview (`Warehouse / Zone / Aisle / Bin`) |
| `#/locations/stock` | `StandardPage` | Reserved location-stock destination | None | Placeholder table | E | Duplicates real Inventory by Location intent → map to that existing capability |
| `#/locations/:id` | `LocationDetail` | Edit physical location | Save / return | Same as new | R/S | No inventory context → location summary and linked stock view |
| `#receiving` | `DirectReceivingPage`, `BulkReceivingSession` | Direct and bulk receipt sessions plus receipt and movement history | Preview; commit; reset; refresh history | Warehouse/reference/notes; scan rows; location, qty, unit cost; optional lot fields | L/E/R/S/C | Three workflows share one long page and histories appear below entry → session workspace + history side rail |
| `#scanner` | `ScannerWorkflowsPage` | Inventory/location lookup, receiving, cycle count, adjustment | Scan; preview; commit | Mode segments; scan input; location/quantity/reason forms; raw response details | E/R/S | Scanner feedback competes with forms; raw JSON leaks implementation shape → full-screen scan state with clear result cues |
| `#orders`, `#/orders/open` | `OrdersPage` + `OpenOrdersTable` | Processing order queue and detail | Import; export; refresh; bulk complete/print/unpick; row actions | Order/customer/item/warehouse filters; pagination; 10-column table; detail dialog | L/E/R/S/C | Zenventory-specific visual dialect breaks shell consistency → Pongo queue table + contextual detail drawer |
| `#/orders/allocate` | `AllocationExceptionsPage` | Unresolved FIFO allocation shortages by items or orders | Refresh; export; run FIFO; adjust stock | Search, dates, warehouse, fully-allocated toggle; item/order tabs | L/E/R/S/C | Strong workflow but multiple panels compete → exception queue with resolution side sheet |
| `#/orders/pick` | `PickOrdersWorkspace` | Select pick-ready orders and enter picked quantities | Search; pick/unpick selected; mark all; confirm pick | Queue table; dedicated line workspace | L/E/R/S/C | Manual quantity entry is safe but lacks scan feedback requested by operational users → scan-first focus with manual fallback |
| `#/orders/completed` | `CompletedOrdersPanel` | Read-only completed/closed orders | Refresh; export | Status/date/customer/order/SKU/barcode/search filters; summary and 15 columns | L/E/R | Filter burden is high for a historical view → saved date presets and progressive filters |
| `#/orders/history` | Allocation/Pick/Fulfillment history panels | Read-only audit of three record families | Clear details; select record; export | Three history tables plus detail panels | E/R | Three vertical master-detail sections create a very long page → single event ledger with type filter |
| `#cycle-count` | `CycleCountPage` | Preview and post physical counts; inspect history | Add line; preview; post; reset; refresh/export history | Warehouse/location/type/notes; scan/count table; detail panel | L/E/R/S/C | Entry, preview, history and detail compete vertically → guided count session with persistent variance summary |
| `#reports` | `ReportsPage`, report panels | Received inventory, fulfilment, SKU orders, valuation, low stock, ledger, activity, utilization, margin, receiving cost, adjustments | Select report; apply/clear; refresh; export | Report-specific filters, summaries and tables | L/E/R | Report selector and high-density forms dominate → report library + contextual parameter drawer |
| `#routes` | `RoutesPage` | Select completed-order candidates; preview/create/manage local routes | Refresh; preview; create; finalize/cancel; edit metadata/stops; export | Candidate and history filters; route form; tables; route detail | L/E/R/S/C | Creation, history and selected route all stack on one page → three-pane planner with explicit provider-disabled state |
| `#settings` | `WooCommerceSettingsPage` | Catalog/order sync, safeguards, writeback queue, remap, sync history | Check; preview/commit sync; queue/approve/send/cancel; remap | Multiple summaries, forms and five tables | L/E/R/S/C | “Settings” is really one very long integration console → settings index + dedicated Woo integration workspace |

## Modal, drawer, and subview inventory

- Item control: `ItemDetailDrawer` with Overview, Stock by Location, Activity, History, and Metadata; `BulkEditModal`; `ImportModal`; `ImportMappingsModal`; `LocalRemapSearchModal`.
- Inventory: `ProductInfoModal`, `StockAdjustmentModal`, `ParLevelModal`.
- Orders: `OpenOrderDetailPanel`, `OrderActionsMenu`, bulk print sheet, allocation stock modal, pick detail workspace.
- Locations: location import modal and import preview.
- Operational detail: cycle-count detail, route detail, allocation/pick/fulfilment detail panels.
- Notifications: new-order toast region and notification-history popover.

## Shared state behavior

- Loading is usually a full-width text strip rather than a skeleton; button-level loading is inconsistent.
- Empty tables are consistently verbalized, a current strength. Only some empty states provide a next action.
- Errors are usually page-level strips and do not consistently identify the field or recovery action.
- Successful mutations use strips; new orders also use a live toast and history popover.
- Confirmation relies on native `window.confirm`, preserving safety but losing contextual detail and consistent styling.
- Responsive adaptation exists for Open Orders and selected workflows, but the global sidebar remains fixed-width and many tables only scroll.
