# Item Import Workspace

## Product contract

Items → Import items opens a full-page, six-step workflow:

1. Choose outcome.
2. Upload a CSV.
3. Match source columns to Pongo OS fields.
4. Review, correct, or exclude rows.
5. Confirm the exact changes.
6. Review results and recovery actions.

The five outcomes are deliberately separate:

| Outcome | Allowed effect | Explicitly protected |
| --- | --- | --- |
| Add new items | Creates new item records and approved metadata. Existing SKUs are blocked. | On hand, allocated, available, on order, stock movement history. |
| Update item details | Matches by SKU and changes approved item metadata. Blank cells preserve current values unless “clear blank values” is enabled. | On hand, allocated, available, on order, stock movement history. |
| Repair item data and locations | Matches by Pongo Item ID, with SKU fallback, updates nonblank Brand/Unit cost, and consolidates unallocated stock plus on-order quantities into one required active location. | Barcode, SKU, Woo identity, item totals, allocations, and WooCommerce stock. Allocated units remain reserved at their source and are reported as deferred. |
| Override stock levels | Matches by exact SKU, sums location rows into one exact total per SKU, skips matching totals and unknown SKUs, and applies every matched change through one audited adjustment. | CSV locations never reassign stock; invalid quantities, allocation conflicts, and stale stock block every matched change. Allocated and sellable stay system-managed. |
| Set starting inventory | For an existing, zero-stock item with no stock movement history, creates one audited opening-balance movement at an active location. | Any item with operational stock or stock history; allocated always starts at zero. |

WooCommerce products do not require CSV. Items → **Import new products** scans
for missing Woo simple products and purchasable variations, imports them in one
step, then opens a short setup form. SKU and barcode are required; description,
brand, prices, unit cost, warehouse/location, and opening stock are optional.
Opening stock uses the audited opening-balance workflow. Full catalog mapping
and connection repair remain under Items → More.

## Backend-owned schema and templates

`GET /api/items/import/schema` is the source of truth for supported outcomes,
field labels, types, aliases, requirements, examples, the maximum upload size,
and preview lifetime. The current schema version is `2026-08-26.1`.

Templates are generated from that same schema:

- `GET /api/items/import/templates/add_items`
- `GET /api/items/import/templates/update_items`
- `GET /api/items/import/templates/update_items?include_existing=true`
- `GET /api/items/import/templates/repair_items?include_existing=true`
- `GET /api/items/import/templates/update_stock`
- `GET /api/items/import/templates/update_stock?include_existing=true`
- `GET /api/items/import/templates/starting_inventory`

Metadata templates never contain In stock, Allocated, Sellable, or stock
movement columns. The editable stock export contains one total row per item:
SKU, exact In stock, and an optional reference note. The starting-inventory
template remains limited to onboarding fields.

On the Items page, selecting a missing title, barcode, brand, category, or unit
cost quality card exposes an `Export CSV` action. It calls the filtered item
export with `editable=true`, so the downloaded rows use the Update item details
schema and exclude protected quantity fields. `Import completed CSV` opens the
update-details upload step directly. Other quality filters remain view-only
because they require a different repair workflow.

The canonical legacy item export and endpoints at `/api/items/import/preview`
and `/api/items/import/commit` remain available for compatibility. The Items UI
uses the guided workspace endpoints.

## Validation and matching rules

- Accept only `.csv` files up to `ITEM_IMPORT_MAX_BYTES` (10 MiB by default).
- Decode UTF-8 and UTF-8 BOM safely.
- Detect comma, semicolon, tab, or pipe delimiters.
- Reject empty files, header-only files, duplicate normalized headers,
  malformed rows, extra row values, unsupported MIME types, and invalid types.
- Normalize header matching by case, surrounding whitespace, punctuation, and
  documented aliases. Ambiguous fields remain unmatched.
- Require one destination per source and prevent the same destination from
  being mapped twice.
- Match update, stock-override, and starting-inventory rows by normalized exact SKU only.
- Match repair rows by immutable Pongo Item ID when present, otherwise by exact SKU. When both are present they must identify the same item. Product name and Woo IDs are read-only identity context; Barcode is not part of the repair schema and an unrelated Barcode column is ignored.
- Never fall back to barcode for an update. This prevents a mistyped SKU from
  renaming the wrong item.
- Detect duplicate SKUs and barcodes in the file and database. Stock override
  sums distinct location rows for one SKU and blocks repeated SKU/location rows
  to prevent accidental double counting.
- Validate URLs, booleans, whole numbers, non-negative decimals, field lengths,
  and active warehouse/location pairs.
- Show row-specific error codes, invalid values, human messages, and suggested
  actions. Rows can be corrected inline or excluded.
- Stock override requires only exact SKU and a non-negative In stock value. A
  full inventory export can be uploaded directly; warehouse, location, and
  unrelated columns are ignored after distinct location rows are summed by SKU.
- A SKU absent from Pongo is a visible, downloadable skip. A Pongo SKU absent
  from the file remains unchanged.
- Existing Pongo assignments are preserved. Total variance is applied to
  UNASSIGNED first, then the default assignment, then remaining assignments;
  no assignment is created and stock never drops below allocated quantity.

## Preview, commit, and concurrency

Every upload creates `import_previews` plus `import_preview_rows`. The preview
stores the sanitized filename, exact UTF-8 source CSV, SHA-256, schema version,
source headers, mapping, normalized rows, corrections, issues, proposed field
changes, actor, and expiration. It is resumable for 24 hours by default.

Commit accepts a required idempotency key. A retry returns the saved result.
Before writing, the service hashes the fields read during preview and compares
them to the current item. A changed or deleted item produces HTTP 409
`stale_preview`; the transaction does not overwrite the newer values.

Metadata commits are one database transaction. Any unexpected write failure
rolls back all metadata changes. Starting inventory uses the existing guarded
stock mutation service per row; its idempotency key is stable per preview row,
and every successful row creates both a stock movement and inventory audit
event.

Stock overrides are all-or-nothing across every matched SKU. Unknown SKUs are
recorded as nonblocking skips; exclusions are not allowed. One transaction and
one stock adjustment lock every matched SKU before the final stale check,
verify its total, allocation, and active assignment set still equal the preview,
calculate each variance, recalculate totals, and create movement audit rows.
Any invalid quantity, ambiguous Pongo SKU, allocation conflict, missing safe
assignment, inconsistent total, excluded row, or stale match changes nothing.
After commit, the existing FIFO allocation runs in the transaction. When live
WooCommerce stock writeback is enabled, the existing chunked stock-sync worker
is queued so a large CSV does not hold the browser request open for one remote
call per item. Stock movements are intentionally not customer-rollbackable.

Repairs are also all-or-nothing. Commit locks every matched item, assignment,
and physical location before comparing the item fields and complete assignment
snapshot captured by preview. It moves only unallocated stock through audited
location transfers, moves current on-order quantities, makes the target the
default, and deactivates only zero-balance sources. A source containing allocated
stock stays active with exactly its reserved quantity and appears in the result
as deferred. Item-level In stock, Allocated, Sellable, and On order totals must
be identical before and after the transaction. Repair does not queue a
WooCommerce stock sync because those totals do not change.

Repair confirmation itself returns `202` after idempotently creating one
`queued` import job. The existing worker dyno claims that job with a locked,
skip-locked query and runs the complete repair transaction outside the web
request. The UI polls `GET /api/import-jobs/{id}` until `completed` or `failed`.
A worker crash rolls back the transaction and leaves the job queued for retry.
A validation or application failure records a failed job, saves no repair
changes, and reopens the preview for a new confirmation. Other item-import
outcomes remain synchronous. A repair cannot be cancelled after it has been
queued, and its running preview does not expire while it waits for the worker.

## History, audit, and recovery

Items → More → Import history shows the outcome, original filename, status,
row totals, actor, completion time, and duration. Operators can download:

- the exact original CSV from `/api/import-jobs/{job_id}/source-file`;
- correction rows with structured error columns from
  `/api/import-jobs/{job_id}/failed-rows`;
- field changes from `/api/import-jobs/{job_id}/changes`. Change history is
  server-paged (`page`, `page_size` up to `100`) and returns the exact total plus
  page metadata; the field-level before/after record shape is unchanged.

Completed item-detail updates support guarded rollback at
`POST /api/import-jobs/{job_id}/rollback`. Rollback is all-or-nothing and only
runs when every imported field still equals the imported value. It restores
metadata and records zero-quantity audit events. It never deletes newly added
items and never reverses stock movements.
Repair jobs do not offer automatic rollback; their paired transfer movements and
zero-quantity audit event are the permanent operational record.

Item detail activity includes the imported field, before/after values, original
filename, actor, and import job reference.

## Configuration and operational limits

| Variable | Default | Purpose |
| --- | ---: | --- |
| `ITEM_IMPORT_MAX_BYTES` | `10485760` | Maximum source CSV bytes. Range: 1 KiB–100 MiB. |
| `ITEM_IMPORT_PREVIEW_TTL_HOURS` | `24` | Preview lifetime. Range: 1–168 hours. |

The current 10 MiB cap keeps parsing and validation synchronous and bounded.
If real files repeatedly approach that ceiling or request latency breaches the
application timeout, add a durable background worker using the same preview and
idempotency records; do not create a second import contract.

### Measured local performance

On 2026-08-06, the automated SQLite/TestClient benchmark processed a 5,000-row,
9,045,017-byte CSV with deliberately large product names:

| Measurement | Result |
| --- | ---: |
| Upload, parse, persist, and validate preview | 2.266 s |
| Fetch page 100 at 25 rows | 0.007 s |
| Commit 5,000 new items and audit records | 12.115 s |
| Peak traced Python memory during preview | 111,618,950 bytes |
| Peak traced Python memory during commit | 102,841,874 bytes |
| Preview response payload | 3,289 bytes |
| 25-row page payload with 1,797-character names | 205,742 bytes |
| Preview SQL statements | 5,014 |
| Commit SQL statements | 35,011 |

On 2026-08-10, the atomic stock regression previewed 1,500 existing SKUs in
0.236 seconds and changed all 1,500 in 0.925 seconds through one adjustment and
one transaction on local SQLite. This proves the requested file-level behavior,
not Heroku/PostgreSQL capacity; production timing must still be observed on the
first controlled Pongo import.

On 2026-08-26, the repair regression previewed 1,500 items with two assignments
each in 0.242 seconds, queued the repair in 0.005 seconds, and completed 1,500
audited consolidations in the worker in 0.888 seconds on local SQLite (1,511
preview statements, 8 web-queue statements, and 12,019 worker statements).
This is a local regression ceiling, not a Heroku/PostgreSQL latency guarantee.

The statement counts are dominated by required per-row persistence and audit
writes; catalog matching is set-based rather than one lookup per row. These are
local SQLite measurements, not PostgreSQL production capacity claims. Run the
same benchmark against the intended Heroku database class before increasing the
10 MiB limit or committing files this large under a tighter request timeout.

## QA runbook

Before release:

1. From `backend`, run `.venv/bin/python -m pytest tests/test_item_import_workspace_api.py -q`.
2. Run the complete backend and frontend suites.
3. Run `npm run build` in `frontend`.
4. Apply Alembic to a disposable database and confirm revision
   `20260806_0035` is at head.
5. Add an item with metadata and verify all quantities remain zero.
6. Update an item that already has stock; compare on hand, allocated, available,
   and movement count before and after.
7. Export editable current stock, change one location to an exact value, and
   verify one adjustment, one movement, correct variance, and unchanged allocation.
8. Change location stock after preview and verify stock commit returns 409
   without overwriting the newer count.
9. Verify negative stock and duplicate SKU/location rows are blocked.
10. Record starting inventory on a new zero-stock item and verify one movement.
11. Repeat that starting-inventory file and verify the row is blocked.
12. Fix and exclude rows inline, then verify only valid included rows commit.
13. Download original and failed-row files from history.
14. Roll back an update, then modify an imported field and verify a second or
    stale rollback is refused safely.
15. Preview a repair with `001` plus `UNASSIGNED`, confirm the summed item total
    is unchanged, allocated sources are deferred, and a post-preview assignment
    change blocks the entire commit.

No production database or live WooCommerce connection is needed for this QA.
