# Architecture Decisions

## ADR-001: Standalone App Instead of Plugin

Decision: Pongo Inventory OS will be a standalone app, not a WordPress or WooCommerce plugin.

Reason: Operational inventory workflows, credentials, reports, and future routing features should live outside the storefront runtime.

## ADR-002: FastAPI Backend

Decision: Use FastAPI for the backend.

Reason: It is lightweight, typed, testable, and a good fit for API-first inventory workflows.

## ADR-003: PostgreSQL Database

Decision: Use PostgreSQL as the system of record.

Reason: Inventory, orders, receipts, stock movements, and route data need relational integrity and strong querying.

## ADR-004: React Frontend

Decision: Use React for the admin frontend.

Reason: The app needs a standalone operational dashboard with tables, forms, filters, and scanning workflows.

## ADR-005: WooCommerce REST API Integration

Decision: Integrate through WooCommerce REST API from the backend only.

Reason: WooCommerce remains storefront source, while frontend credentials must never be exposed.

## ADR-006: Read-Only WooCommerce Sync First

Decision: Start with read-only product and variation sync.

Reason: Stock writeback should wait until mappings, local workflows, and audit behavior are stable.

## ADR-007: Stock by Location

Decision: Use `inventory_item_locations` as the operational source for
item/location stock splits. `inventory_items` keeps aggregate `in_stock`,
`allocated`, `sellable`, and `on_order` totals for compatibility and fast UI
display.

Reason: A SKU can exist in multiple physical locations, and totals must be derived from those rows.

Update 2026-07-07: Stock by Location v2 is implemented. Receiving, cycle count,
allocation, picking, and fulfillment now resolve item-location rows. Transfers
and explicit adjustments are local-only workflows. WooCommerce writeback remains
disabled.

## ADR-008: Direct Receiving Without PO

Decision: Build direct receiving only.

Reason: Pongo does not use purchase orders.

## ADR-009: Only Three Order Stages

Decision: Support only Open Orders, Allocate Orders, and Pick Orders.

Reason: Pongo does not need complex warehouse/delivery stages in MVP.

## ADR-010: Routes as Separate Module

Decision: Route creation and optimization will be a separate module.

Reason: Routing should not complicate inventory receiving or picking workflows.

## ADR-011: Backend Foundation Before Workflow Logic

Decision: Scaffold FastAPI, SQLAlchemy models, Alembic migrations, environment
configuration, CORS, placeholder routers, and tests before implementing
WooCommerce sync or stock-changing workflows.

Reason: The system needs a stable local backend and database foundation before
adding operations that mutate inventory, allocate orders, receive stock, or call
external services.

Safety: Environment examples contain placeholders only. WooCommerce and map
provider credentials are not committed, and no external WooCommerce or map API
calls are attempted in the scaffold.

## ADR-012: Direct Receiving Is the First Stock-Changing Workflow

Decision: Implement direct receiving without purchase orders as the first
stock-changing workflow.

Reason: Pongo receives inventory directly and needs item stock increases before
cycle count, allocation, picking, or WooCommerce stock writeback are safe.

Safety: Direct receiving validates the full receipt before commit. If any line
is invalid, no item stock is changed. Every successful received line creates a
stock movement/audit row. Unit cost is stored on receipt lines and movements but
does not overwrite item Unit Cost in this phase.

## ADR-013: Received Inventory Report Uses Receipt Lines

Decision: Generate the Received Inventory Report from receipt headers and
receipt item rows, enriching from item and location master data as needed.

Reason: Receipt lines are the operational source of truth for what was received,
while stock movements are the immutable audit trail for stock changes. Reporting
from receipt lines keeps received inventory audit views aligned with receiving
sessions, receipt numbers, reference numbers, line notes, and receipt notes.

Safety: The report endpoints are read-only. They do not modify inventory,
create stock movements, call WooCommerce, or introduce purchase order, supplier,
cycle count, allocation, picking, route, or fulfillment workflows.

## ADR-014: Cycle Count Posts Atomic Stock Adjustments

Decision: Implement Cycle Count as the second stock-changing workflow after
Direct Receiving, with preview and atomic commit endpoints.

Reason: Staff need to compare physical stock with system stock and post audited
adjustments without connecting WooCommerce stock writeback yet. Preview lets
staff review variances before stock changes, while commit revalidates the full
payload and rejects the entire count if any line is invalid.

Safety: Cycle Count updates item In Stock only on posted variance lines, leaves
Allocated unchanged, recalculates derived item fields, creates cycle count
header/line records, and creates stock movement rows only for adjusted lines.
No WooCommerce calls, credentials, external APIs, purchase orders, supplier
workflows, allocation, picking, route, or fulfillment workflows are added.

## ADR-015: WooCommerce Product Sync Is Read-Only Against WooCommerce

Decision: Implement WooCommerce product and variation sync as a backend-only,
read-only integration with preview and local-only commit.

Reason: Pongo needs stable mappings between WooCommerce sellable records and
local inventory items before order sync, allocation, picking, or stock writeback
can be safely introduced. Preview lets staff inspect creates, updates, skips,
and conflicts before any local database changes.

Safety: WooCommerce credentials live only in backend environment variables and
are never exposed in API responses or frontend code. The sync client only
implements read methods. Commit creates or updates local Pongo OS items only,
preserves manual operational fields, stores Woo stock as a snapshot, creates no
stock movements, and never writes WooCommerce products, orders, or stock.

## ADR-016: WooCommerce Order Sync Is Read-Only and Local-Only

Decision: Implement WooCommerce order sync as a backend-only, read-only
integration with preview and local-only commit.

Reason: Pongo needs a local Open Orders queue before allocation, picking,
fulfillment exports, route creation, or WooCommerce status/stock writeback can
be safely designed. Preview lets staff inspect unmatched lines, conflicts, and
shortages before local order snapshots are stored.

Safety: Order sync reads WooCommerce orders only. Preview writes nothing.
Commit creates or updates local `orders` and `order_items` rows only, stores
sync run/error history, and preserves unmatched/conflict lines for review. It
does not create inventory items, allocate, pick, route, fulfill, change local
item stock or Allocated quantities, create stock movements, or write
WooCommerce orders/products/stock.

## ADR-017: Allocation Reserves Local Sellable Inventory Only

Decision: Implement Allocation as a local reservation workflow that increases
item Allocated, leaves item In Stock unchanged, recalculates Sellable, updates
local order line allocation quantities, and creates dedicated allocation audit
events.

Reason: Allocation is not a physical stock movement. It reserves inventory for
orders before picking, so overloading stock movements would blur physical stock
changes with reservation state changes.

Safety: Allocation is atomic and cannot make Allocated exceed In Stock or
allocate more than current Sellable. Allocation creates `allocations`,
`allocation_lines`, and `inventory_audit_events` rows, but it does not create
stock movement rows, reduce In Stock, pick items, create routes, fulfill
orders, change WooCommerce order status, update WooCommerce stock/products, or
call WooCommerce write APIs.

## ADR-018: Picking Tracks Operational Progress Only

Decision: Implement Picking as a local progress workflow against already
allocated order quantities. Picking creates `picks`, `pick_lines`, and
`inventory_audit_events` rows, updates local order line picked quantities, and
updates local order status to `partially_picked` or `picked` when applicable.

Reason: Picking confirms staff have physically gathered allocated items, but it
is not the same as shipping, completion, or inventory reduction. Keeping picking
separate preserves the future ability to review, route, fulfill, and audit
orders before local stock or WooCommerce state changes.

Safety: Picking is atomic and cannot pick more than allocated or more than the
remaining quantity to pick. Picking does not reduce item In Stock, does not
reduce item Allocated, does not recalculate Sellable, does not create stock
movement rows, does not fulfill orders, does not create routes, and does not
write WooCommerce order status, products, or stock.

## ADR-019: Fulfillment Reduces Local In Stock and Allocated

Decision: Implement Fulfillment/Completion as the first order workflow that
removes picked quantities from local physical inventory. Fulfillment reduces
item In Stock and item Allocated by the same fulfilled quantity, recalculates
Sellable and Under Par, updates local order line fulfilled quantities, creates
`fulfillments` and `fulfillment_lines`, creates `fulfill_order` stock movement
rows, and creates `fulfill` inventory audit events.

Reason: Allocation reserves stock and Picking records staff progress, but
neither should imply physical inventory has left the warehouse. Fulfillment is
the local operational boundary where picked goods are completed and should no
longer count as physically on hand or reserved. Reducing In Stock and Allocated
together keeps Sellable stable for already reserved units while accurately
lowering physical inventory.

Safety: Fulfillment is atomic and cannot fulfill more than picked, allocated,
current item In Stock, current item Allocated, or remaining-to-fulfill quantity.
It cannot make In Stock or Allocated negative and cannot leave Allocated greater
than In Stock. Fulfillment does not write WooCommerce order status, products, or
stock, does not create routes, does not create shipping labels, does not send
notifications, and does not add purchase order or supplier workflows.

## ADR-020: Fulfillment Reports Are Read-Only Line Audits

Decision: Build Fulfillment Report and Completed Orders export from local
fulfillment/order data only. The fulfillment report uses `fulfillment_lines` as
the primary source and enriches from fulfillment headers, local orders, order
lines, and items. Completed Orders uses local orders with `fulfilled` or
`partially_fulfilled` status.

Reason: Fulfillment already created the stock-changing audit trail. Reports
should explain what happened without causing any new inventory or WooCommerce
side effects.

Safety: Fulfillment report and completed-order endpoints do not modify item
stock, Allocated, orders, fulfillment records, stock movements, audit events, or
WooCommerce. They do not add route, shipping label, notification, purchase
order, or supplier workflows.

## ADR-021: Route Creation Is Local Manual Planning

Decision: Build route creation as a local planning foundation that uses
completed local orders only. Eligible candidates are local orders with
`fulfilled` or `partially_fulfilled` status and no non-cancelled route. Route
preview validates selected orders without writes. Commit creates a `draft`
route and route-stop snapshots, then list/detail/export/finalize/cancel operate
on local route records.

Reason: Pongo needs a route planning surface after local fulfillment, but map
provider selection, route optimization, labels, dispatch, delivery tracking,
notifications, and WooCommerce status writeback are separate higher-risk
workflows.

Safety: Route creation does not call WooCommerce, maps, geocoding, routing,
shipping label, notification, purchase order, supplier, or inventory stock
services. It does not change local item In Stock, Allocated, Sellable, On Order,
order status, stock movements, or audit rows. Cancelled routes retain stops for
review while making their orders eligible for future route planning.

## ADR-022: Command Center Is Read-Only Local Operations Data

Decision: Build the dashboard as a read-only Command Center over local records:
items, orders, routes, stock movements, audit events, receipts, cycle counts,
allocations, picks, fulfillments, sync errors, and import jobs.

Reason: Managers need one operational page for health, warnings, and recent
activity without triggering business workflows.

Safety: Dashboard endpoints do not mutate inventory, orders, routes,
WooCommerce, stock movements, or audit rows.

## ADR-023: Remap Is Local Metadata Only

Decision: Build WooCommerce remap as local metadata using `woo_item_mappings`
plus local item Woo ID metadata. Remap preview and commit never call
WooCommerce.

Reason: Staff need a way to recover broken product/variation links while
preserving the backend-only WooCommerce boundary and Pongo OS field ownership.

Safety: Remap does not update WooCommerce, stock, allocation, sellable, picked,
fulfilled, route, or order status quantities. Manual item fields are preserved.

## ADR-024: Route Providers Default To Disabled

Decision: Add route map/geocode/optimization architecture as local endpoints
with disabled/no-op provider behavior by default.

Reason: The UI can now support metadata, stop ordering, coordinate review, and
future provider integration without committing to Google, Mapbox, or another
paid routing provider.

Safety: No provider keys are exposed in frontend responses. No external
geocoding, maps, routing, optimization, WooCommerce, notification, label, or
delivery tracking calls are made by the current implementation.

## ADR-025: Item Control Center Uses Local Activity Composition

Decision: Build item detail as a local control center assembled from existing
records: item rows, `inventory_item_locations`, stock movements, receipts,
cycle counts, transfers, adjustments, allocations, picks, fulfillments, local
orders, and item notes.

Reason: Operators need one place to inspect item state without duplicating
activity into a new event stream.

Safety: Item detail and activity endpoints are read-only except item notes and
metadata-only edit paths. Stock fields must still be changed through receiving,
cycle count, transfer, or adjustment workflows.

## ADR-026: Bulk Receiving Is One Local Receipt Session

Decision: Bulk receiving preview validates all rows without writes. Commit
creates one local receipt and one receipt item per valid row, updates
`inventory_item_locations`, recalculates aggregate item stock fields, and
creates stock movements.

Reason: Warehouse receiving needs fast multi-row scanner/cart entry while
preserving stock auditability.

Safety: No WooCommerce calls or writeback. Invalid rows block commit by
default. Stock is changed only through the location inventory service.

## ADR-027: Scanner Workflows Are Keyboard-Input Local Operations

Decision: Treat barcode scanners as keyboard input and expose local scanner
endpoints for inventory lookup, location lookup, receiving, cycle count,
transfer, and adjustment. Picking continues to use the existing order scanner.

Reason: Pongo can support warehouse devices without hardware-specific
integration or browser plugins.

Safety: Scanner commits are local only. Cycle count requires a reason when the
count differs from system quantity. Transfer and adjustment checks prevent
negative location stock.

## ADR-028: Expanded Reports Are Read-Only

Decision: Build inventory valuation, low stock/reorder, stock movement ledger,
item activity, location utilization, margin by SKU, receiving cost, and
adjustment/damage/loss reports from local tables only.

Reason: Reporting should explain operational data without changing stock,
orders, WooCommerce, or route state.

Safety: All expanded report endpoints are read-only and include CSV export
only.

## ADR-029: Pongo Frontend Design System

Decision: Use centralized CSS variables for Pongo blue `#0f149a`, blue hover
and active states, soft peach backgrounds, white/off-white surfaces, borders,
text colors, and status colors. Primary buttons use Pongo blue; secondary and
action buttons use consistent muted/outline controls.

Reason: The app must feel like a polished standalone Pongo operations system,
not a Zenventory clone or rough scaffold.

Safety: Tables must scroll inside `.table-scroll`; the page/body must not
overflow horizontally. Visible action controls must work, navigate to a real
workflow, or be disabled/removed. Frontend tests run with Vitest and Testing
Library through `npm test -- --run`.
