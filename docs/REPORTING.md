# Verified Reporting

Pongo OS reporting is read-only. Generating, downloading, publishing, or
emailing a report never changes inventory, orders, receipts, fulfillments, or
WooCommerce.

## Report runs

Every generation creates an immutable `report_runs` snapshot containing:

- the report key and calculation-definition version
- normalized filters and the `America/Edmonton` reporting timezone
- columns, rows, KPIs, chart data, findings, calculation definitions, and
  data-quality disclosures
- generation time, generating actor, row count, and a SHA-256 evidence hash

CSV, PDF, Google Sheets, and email attachments are generated from that stored
snapshot. They do not rerun the database query, so every format for a run has
the same rows and evidence hash. Running the same report again creates a new
run ID; identical inputs and source data produce the same evidence hash.

This supports reconciliation and bookkeeping, but does not replace accountant
review or source-document retention.

## Implemented catalog

- Current Cost of Inventory by Category
- Current Cost of Inventory by SKU
- Inventory in Stock
- Inventory Usage Summary
- Unallocated Order Items
- Delivered Inventory
- Received Inventory
- Inventory Export
- Inventory Forecast
- Incomplete Orders
- Order Summary
- Daily Item Orders
- Detailed Customer Orders
- Executive Weekly Report
- Reorder Intelligence
- PO Received
- Sales by SKU

Each report returns its own calculation definitions and explicit disclosures.
Missing cost, incomplete history, unavailable delivery timestamps, unallocated
refund detail, and similar limitations are disclosed instead of being silently
treated as zero.

## External delivery

Google Sheets publishing and SMTP email are backend-only integrations.
Credentials never enter the frontend and are never returned by an API.

Google Sheets requires an OAuth client and refresh token with Sheets and Drive
access. A report creates a spreadsheet with `Report` and `Audit` tabs. Optional
email addresses receive Google Drive writer permissions.

Email delivery can attach CSV and PDF versions and include a previously-created
Google Sheet URL. Each attempt creates a `report_deliveries` audit row.

Required environment variables are documented in `backend/.env.example`.

## Accounting boundaries

- Currency calculations use `Decimal`, not binary floating point.
- Inventory value is current physical stock multiplied by current unit cost.
- Missing unit cost produces a null value and disclosure, never a fabricated
  zero-cost valuation.
- WooCommerce sales include only processing and completed snapshots; manual
  sales include processing, completed, and fulfilled orders. Shipping and tax
  are excluded.
- Partial refund summaries that cannot be allocated safely to a SKU are shown
  as a disclosure.
- Received and delivered costs use the unit cost frozen on the receipt or
  fulfillment line. Historical lines without a frozen cost remain null and
  disclosed; current item cost is never substituted.
- Delivered Inventory uses fulfillment posting time because a carrier-confirmed
  delivery timestamp is not stored.
- PO Received uses receipt reference fields; Pongo OS does not currently have a
  purchase-order ledger.
- Forecast version 1 is recent successful-order velocity, not a promise of
  future demand. Insufficient history remains explicitly marked.

For fiscal or legal use, save the report run ID and evidence hash with the
period-close workpapers and reconcile disclosed exceptions before filing.
