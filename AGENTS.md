# Pongo Inventory OS Instructions

Pongo Inventory OS is a standalone inventory and operations system for Pongo Pet Supplies.

## Project Boundaries

- This is not a WordPress plugin.
- This is not a WooCommerce plugin.
- This is not a shortcode app inside WordPress.
- Build it as a standalone full-stack application that can later be deployed to Heroku.
- WooCommerce remains the storefront and customer-facing product/order system.
- Pongo Inventory OS is the operational inventory layer.

## Target Stack

- Backend: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Frontend: React
- Deployment target: Heroku
- External integration: WooCommerce REST API
- CSV import/export: backend-driven
- Auth: internal staff login, simple MVP auth is acceptable

## Safety Rules

- Do not commit credentials, API keys, secrets, or real customer data.
- WooCommerce credentials must only live in backend environment variables.
- Frontend code must never call WooCommerce directly.
- Do not expose WooCommerce or map provider credentials in frontend code.
- Do not make destructive WooCommerce API calls in early stages.
- Do not update live WooCommerce stock until read-only sync and local workflows are stable.
- Every stock-changing action must create a stock movement/audit row.
- Keep documentation updated whenever architecture, models, API routes, workflows, or business rules change.

## Core Inventory Rules

- Every sellable stock unit is its own inventory item.
- Every WooCommerce simple product becomes one inventory item.
- Every WooCommerce variation becomes one inventory item.
- Manual Pongo OS-owned fields must not be overwritten by WooCommerce refresh.
- Barcode scanners should behave as keyboard input in SKU/barcode fields.

## Build Focus

Build a lightweight Zenventory replacement customized for Pongo's workflow.

Core modules:
- Items
- WooCommerce product and variation sync
- Refresh and remap
- Bulk product import/export
- Manual product create/edit
- Locations and stock by location
- Direct receiving without purchase orders
- Received inventory report
- Cycle count
- Open orders, allocate orders, and pick orders
- Fulfillment export
- SKU/barcode order report
- Route creation and route optimization as a separate module

Do not build unless explicitly requested later:
- Supplier management
- Purchase orders
- Supplier quote portals
- Complex delivery stages
- EOQ/ABC forecasting
- Generic enterprise warehouse features
