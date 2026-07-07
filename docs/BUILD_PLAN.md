# Build Plan

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

Deliverables:
- Items API
- Items page
- Local item create/edit

Acceptance criteria:
- Staff can manage Pongo OS-owned fields.

Safety notes:
- No WooCommerce connection yet.

What not to build yet:
- Product refresh/remap

## Phase 5: WooCommerce Product and Variation Sync Read-Only

Goal: Pull products and variations into local items.

Deliverables:
- Backend WooCommerce client
- Read-only sync service
- Sync summary

Acceptance criteria:
- Every simple product and variation becomes one item.
- Pongo OS-owned fields are preserved.

Safety notes:
- Read-only only.

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

Deliverables:
- Product import job tracking
- Import errors
- Inventory export

Acceptance criteria:
- Import errors are visible and traceable.

Safety notes:
- Imports that change stock must create audit rows.

What not to build yet:
- Receiving workflows

## Phase 8: Location Import and Location Management

Goal: Support preset locations and stock by location.

Deliverables:
- Location CRUD
- Location CSV import/export
- Item-location stock model

Acceptance criteria:
- A SKU can exist in multiple locations.

Safety notes:
- Location stock totals must reconcile with item totals.

What not to build yet:
- Direct receiving

## Phase 9: Direct Receiving Without PO with Location

Goal: Receive stock directly into locations.

Deliverables:
- Receipt creation
- Receipt items
- Stock movements
- Bulk receiving rows

Acceptance criteria:
- Receiving increases location stock and creates audit rows.

Safety notes:
- WooCommerce stock update remains disabled or queued.

What not to build yet:
- Received inventory report

## Phase 10: Received Inventory Report

Goal: Report received inventory.

Deliverables:
- Received inventory report endpoint and CSV
- UI filters

Acceptance criteria:
- Receipt numbers appear as PO or Receipt Number.

Safety notes:
- Report is read-only.

What not to build yet:
- Cycle count

## Phase 11: Cycle Count

Goal: Adjust stock through audited counts.

Deliverables:
- Count submission
- Reason handling
- Stock movement rows

Acceptance criteria:
- Non-zero differences require reason.

Safety notes:
- WooCommerce stock update remains disabled or explicitly queued.

What not to build yet:
- Order sync

## Phase 12: WooCommerce Order Sync

Goal: Pull eligible WooCommerce orders into local tables.

Deliverables:
- Order sync endpoint
- Open orders screen

Acceptance criteria:
- Eligible statuses are configurable after confirmation.

Safety notes:
- No fulfillment/status writes until picking is stable.

What not to build yet:
- Allocation/picking completion writes

## Phase 13: Open, Allocate, Pick Order Workflow

Goal: Support three-stage order workflow.

Deliverables:
- Open Orders
- Allocate Orders
- Pick Orders

Acceptance criteria:
- Allocation uses sellable stock.
- Picking prevents overpicking.

Safety notes:
- Every allocation/pick movement is audited.

What not to build yet:
- Route optimization

## Phase 14: Fulfillment and SKU/Barcode Reports

Goal: Add order fulfillment exports.

Deliverables:
- Fulfillment export
- SKU/barcode order report

Acceptance criteria:
- Reports export CSV.

Safety notes:
- Reports are read-only.

What not to build yet:
- Routes

## Phase 15: Route Creation

Goal: Create routes from selected orders.

Deliverables:
- Route and route stop models
- Route creation UI

Acceptance criteria:
- Staff can save selected order stops.

Safety notes:
- No map keys in frontend.

What not to build yet:
- Optimization provider

## Phase 16: Route Optimization

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
