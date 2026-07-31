# 08: Information Architecture

The redesign reorganizes navigation without removing any current capability. Every current destination maps to a proposed home below; nothing is unmapped.

## 1. Current navigation map (as shipped)

Flat sidebar, 13 items: Dashboard, Inventory Overview, Items, Inventory (6 subviews), Locations, Receiving, Scanner, Orders (5 subviews), Cycle Count, Reports, Routes, Insights, Settings (renders the WooCommerce workspace). Plus header bell notifications and hidden routes (items new/detail/categories/commodities, locations new/stock/detail).

## 2. Proposed navigation map

Sidebar with grouped eyebrows (collapsible to icon rail; overlay drawer on mobile):

```
COMMAND
  Command Center            (merges Dashboard + Inventory Overview as Business and Operations bands)
COMMERCE
  Orders                    (Open, Allocation, Completed, History as page tabs)
  Picking                   (promoted from Orders subview: floor workspace)
  Routes
WAREHOUSE
  Inventory                 (All, By Location, Low Stock, Expiring, Par Levels, Movements as page tabs)
  Catalog                   (renamed Items: item master, mapping, enrichment)
  Locations
  Receiving
  Cycle Count
  Scan                      (scanner console, also reachable from every page via the command bar)
INTELLIGENCE
  Insights                  (grouped report nav replaces 13 flat tabs)
  Reports
SYSTEM
  Integrations              (the current "Settings" WooCommerce workspace, honestly named)
  Settings                  (future company, users, warehouses, system; placeholder marked as roadmap)
```

Top bar: breadcrumb (module / page / record), global command search (Cmd+K, scan-aware: a scanned barcode from anywhere resolves to item or order), sync status chip, notifications bell, warehouse workspace switcher.

## 3. Current-to-proposed page mapping

Format: Current destination | Current purpose | Proposed destination | Group | Screen pattern | Reason.

| Current | Purpose | Proposed | Group | Pattern | Reason |
|---|---|---|---|---|---|
| `#dashboard` | business snapshot | Command Center, Business band | Command | KPI band + cards + chart | one front door; business and ops together |
| `#inventory-overview` | ops health | Command Center, Operations band | Command | pipeline bar + alerts + activity | removes dual-dashboard confusion |
| `#items` | item master | Catalog | Warehouse | toolbar + data grid + drawer | "Catalog" matches commerce platform language |
| `#/items/new` | create item | Catalog, New item | Warehouse | form workspace | unchanged flow |
| `#/items/:id` | edit item | Catalog, item drawer (full page for deep edit) | Warehouse | drawer over grid | keeps list context |
| `#/items/categories`, `#/items/commodities` | reserved | Catalog, Taxonomy (roadmap chip) | Warehouse | roadmap placeholder | honest future-state labeling |
| `#/inventory/all` | stock overview | Inventory, All tab | Warehouse | summary band + grid | same data, tabbed views |
| `#/inventory/by-location` | per-location stock | Inventory, By Location tab | Warehouse | location index + split detail | spatial grouping made visible |
| `#/inventory/low-stock` | under par | Inventory, Low Stock tab | Warehouse | risk queue | severity-ranked |
| `#/inventory/expiring` | expiry view | Inventory, Expiring tab | Warehouse | roadmap-aware empty state | capability marker kept |
| `#/inventory/par-level` | reorder thresholds | Inventory, Par Levels tab | Warehouse | grid + side sheet | inline par editing |
| `#/inventory/movements` | audit ledger | Inventory, Movements tab | Warehouse | ledger table | immutable-ledger styling |
| `#locations` | location master | Locations | Warehouse | grid + hierarchy path | unchanged scope |
| `#/locations/new`, `#/locations/:id` | create or edit | Locations drawer | Warehouse | drawer form with live path preview | keeps list context |
| `#/locations/stock` | reserved stock view | Inventory, By Location tab | Warehouse | redirect mapping | duplicates an existing capability |
| `#receiving` | direct and bulk receiving | Receiving | Warehouse | 3-step session flow + history rail | honest steps replace fake tabs |
| `#scanner` | scan workflows | Scan | Warehouse | scan console (segmented modes) | promoted, floor-first |
| `#/orders/open` | open queue | Orders, Open tab | Commerce | toolbar + grid + order drawer | same columns and actions |
| `#/orders/allocate` | allocation exceptions | Orders, Allocation tab | Commerce | exception resolution queue | same commit verbs |
| `#/orders/pick` | pick queue and entry | Picking (module) | Commerce | queue cards + floor pick flow | floor work deserves top-level access |
| `#/orders/completed` | completed list | Orders, Completed tab | Commerce | grid with saved date presets | unchanged scope |
| `#/orders/history` | three audit ledgers | Orders, History tab | Commerce | unified event ledger with type filter | same three record families |
| `#cycle-count` | count and reconcile | Cycle Count | Warehouse | count session + variance review | same preview and commit |
| `#reports` | operational reports | Reports | Intelligence | report library + canvas | same reports and exports |
| `#routes` | route planning | Routes | Commerce | stop list + map placeholder split | spatial work gets spatial layout |
| `#insights` | 13 BI views | Insights | Intelligence | grouped subnav (Revenue, Customers, Products, Subscriptions, Payments, Geography, Forecasts) + chart-first panels | 13 flat tabs collapse into 7 groups; every dataset keeps its own view and export rules |
| `#settings` (Woo workspace) | sync, mapping, writeback | Integrations, WooCommerce | System | connection card + sync tiles + queue + runs | honest naming; audit-grade treatment |
| (declared, unbuilt) Settings tabs Company, Users, Warehouses, System | reserved | Settings | System | roadmap placeholders | preserves the declared intent without faking it |
| Header bell and toast | live order events | unchanged, restyled Notification Center | shell | toast + popover | identical logic and copy |

## 4. Page-level navigation rules

- Module tabs are real links (hash routes) rendered as underline tabs; static labels are eliminated everywhere.
- Records open in right drawers by default with "Open full page" escape; drawer state is URL-addressable (`#/orders/open?order=701`) so deep links and refresh restore context.
- Back behavior: hash history preserves scroll and filter state; breadcrumb always offers the parent.
- Badges: live counts on Orders (open), Picking (ready), Integrations (queue pending); cleared by visiting.

## 5. Global search and command behavior

One surface, three behaviors: type to filter destinations and actions; type an identifier (order number, SKU, barcode) to jump to the record; scan from anywhere (burst-input detection) to resolve item or order and open its drawer. Recent scans and recent records listed when empty. Keyboard: Cmd+K or / focuses; Escape returns focus to the page.

## 6. Detail-view behavior

Drawer anatomy: identity header (mono id, status pill, health dot), key facts grid, primary content (lines, stock, stops), timeline, sticky footer with the single next action per state (Open → Allocate; Allocated → Send to Picking; Ready → Start Pick; Picked → Complete; Exception → Resolve). Power actions stay in an overflow menu, matching current kebab contents.

## 7. Mobile navigation

Under 768px: top bar keeps menu button (opens navigation overlay with the full grouped sidebar), breadcrumb collapses to page title, search becomes an icon expanding full-width. Operational flows (Picking, Scan, Receiving) present as full-screen step flows with sticky bottom action bars. Bottom tab bar is intentionally not used: the module count exceeds 5 and the primary mobile context is tablet floor work, where the overlay drawer plus in-flow actions perform better.

## 8. Meaningful layout shifts, explained

1. One Command Center instead of two dashboards: removes the first navigation decision users currently face.
2. Picking promoted to a module: the highest-frequency floor task no longer hides as the third subview of Orders.
3. Settings renamed Integrations: the page is a WooCommerce operations workspace; naming it honestly restores trust; a real Settings area is reserved for the declared Company, Users, Warehouses, System content.
4. Insights grouped: 13 tabs become 7 domain groups with identical datasets, removing horizontal tab overflow.
5. Items renamed Catalog: aligns with the commerce-platform vocabulary used by Woo mapping and enrichment flows.
6. Scanner reachable globally: scan is a system capability (command bar), not only a page.
