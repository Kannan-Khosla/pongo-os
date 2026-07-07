# Pongo Inventory OS

Pongo Inventory OS is a standalone inventory and operations management system for Pongo Pet Supplies.

It is intended to become a lightweight Zenventory replacement tailored to Pongo's real workflow: item management, WooCommerce product and variation sync, locations, direct receiving, cycle count, order allocation/picking, reports, and route planning.

## Why This Exists

Pongo needs an operational inventory layer that is separate from the storefront. WooCommerce should remain the customer-facing product and order system, while Pongo Inventory OS manages internal inventory operations in its own PostgreSQL database.

## Standalone Architecture

This project is not a WordPress plugin, not a WooCommerce plugin, and not a shortcode app inside WordPress. It will be a standalone full-stack application that integrates with WooCommerce through the WooCommerce REST API.

The frontend must read from the local backend/database. It must never call WooCommerce directly.

## Target Stack

- Backend: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Frontend: React
- Deployment target: Heroku
- External integration: WooCommerce REST API
- CSV import/export: backend-driven
- Auth: internal staff login, starting simple for MVP

## Main Modules

- Items
- WooCommerce product and variation sync
- Refresh and remap
- Bulk product import/export
- Manual product create/edit
- Locations and stock by location
- Direct receiving without purchase orders
- Received inventory report
- Inventory export and inventory export by location
- Open orders, allocate orders, and pick orders
- Cycle count
- Fulfillment export
- SKU/barcode order report
- Route creation and route optimization

## Safety Rules

- No credentials should be committed.
- WooCommerce credentials must only live in backend environment variables.
- Frontend code must never call WooCommerce directly.
- Every stock-changing action must create a stock movement/audit row.
- Do not update live WooCommerce stock until read-only sync and local workflows are stable.
- Every WooCommerce simple product and every WooCommerce variation becomes its own inventory item.

## Build Phases

This repository starts with documentation and structure only. The detailed phased plan lives in [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md).

## Local Development Status

The frontend admin shell is scaffolded in `frontend/` as a Vite React app.
It currently contains placeholder screens only and does not connect to the backend,
WooCommerce, or live inventory logic.

```bash
cd frontend
npm install
npm run dev
```

The backend foundation is scaffolded in `backend/` as a FastAPI app with
SQLAlchemy models, Alembic migration setup, PostgreSQL configuration, placeholder
API routers, and tests. It does not connect to WooCommerce and does not implement
stock-changing workflows yet.

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Run backend tests:

```bash
cd backend
.venv/bin/python -m pytest
```

Run the initial Alembic migration against a local PostgreSQL database after
creating `pongo_inventory_os` and configuring `backend/.env`:

```bash
cd backend
.venv/bin/alembic upgrade head
```

The current backend route implementations are intentionally structural only.
WooCommerce sync, receiving, allocation, picking, route optimization, and real
stock-changing business logic will be added in later tasks.
