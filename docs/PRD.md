# Product Requirements Document

## Project Overview

Pongo Inventory OS is a standalone inventory and operations management system for Pongo Pet Supplies. It will replace lightweight operational needs currently associated with Zenventory-style workflows while keeping WooCommerce as the storefront and customer-facing order system.

The system will sync WooCommerce products, variations, and eligible orders into a local PostgreSQL database. Internal staff will use Pongo Inventory OS for item management, stock by location, direct receiving, cycle count, order allocation, picking, reports, and route planning.

## Business Problem

Pongo needs an inventory system that reflects its actual workflow without unnecessary enterprise warehouse complexity. The system must support stock by physical location, direct receiving without purchase orders, barcode/SKU scanning, WooCommerce product mapping, and operational reports.

## Why Replace Zenventory

The goal is to build a lightweight replacement customized for Pongo's workflows rather than adopting generic warehouse features that add friction. Pongo needs control over field ownership, WooCommerce sync rules, reports, and future route workflows.

## Why Standalone

The app must not be a WordPress or WooCommerce plugin. A standalone app keeps operational logic, credentials, and internal workflows separate from the public storefront. WooCommerce REST API credentials will live only in backend environment variables, and the React frontend will never call WooCommerce directly.

## Target Users

- Inventory staff managing products, barcodes, locations, and receiving.
- Order staff allocating and picking WooCommerce orders.
- Managers reviewing reports, cycle counts, and route plans.
- Administrators maintaining mappings and system settings.

## Core Workflows

1. Manage item master data.
2. Refresh WooCommerce simple products and variations into local inventory items.
3. Remap local items to WooCommerce products or variations.
4. Import and export product data.
5. Manage warehouse and inventory locations.
6. Receive stock directly without purchase orders.
7. Run received inventory reports.
8. Perform cycle counts.
9. Sync open WooCommerce orders.
10. Allocate orders from sellable stock.
11. Pick orders by SKU or barcode.
12. Export inventory, fulfillment, and SKU/barcode order reports.
13. Create and optimize delivery routes as a separate module.

## Non-Goals

- Supplier management
- Purchase orders
- Receiving against purchase orders
- Supplier quote portals
- Complex order stages beyond open, allocated, and picked/completed
- EOQ/ABC forecasting
- Generic enterprise warehouse features
- Direct frontend calls to WooCommerce
- Live WooCommerce stock updates before read-only sync and local workflows are stable

## Core Product Rule

Every sellable stock unit is its own inventory item.

A WooCommerce simple product becomes one inventory item. A WooCommerce variation becomes one inventory item. For example, a variable product called "Dog Food Can" with 100g, 200g, and 500g variations becomes three separate Pongo Inventory OS items.

## Items Module

The first major screen is Admin > Items. It should be inspired by Zenventory-style admin inventory tools, but must not copy Zenventory branding, logos, or protected assets.

Items page features:
- Page title: Items
- Tabs: Main, Nutrition, Categories, Customizations
- Main tab real for MVP; other tabs may be placeholders
- Search bar
- Category filter
- Active/inactive filter
- Include Non Inventory checkbox
- Reset and Clear buttons
- Refresh, Remap, and Export buttons
- Items table
- Edit icon/action
- Product image column
- Row action dropdown

Items table columns:
- Image
- SKU
- Description
- Category
- UOM
- Unit Cost
- Sales Price
- Recommended Retail Price
- Barcode
- Brand
- Manufacturer
- Manufacturer Website
- Warehouse
- Inventory Location
- Default Location
- In Stock
- Allocated
- Sellable
- Under Par
- On Order
- Weight
- Active status

## WooCommerce Sync

Refresh calls a backend WooCommerce sync. The backend fetches simple products, variable products, and all variations. Each simple product creates or updates one local inventory item. Each variation creates or updates one local inventory item.

Sync updates WooCommerce-owned fields and preserves Pongo OS-owned fields such as barcode, manufacturer, unit cost, warehouse, location, par level, reorder settings, and manual brand override.

Sync summary should include:
- created_count
- updated_count
- skipped_count
- error_count
- errors

## Remap

Remap allows staff to link or relink a local inventory item to a WooCommerce product or variation using Woo Product ID, Woo Variation ID, SKU, barcode, or product name.

Use cases:
- SKU changed
- Variation mapping broke
- Product was imported manually first
- Duplicate SKU issue
- Product not linked correctly

## Locations

Locations are core. A SKU can exist in multiple physical locations. Use separate concepts:
- `inventory_items`: item master data
- `inventory_locations`: physical location master data
- `inventory_item_locations`: stock split by item and location

Total item stock is calculated from item-location rows:
- In Stock = sum location in_stock
- Allocated = sum location allocated
- Sellable = sum location sellable

## Direct Receiving

Pongo does not use purchase orders. Build direct receiving only.

Workflow:
1. Staff scans barcode or enters SKU.
2. System finds item.
3. Staff enters quantity received and unit cost.
4. Staff selects warehouse and inventory location.
5. Staff may enter lot number, expiration date, PKG number, item number, pallet number, sales price, weight, and notes.
6. Submit increases stock for that item/location.
7. System creates receipt, receipt item rows, and a stock movement/audit row.
8. WooCommerce stock update is queued or performed later only when safe.

Bulk receiving should allow multiple scan/add rows to be submitted as one receipt session.

## Cycle Count

Workflow:
1. Staff scans barcode or enters SKU.
2. System shows item and current stock.
3. Staff enters counted stock.
4. System calculates difference.
5. Reason is required when difference is not zero.
6. Submit updates stock and creates a stock movement/audit row.
7. WooCommerce stock update may happen later only when linked and safe.

## Order Workflow

Only three operational stages are supported:
- Open Orders
- Allocate Orders
- Pick Orders

Open Orders shows eligible WooCommerce orders with order number, customer, placed date, order status, total items, total quantity, allocation status, and allocate action.

Allocate Orders matches order items by Woo product ID, Woo variation ID, SKU, or barcode. It checks sellable stock, increases allocated quantity when available, records allocation, and shows shortages clearly.

Pick Orders lets staff scan barcode or enter SKU, match the item to the order line, increment picked quantity, prevent overpicking, and complete the order when all items are picked.

On completion, the system updates local order status, updates WooCommerce order status to completed through the backend API client, and records fulfillment data.

## Reports

Required reports:
- Inventory Export
- Inventory Export by Location
- Received Inventory Report
- Order Fulfillment Export
- SKU/Barcode Order Report
- CSV exports for all reports

## Routes

Route creation and optimization is a separate module. It should not be mixed into receiving or picking.

Workflow:
1. Staff selects route date.
2. System shows eligible WooCommerce orders with shipping addresses.
3. Staff selects orders.
4. System creates route stops.
5. System shows stops on a map.
6. Staff clicks Optimize Route.
7. System calculates optimized stop sequence.
8. Staff saves route.
9. Export can be added later.

Map provider API keys must live in backend environment variables. Use a provider abstraction so Google Maps, Google Routes API, Mapbox, or OpenRouteService can be added later.

## Safety Requirements

- No real credentials in code, docs, tests, or examples.
- No destructive WooCommerce API calls in early stages.
- Read-only WooCommerce sync first.
- Every stock-changing action creates a stock movement/audit row.
- Manual Pongo OS-owned fields must not be overwritten during refresh.

## MVP Scope

- Documentation and repository foundation
- Backend/frontend scaffold in a later task
- Local item model and Items page
- Read-only WooCommerce product/variation sync
- Refresh/remap
- Import/export
- Location stock
- Direct receiving
- Received inventory report
- Cycle count
- Order sync, allocation, picking
- Core reports

## Later Scope

- WooCommerce stock writeback after safety validation
- Route optimization
- Heroku production deployment
- Advanced staff roles
- Provider integrations for maps/routes
