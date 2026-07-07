You are Codex working on a new production project called Pongo Inventory OS.

Your job is to build a clean, scalable, standalone inventory and operations system for Pongo Pet Supplies.

Important:
This is NOT a WordPress plugin.
This is NOT a WooCommerce plugin.
This is a standalone web application that will later be deployed on Heroku and connected to WooCommerce through the WooCommerce REST API.

Target stack:
Backend: FastAPI
Database: PostgreSQL
ORM: SQLAlchemy
Migrations: Alembic
Frontend: React
Styling: clean modern admin dashboard UI
Deployment target: Heroku
Integration: WooCommerce REST API
CSV import/export: backend driven
Auth: internal staff login, can start simple for MVP

Core project goal:
Build a lightweight Zenventory replacement customized for Pongo’s actual workflow.

Do not build unnecessary enterprise warehouse features.
Do not build suppliers, purchase orders, supplier quote portals, complex delivery stages, EOQ/ABC forecasting, or generic warehouse bloat unless explicitly requested later.

Core modules needed:
1. Items module
2. WooCommerce product and variation sync
3. Every simple product and every variation becomes its own inventory item
4. Refresh button to pull latest products from WooCommerce
5. Remap button to map local items to WooCommerce products or variations
6. Bulk product import and export
7. Manual product create and edit
8. Locations and stock by location
9. Direct receiving without purchase orders
10. Received inventory report
11. Inventory export
12. Inventory export by location
13. Open orders
14. Allocate orders
15. Pick orders
16. Cycle count
17. Fulfillment export
18. SKU/barcode order report
19. Route creation and route optimization as a separate module

Architecture rules:
1. WooCommerce remains the storefront and customer facing product/order system.
2. Pongo Inventory OS becomes the operational inventory layer.
3. The app should sync WooCommerce data into its own PostgreSQL database.
4. Frontend should read from the local backend/database, not directly from WooCommerce.
5. WooCommerce credentials must never be exposed in frontend code.
6. WooCommerce API credentials must only live in backend environment variables.
7. Every stock changing action must create a stock movement/audit record.
8. Simple WooCommerce products and each WooCommerce variation must be represented as separate inventory items.
9. Barcode scanners should work as keyboard input in SKU/barcode search fields.
10. Build safely. Do not update live WooCommerce stock until read-only sync and local workflows are stable.
11. Prefer small clean commits and focused tasks.
12. Keep docs updated as the project evolves.

Product rule:
Every sellable stock unit is its own inventory item.

A WooCommerce simple product becomes one inventory item.
A WooCommerce variation becomes one inventory item.

Example:
If WooCommerce has a variable product called Dog Food Can with 100g, 200g, and 500g variations, Pongo Inventory OS should show three separate inventory items:
Dog Food Can 100g
Dog Food Can 200g
Dog Food Can 500g

Each item should have its own:
SKU
Barcode
Description
Category
Brand
Manufacturer
Manufacturer Website
Warehouse
Inventory Location
Default Location
In Stock
Allocated
Sellable
Under Par
On Order
Unit Cost
Sales Price
Recommended Retail Price
Weight
Dimensions
Par Level
Reorder settings
Woo Product ID
Woo Variation ID

Important inventory columns:
Client
SKU
Description
Category
Unit of Measurement
Warehouse
Inventory Location
Default Location
In Stock
Allocated
Sellable
Under Par
On Order
Barcode
Manufacturer
Manufacturer Website
Recommended Retail Price
Sales Price
Unit Cost
Weight
Default Econ Order
Default Lead Time Days
Par Level
Assembly
Serializable
Track Lot
Perishable
Re-Order
Storage Length
Storage Width
Storage Height
Storage Volume
Brand
Image URL
Woo Product ID
Woo Variation ID
Active

Calculated fields:
Sellable = In Stock minus Allocated
Under Par = In Stock <= Par Level
Storage Volume = Storage Length × Storage Width × Storage Height
Inventory Value = In Stock × Unit Cost
Unit Cost Total = Quantity × Unit Cost
Total Price = Quantity × Unit Price

Items page requirements:
Build an Admin → Items page inspired by the Zenventory Items page reference.
Do not copy Zenventory branding or assets.
Build functional parity for Pongo’s internal use.

Items page should include:
Search bar
Category filter
Active/inactive filter
Include non inventory checkbox
Reset button
Clear button
Refresh button
Remap button
Export button
Items table
Edit action
Product image column
Row action dropdown

Items table columns:
Image
SKU
Description
Category
UOM
Unit Cost
Sales Price
Recommended Retail Price
Barcode
Brand
Manufacturer
Manufacturer Website
Warehouse
Inventory Location
Default Location
In Stock
Allocated
Sellable
Under Par
On Order
Weight
Active status

WooCommerce sync behavior:
Refresh button should call backend sync.
Backend should fetch simple products, variable products, and variations from WooCommerce.
Each simple product becomes one local inventory item.
Each variation becomes one local inventory item.
Sync should create missing local items and update WooCommerce owned fields.
Sync must preserve Pongo OS owned fields like barcode, manufacturer, manufacturer website, unit cost, warehouse, location, par level, reorder settings, and manual brand override.
Return sync summary:
created_count
updated_count
skipped_count
error_count
errors

Remap behavior:
Allow a local inventory item to be remapped to a WooCommerce product or variation using:
Woo Product ID
Woo Variation ID
SKU
Barcode
Product name

Locations:
The system must support preset warehouse/inventory locations.
A SKU can exist in multiple physical locations.
Use separate tables for item master data and location stock.

Direct receiving without PO:
Pongo does not use purchase orders.
Build direct receiving only.

Workflow:
Scan barcode or enter SKU.
Find item.
Enter quantity received.
Enter unit cost.
Select warehouse.
Select inventory location.
Optional lot number, expiration date, PKG number, item number, pallet number, sales price, weight, and notes.
Submit.
Increase stock for that item and location.
Create receipt and receipt item records.
Create stock movement/audit record.
Queue or perform WooCommerce stock update later only when safe.

Order workflow:
Only build three stages:
Open Orders
Allocate Orders
Pick Orders

Do not build picking started, packed, ready for delivery, out for delivery, delivered, or other complex stages.

Cycle count:
Staff scans barcode or enters SKU.
System shows current stock.
Staff enters counted stock.
System calculates difference.
If difference is not zero, reason is required.
Submit updates stock and creates stock movement/audit record.

Reports required:
1. Inventory Export
2. Inventory Export by Location
3. Received Inventory Report
4. Fulfillment Export
5. SKU/Barcode Order Report
6. CSV exports for all reports

Received Inventory Report columns:
Receipt
SKU
Category
Description
Quantity
UOM
Unit Cost Total
Quantity Base UOM
Lot Number
Expiration Date
PKG Number
Item Number
Pallet Number
Unit Cost
Sales Price
Weight
Brand
Client
Received Date
Warehouse
PO or Receipt Number
Name

Fulfillment Export columns:
CO#
Client
SKU
Ordered Qty
Ordered UOM
Completed On
Unit Cost
Unit Cost Total
Placed On
On Hold
Hold Until
Unit Price
Total Price
Description
Line #
Customer
Shipping Address 1
Shipping Address 2
Shipping Address 3
Shipping City
Shipping State
Shipping Country
Shipping Zip
Shipping Phone
Billing Address 1
Billing Address 2
Billing Address 3
Billing City
Billing State
Billing Country
Billing Zip
Billing Phone
Created By
Brand
Tracking Number
Company

Routes:
Route creation and optimization is a separate module.
It should let staff select orders, create stops from shipping addresses, show stops on a map, optimize stop sequence, and save route.
Do not expose map API keys in frontend.
Use provider abstraction so Google Maps, Google Routes API, Mapbox, or OpenRouteService can be added later.

Development rules:
Do not use real credentials.
Use .env.example files.
Add tests where reasonable.
Keep README updated.
Keep docs updated.
Do not make destructive WooCommerce API calls in early stages.
Prioritize clean architecture over speed.