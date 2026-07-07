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
