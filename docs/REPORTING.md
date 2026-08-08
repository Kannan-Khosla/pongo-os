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

Report generation is queued on the existing worker instead of running inside a
web request. The UI immediately shows the latest completed snapshot for the
same normalized filters, then polls a small job-status response for progress.
Only one queued or running job is allowed for an identical report request.
Interrupted jobs are retryable, and completed snapshots remain immutable.
The worker also renders the CSV and PDF once, stores both artifacts and their
SHA-256 hashes with the run in PostgreSQL, and marks the job complete only after
both artifacts are ready. Downloads stream those stored bytes; they do not
rebuild a large report in the web process. Runs created before persisted
artifacts were introduced must be regenerated before download.

Job endpoints:

- `POST /api/reports/jobs/{report_key}` queues or deduplicates a run.
- `GET /api/reports/jobs/{job_id}` returns progress and the completed run ID.
- `POST /api/reports/jobs/latest/{report_key}` returns the latest verified run
  with exactly matching normalized filters.

The original synchronous run endpoint remains available for API compatibility.

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

Date-based reports provide instant last month, last two months, last three
months, last year, and calendar-year-to-date presets while preserving custom
date entry. Received Inventory also exposes the same presets directly on its
operational report page.

Shared report scope controls use the live location and item catalogs. When
Pongo has one active warehouse it is selected automatically; location, brand,
category, and order-status filters default to all. Warehouse, location, brand,
category, and order status are dropdowns, while SKU remains an exact-or-partial
text search. The same behavior applies to every report that exposes those
filters.

## External delivery

Google Sheets publishing and SMTP email remain backend-only operations. Staff
configure Google Sheets under Settings → Google Sheets, or follow the direct
**Sign in with Google** action shown beside a disconnected report. Pongo displays the
exact authorized redirect URI for a Google OAuth web client. Staff enter the
client ID/secret once, click **Sign in with Google**, approve access in
Google, and return to Pongo. The authorization code is exchanged server-side;
the resulting refresh token is stored encrypted and is never shown or copied by
staff.

The Google consent requests Sheets access plus file-level Google Drive access.
A report creates a spreadsheet with `Report` and `Audit` tabs. Optional email
addresses receive Google Drive writer permissions. The Google Sheets action
appears immediately after a verified run is ready and opens the created
spreadsheet directly, without a local CSV or Excel download.

Email delivery can attach CSV and PDF versions and include a previously-created
Google Sheet URL. Each attempt creates a `report_deliveries` audit row.

The legacy `GOOGLE_REPORTS_*` environment variables remain as a bootstrap
fallback. App-saved database configuration takes precedence.

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

## Interactive preview pagination

The browser requests report detail in pages of at most 100 rows and displays
the exact full row count. This bounds response size and table rendering for
large reports. Pagination is presentation-only: the immutable database payload,
SHA-256 evidence hash, persisted CSV/PDF artifacts, Google Sheet, and emailed
attachments continue to contain the complete report.
