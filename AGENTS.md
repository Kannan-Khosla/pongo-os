# Pongo Inventory OS Instructions

You are working on Pongo Inventory OS, a standalone inventory and operations system for Pongo Pet Supplies.

This is not a WordPress plugin and not a WooCommerce plugin. Build it as a standalone web application.

Target stack:
- Backend: FastAPI
- Database: PostgreSQL
- ORM: SQLAlchemy
- Migrations: Alembic
- Frontend: React
- Deployment target: Heroku
- Integration: WooCommerce REST API

Core rules:
- WooCommerce remains the storefront and customer-facing product/order system.
- Pongo Inventory OS is the operational inventory layer.
- Frontend must never call WooCommerce directly.
- WooCommerce API keys must only live in backend environment variables.
- Do not use real credentials in code.
- Every stock-changing action must create a stock movement/audit record.
- Every simple WooCommerce product becomes one inventory item.
- Every WooCommerce variation becomes its own inventory item.
- Barcode scanners should work as keyboard input in SKU/barcode search fields.
- Do not make destructive WooCommerce API calls in early stages.
- Keep the code clean, modular, tested, and documented.

Core modules:
- Items
- WooCommerce product and variation sync
- Refresh and remap
- Bulk import/export
- Manual product create/edit
- Locations and stock by location
- Direct receiving without PO
- Received inventory report
- Cycle count
- Open orders, allocate orders, pick orders
- Fulfillment export
- SKU/barcode order report
- Route creation and route optimization

Do not build unnecessary modules unless requested:
- Supplier management
- Purchase orders
- Supplier quote portals
- Complex delivery stages
- EOQ/ABC forecasting
- Generic warehouse bloat

Always update docs when architecture, models, API routes, or business rules change.