# Item Import Workspace

## Product contract

Items → Import items opens a full-page, six-step workflow:

1. Choose outcome.
2. Upload a CSV.
3. Match source columns to Pongo OS fields.
4. Review, correct, or exclude rows.
5. Confirm the exact changes.
6. Review results and recovery actions.

The three outcomes are deliberately separate:

| Outcome | Allowed effect | Explicitly protected |
| --- | --- | --- |
| Add new items | Creates new item records and approved metadata. Existing SKUs are blocked. | On hand, allocated, available, on order, stock movement history. |
| Update item details | Matches by SKU and changes approved item metadata. Blank cells preserve current values unless “clear blank values” is enabled. | On hand, allocated, available, on order, stock movement history. |
| Set starting inventory | For an existing, zero-stock item with no stock movement history, creates one audited opening-balance movement at an active location. | Any item with operational stock or stock history; allocated always starts at zero. |

WooCommerce catalog sync and connection repair remain separate actions under
Items → More. A variable product parent is not an inventory item; purchasable
variations remain separate items.

## Backend-owned schema and templates

`GET /api/items/import/schema` is the source of truth for supported outcomes,
field labels, types, aliases, requirements, examples, the maximum upload size,
and preview lifetime. The current schema version is `2026-08-06.1`.

Templates are generated from that same schema:

- `GET /api/items/import/templates/add_items`
- `GET /api/items/import/templates/update_items`
- `GET /api/items/import/templates/update_items?include_existing=true`
- `GET /api/items/import/templates/starting_inventory`

Metadata templates never contain On hand, Allocated, Available, or stock
movement columns. The starting-inventory template contains only SKU, starting
quantity, warehouse, inventory location, and an optional reference note.

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
- Match update and starting-inventory rows by normalized exact SKU only.
- Never fall back to barcode for an update. This prevents a mistyped SKU from
  renaming the wrong item.
- Detect duplicate SKUs and barcodes in the file and database.
- Validate URLs, booleans, whole numbers, non-negative decimals, field lengths,
  and active warehouse/location pairs.
- Show row-specific error codes, invalid values, human messages, and suggested
  actions. Rows can be corrected inline or excluded.

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

## History, audit, and recovery

Items → More → Import history shows the outcome, original filename, status,
row totals, actor, completion time, and duration. Operators can download:

- the exact original CSV from `/api/import-jobs/{job_id}/source-file`;
- correction rows with structured error columns from
  `/api/import-jobs/{job_id}/failed-rows`;
- field changes from `/api/import-jobs/{job_id}/changes`.

Completed item-detail updates support guarded rollback at
`POST /api/import-jobs/{job_id}/rollback`. Rollback is all-or-nothing and only
runs when every imported field still equals the imported value. It restores
metadata and records zero-quantity audit events. It never deletes newly added
items and never reverses stock movements.

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
7. Record starting inventory on a new zero-stock item and verify one movement.
8. Repeat that starting-inventory file and verify the row is blocked.
9. Change an item after preview and verify commit returns stale-preview 409.
10. Fix and exclude rows inline, then verify only valid included rows commit.
11. Download original and failed-row files from history.
12. Roll back an update, then modify an imported field and verify a second or
    stale rollback is refused safely.

No production database or live WooCommerce connection is needed for this QA.
