# Build Plan

## MVP Hardening / Admin Upgrade

Status: Completed for Command Center v1, local WooCommerce remap metadata,
scanner-style Pick Orders UX, SKU Orders report, route metadata editing, stop
reordering, local map payload, and disabled provider architecture for geocoding
and optimization. Stock by Location v2, inventory transfers, and stock
adjustments are also completed locally. Frontend polish is in progress with
Pongo blue/peach design tokens, contained table overflow, report single-panel
rendering, scanner console polish, contextual order actions, and
Vitest/Testing Library coverage.

Safety notes:
- No WooCommerce writes.
- No frontend WooCommerce calls.
- No external map/geocoding/routing calls.
- No visible frontend action should be fake: actions must work, navigate to a
  real workflow, or be disabled/removed.
- Dashboard, reports, remap, route metadata, route map, and route provider
  preview/disabled endpoints do not mutate stock, allocation, picked,
  fulfilled, or order status quantities.
- Scanner picking reuses the existing pick commit path and still does not
  reduce In Stock, Allocated, or Sellable.
- `inventory_item_locations` is now the operational source for stock
  quantities; `inventory_items` stock fields are cached aggregates.

## Phase 1: Repository Documentation and Structure

Goal: Establish project rules, documentation, and empty top-level structure.

Deliverables:
- `backend/`, `frontend/`, and `docs/`
- README
- AGENTS rules
- Required documentation set

Acceptance criteria:
- Docs accurately describe scope and safety rules.
- No app code or business logic is implemented.

Safety notes:
- No credentials.
- No WooCommerce connection.

What not to build yet:
- FastAPI scaffold
- React scaffold
- SQLAlchemy models
- Alembic migrations

## Phase 2: Backend and Frontend Scaffold

Goal: Create minimal FastAPI and React app structure.

Status: Completed. Initial frontend shell and backend foundation scaffolded.

Deliverables:
- Backend app entrypoint
- Frontend app shell
- Local development instructions
- Environment example files with placeholders only

Acceptance criteria:
- Health endpoint can run locally.
- Frontend can start locally.

Safety notes:
- No real credentials.

What not to build yet:
- WooCommerce sync
- Stock-changing endpoints

## Phase 3: Database Models and Migrations

Goal: Add SQLAlchemy models and Alembic migrations.

Status: Completed. Initial model set and Alembic revision scaffolded.

Deliverables:
- Models for inventory, locations, movements, receipts, orders, routes, and imports
- Initial migrations

Acceptance criteria:
- Migrations create schema in PostgreSQL.
- Relationships and constraints match docs.

Safety notes:
- No production database changes.

What not to build yet:
- WooCommerce stock writes

## Phase 4: Items Module with Local Data

Goal: Build CRUD and UI for local items.

Status: Completed for backend-persistent local item CRUD/export/import. The Items
module now uses the canonical Zenventory-compatible inventory CSV columns for
frontend display, backend schemas, database persistence, filters, table display,
local edit form, calculated fields, clone behavior, filtered CSV export, and
Zenventory-compatible CSV import preview/commit. WooCommerce sync remains later
work.

Deliverables:
- Items API
- Items page
- Local item create/edit
- Canonical CSV-driven product import/export structure
- Import job tracking and failed row download for item CSV imports

Acceptance criteria:
- Staff can manage Pongo OS-owned fields.
- Items import/export preserves the canonical CSV column order documented in
  `docs/CSV_COLUMNS.md`.
- Item CSV import previews rows before commit and records import errors.

Safety notes:
- No WooCommerce connection yet.
- Current item import is a migration/local item upsert path only; it does not
  run receiving, cycle count, allocation, picking, or WooCommerce stock writes.

What not to build yet:
- Product refresh/remap

## Phase 5: WooCommerce Product and Variation Sync Read-Only

Goal: Pull products and variations into local items.

Status: Completed for read-only product/variation sync foundation. The backend
has a safe WooCommerce client, configuration status endpoint, product sync
preview, local-only commit, sync run history, row-level sync errors, and item
sync metadata. The Settings page exposes WooCommerce Product Sync controls.

Deliverables:
- Backend WooCommerce client
- Read-only sync service
- Sync summary
- Preview endpoint
- Local-only commit endpoint
- Sync run history
- Settings UI

Acceptance criteria:
- Every simple product and variation becomes one item.
- Pongo OS-owned fields are preserved.
- WooCommerce stock is stored only as a snapshot and does not overwrite local
  In Stock.

Safety notes:
- Read-only only.
- Frontend never calls WooCommerce directly.
- No WooCommerce product, order, or stock writes.

What not to build yet:
- WooCommerce stock updates

## Phase 6: Refresh and Remap

Goal: Add staff controls for sync and item mapping.

Deliverables:
- Refresh endpoint/button
- Remap endpoint/UI

Acceptance criteria:
- Staff can recover broken or missing mappings.

Safety notes:
- Validate duplicate SKU behavior before changing mappings.

What not to build yet:
- Order sync

## Phase 7: Bulk Product Import/Export

Goal: Add CSV import/export for product data.

Status: Completed for canonical item CSV import/export. Future enhancements may
add richer import review workflows after real Zenventory files are tested.

Deliverables:
- Product import job tracking
- Import errors
- Inventory export

Acceptance criteria:
- Import errors are visible and traceable.

Safety notes:
- Future operational imports that change stock must create audit rows. The
  current item CSV import is for local item migration/upsert only.

What not to build yet:
- Receiving workflows

## Phase 8: Location Import and Location Management

Goal: Support preset locations and stock by location.

Status: Completed for backend-persistent location master data, filtered
location list, create/edit/deactivate, CSV export, CSV import preview/commit,
import job tracking, failed-row download, and frontend Locations page. Item
stock splits by location remain later work.

Deliverables:
- Location CRUD
- Location CSV import/export
- Item-location stock model foundation

Acceptance criteria:
- Staff can manage warehouse/location master data.
- Location imports match by Warehouse + Location Code and record import errors.
- A SKU can exist in multiple locations once stock workflows are connected.

Safety notes:
- Location stock totals must reconcile with item totals.
- Current location import does not change stock and does not create stock
  movements.

What not to build yet:
- Direct receiving

## Phase 9: Direct Receiving Without PO with Location

Goal: Receive stock directly into locations.

Status: Completed for direct receiving preview/commit, receipt history,
receipt detail, stock movement audit rows, frontend receiving form, and recent
movement table. Receiving requires an active warehouse/location and existing
item match. Purchase orders, suppliers, lot workflows, expiry workflows, cycle
count, allocation, picking, and WooCommerce stock writes remain later work.

Deliverables:
- Receipt creation
- Receipt items
- Stock movements
- Bulk receiving rows

Acceptance criteria:
- Receiving increases location stock and creates audit rows.
- Direct receiving increases item In Stock, leaves Allocated unchanged, and
  recalculates Sellable.
- Direct receiving commits atomically: invalid lines prevent all stock updates.

Safety notes:
- WooCommerce stock update remains disabled or queued.
- Every committed receiving line creates a stock movement row.

What not to build yet:
- Received inventory report

## Phase 10: Received Inventory Report

Goal: Report received inventory.

Status: Completed for direct receiving records. The backend exposes read-only
received inventory JSON, summary, and CSV endpoints, and the frontend Reports
page includes a Received Inventory dashboard with filters, summary cards,
report table, grouped-by-location summary, refresh, and CSV export.

Deliverables:
- Received inventory report endpoint and CSV
- UI filters

Acceptance criteria:
- Receipt numbers appear as the receipt number.
- Report rows come from receipt lines and receipt headers.
- Summary totals and grouped location totals are available.
- CSV export uses the documented received inventory report header order.

Safety notes:
- Report is read-only.
- No WooCommerce calls, purchase orders, supplier workflows, cycle count,
  allocation, picking, route, or fulfillment workflows are added.

What not to build yet:
- Cycle count

## Phase 11: Cycle Count

Goal: Adjust stock through audited counts.

Status: Completed for selected-item and full-location cycle count posting.
The backend supports preview, atomic commit, history, detail, and per-count CSV
export. The frontend Cycle Count page supports scanner-friendly line entry,
preview results, posting, history, detail lines, and export.

Deliverables:
- Count submission
- Reason handling
- Stock movement rows
- Count preview
- Count history/detail/export

Acceptance criteria:
- Line notes are optional in the current MVP.
- Preview does not change stock.
- Commit updates item In Stock to counted quantity.
- Commit leaves Allocated unchanged.
- Commit recalculates Sellable and Under Par.
- Commit creates stock movement rows only for variance lines.
- Invalid counts do not partially commit.

Safety notes:
- WooCommerce stock update remains disabled or explicitly queued.
- No purchase order, supplier, allocation, picking, route, or fulfillment
  workflows are included.

What not to build yet:
- Order sync

## Phase 12: WooCommerce Order Sync

Goal: Pull eligible WooCommerce orders into local tables.

Status: Completed for read-only order sync foundation. The backend supports
WooCommerce order preview, local-only commit, sync run history, open order
list/detail/export endpoints, and line-level matching/availability snapshots.
The frontend Settings page exposes WooCommerce Order Sync controls and the
Orders page shows the local Open Orders queue.

Deliverables:
- Order sync endpoint
- Open orders screen

Acceptance criteria:
- Eligible statuses default to `processing,on-hold` and can be configured.
- Preview writes nothing.
- Commit creates/updates local orders and order lines only.
- Order sync does not allocate, pick, route, fulfill, change local item stock,
  create stock movements, or write WooCommerce.

Safety notes:
- Read-only WooCommerce calls only.
- No fulfillment/status writes until picking is stable and explicitly approved.

What not to build yet:
- Allocation/picking completion writes

## Phase 13: Open, Allocate, Pick Order Workflow

Goal: Support three-stage order workflow.

Status: In progress. Open Orders, Allocation foundation, and Picking foundation
are implemented. Allocation preview and commit reserve local sellable inventory
by increasing item Allocated, leave In Stock unchanged, update local order line
allocation quantities/statuses, and create allocation audit events. Picking
preview and commit record operational progress against allocated quantities by
updating local order line picked quantities and creating pick audit events.

Deliverables:
- Open Orders
- Allocate Orders
- Pick Orders

Acceptance criteria:
- Allocation uses sellable stock.
- Allocation commit is atomic and cannot over-allocate.
- Allocation creates allocation records, allocation lines, and
  `inventory_audit_events`.
- Picking uses already allocated quantities only.
- Picking commit is atomic and cannot overpick allocated or remaining quantity.
- Picking creates pick records, pick lines, and `inventory_audit_events`.
- Open Orders exposes Remaining To Pick and picking status.

Safety notes:
- Allocation is local-only and never writes WooCommerce.
- Allocation does not reduce In Stock and does not create stock movement rows.
- Picking is local-only and never writes WooCommerce.
- Picking does not reduce In Stock, reduce Allocated, or create stock movement
  rows.
- No route, PO, shipping label, customer notification, or supplier workflows are
  included in the open/allocate/pick phase.
- Every allocation/pick movement is audited.

What not to build yet:
- Route optimization

## Phase 14: Fulfillment and SKU/Barcode Reports

Goal: Add order fulfillment exports.

Status: In progress. Fulfillment/completion foundation is implemented for
picked local orders. It previews picked quantities, posts local fulfillment
records, reduces item In Stock and Allocated, recalculates Sellable/Under Par,
updates order line fulfilled quantities, creates stock movement rows, and
creates inventory audit events. Fulfillment does not write WooCommerce or add
route, shipping label, notification, PO, or supplier workflows.
Fulfillment Report and Completed Orders export are implemented as read-only
audit/reporting surfaces.

Deliverables:
- Fulfillment preview/commit
- Fulfillment records and fulfillment lines
- Fulfillment CSV export
- Fulfillment Report JSON/summary/CSV
- Completed Orders JSON/CSV
- SKU/barcode order report

Acceptance criteria:
- Fulfillment commit is atomic and cannot exceed picked, allocated, In Stock,
  or remaining-to-fulfill quantities.
- Fulfillment reduces both In Stock and Allocated.
- Fulfillment creates `fulfill_order` stock movements and `fulfill` audit
  events.
- Fulfillment reports read from fulfillment lines and do not modify inventory.
- Completed Orders export lists fulfilled and partially fulfilled local orders.
- Reports export CSV.

Safety notes:
- Fulfillment is local-only and never writes WooCommerce.
- Fulfillment does not update WooCommerce order status or stock.
- Fulfillment itself does not create routes, shipping labels, notifications,
  purchase orders, or supplier workflows.

What not to build yet:
- Fulfillment-driven route auto-creation
- Shipping labels
- Notifications

## Phase 15: Route Creation

Goal: Create routes from selected orders.

Status: In progress / foundation completed.

Deliverables:
- Route and route stop models: completed
- Route creation migration: completed
- Candidate list from completed local orders: completed
- Route preview and commit endpoints: completed
- Route list/detail/export/finalize/cancel endpoints: completed
- Route creation UI: completed

Acceptance criteria:
- Staff can filter completed local orders and select route stops.
- Staff can preview selected stops before writing a route.
- Staff can save a local draft route from selected order stops.
- Staff can list, view, export, finalize, and cancel local routes.
- Cancelled routes preserve stops and allow the order to be routed again later.

Safety notes:
- No map keys in frontend.
- No external maps, geocoding, routing, or route optimization calls.
- No WooCommerce writes.
- No WooCommerce order status changes.
- No inventory quantity, allocation, sellable, or stock movement changes.

What not to build yet:
- Optimization provider
- Delivery tracking
- Shipping labels
- Customer notifications

## Phase 16: Stock by Location v2, Transfers, and Adjustments

Status: Completed locally.

Deliverables:
- Migration `20260707_0013_stock_by_location_v2_transfers.py`
- Expanded `inventory_item_locations`
- Extended stock movements and workflow line location references
- Inventory transfer and stock adjustment tables
- Central location inventory service
- Item-location, location inventory, transfer, and adjustment APIs
- Location-aware receiving, cycle count, allocation, pick, and fulfillment paths
- Inventory UI location rows plus transfer/adjustment controls

Safety notes:
- No WooCommerce writes.
- No frontend WooCommerce calls.
- Transfers and adjustments are local only.
- Stock-changing operations are transaction-scoped and audited with stock
  movements or audit events.

## Phase 17: Route Optimization

Goal: Add provider-backed route optimization.

Deliverables:
- Provider abstraction
- Optimize endpoint
- Optimized sequence display

Acceptance criteria:
- Provider can be swapped later.

Safety notes:
- API keys only in backend env vars.

What not to build yet:
- Unrequested delivery stages

## Phase 17: Heroku Deployment

Goal: Deploy app to Heroku.

Deliverables:
- Heroku configuration
- PostgreSQL add-on setup
- Environment variable documentation

Acceptance criteria:
- App deploys with no committed secrets.

Safety notes:
- Verify production credentials and permissions before enabling writebacks.

## Phase 18: Items Control Center, Bulk Receiving, Scanners, Reports

Status: Completed locally.

Deliverables:
- Migration `20260707_0014_items_bulk_receiving_scanners_reports.py`
- Saved item views and item notes
- Item detail, activity, history, notes, search, and safe bulk edit endpoints
- Bulk receiving preview/commit workflow
- Scanner endpoints for lookup, receiving, cycle count, transfer, and adjustment
- Expanded read-only reports with summaries and CSV exports
- React Items page control center, bulk receiving session, Scanner page, and
  expanded Reports section
- Dashboard metrics for reorder, damage/loss value, transfers, receiving, and
  adjustments

Safety notes:
- No WooCommerce writes.
- No frontend WooCommerce calls.
- No auth/RBAC.
- No purchase orders or supplier workflows.
- Stock-changing workflows use `inventory_item_locations` as the operational
  quantity source and create stock movements/audit records.
