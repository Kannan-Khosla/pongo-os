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

Decision: Use `inventory_item_locations` for item/location stock splits.

Reason: A SKU can exist in multiple physical locations, and totals must be derived from those rows.

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
