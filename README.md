# Pongo Inventory OS

Pongo Inventory OS is a standalone internal inventory and operations system for Pongo Pet Supplies. It is the operational inventory layer beside WooCommerce: WooCommerce remains the customer-facing storefront, while Pongo OS manages local item data, stock workflows, fulfillment, reports, and routes.

This is not a WordPress plugin, not a WooCommerce plugin, and not a shortcode app.

## Stack

- Backend: FastAPI
- ORM: SQLAlchemy
- Migrations: Alembic
- Local dev DB: SQLite
- Target production DB: PostgreSQL
- Frontend: React with Vite
- Deployment target: Heroku later
- WooCommerce integration: backend-only WooCommerce REST API

## Current Modules

Implemented locally:
- Command Center dashboard
- Persistent Items
- Zenventory-compatible item CSV import/export
- Locations and inventory by location reporting/export
- Stock by Location v2 with item-location source-of-truth rows
- Direct receiving without purchase orders
- Received inventory report
- Cycle count
- Read-only WooCommerce product/variation sync
- Local WooCommerce remap metadata
- Read-only WooCommerce order sync and open orders
- Allocation
- Scanner-style picking and pick history
- Fulfillment/completion
- Inventory transfers and stock adjustments
- Fulfillment report
- Completed orders export
- SKU Orders report
- Local-only route creation, metadata edit, stop reorder, map payload, disabled geocode/optimization architecture

Not implemented yet:
- Staff auth/login
- Live WooCommerce stock or order-status writeback
- Real map/geocoding/routing provider calls
- Heroku production deployment files
- Supplier management, purchase orders, delivery issue logs, customer notifications, and shipping labels

## Safety Boundaries

- Do not commit credentials, API keys, secrets, or real customer data.
- WooCommerce credentials live only in backend environment variables.
- Frontend code must never call WooCommerce directly.
- WooCommerce sync is read-only unless explicitly approved later.
- WooCommerce stock is stored only as a read-only snapshot.
- Pongo OS local inventory is the operational source of truth.
- Location stock rows are the operational quantity source; item stock fields
  are cached aggregates for compatibility and fast display.
- Stock-changing local workflows must create stock movement or audit rows.
- Route, dashboard, report, remap, and metadata work must not mutate stock quantities.
- Map/geocoding/optimization providers are disabled unless configured backend-side.

## Local Setup

Backend:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
DATABASE_URL=sqlite:///local_items_dev.db .venv/bin/alembic upgrade head
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Local URLs:
- Frontend: http://127.0.0.1:5173
- Backend: http://127.0.0.1:8000
- Health check: http://127.0.0.1:8000/health

## Tests And Builds

Backend tests:

```bash
backend/.venv/bin/pytest backend/tests -q
```

Frontend build:

```bash
cd frontend
npm run build
```

## Environment

Use placeholders only in `.env.example`. Real values belong in local or deployment environment variables.

Route provider placeholders are intentionally disabled by default:

```bash
ROUTE_GEO_PROVIDER=disabled
ROUTE_MAP_PROVIDER=disabled
ROUTE_OPTIMIZATION_PROVIDER=disabled
```
