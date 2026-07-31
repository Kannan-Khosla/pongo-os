# First-Time Woo Catalog And Zenventory Migration

Use this procedure only for a local/development database. Keep production
WooCommerce writes disabled throughout it.

## Backup And Reset

1. Stop the backend and back up the database. For PostgreSQL use
   `pg_dump "$DATABASE_URL" > pongo-before-mapping.sql`; for SQLite, copy the
   configured database file while the backend is stopped.
2. Run `make reset-local-db`. Verify the displayed host/database and confirm.
   The command refuses staging, production, Heroku, and non-local hosts. Pass
   `--yes` only for a deliberate scripted local reset.
3. The reset runs Alembic migrations. Run `make seed-local-locations` to
   idempotently create Main Warehouse/RECEIVING.

## Map And Enrich

1. Start the app, open Items, and click **Import Mappings**.
2. Review all counts/conflicts. A parent with three purchasable variations must
   propose three—not four—stock items.
3. Commit mappings and export **Enrichment Template**.
4. Open the template and Zenventory export in Excel. Populate local fields with
   SKU-based matching such as `XLOOKUP`; never match by row position. Preserve
   the five protected identity columns.
5. Save CSV, choose **Import CSV → Enrich Woo-Mapped Items**, and enable
   **Import opening stock** only for this first clean migration.
6. Review matched, unmatched, conflict, invalid, and changed-field rows.
   Download exceptions, fix the source, and preview again before commit.
7. Commit and reconcile item/variation count, location stock, total stock, and
   inventory value against Zenventory. Resolve only genuine exceptions with the
   searchable Remap Exceptions workflow.
8. Explicitly revalidate any old pending/failed mapping queue rows, preview them
   again, and leave production writes disabled.

## Later New Products Or Variations

Run **Import Mappings** again after Woo catalog changes. A new simple product
creates one item and each new purchasable variation creates one item. Existing
mappings receive only valid Woo-owned refreshes. Add barcode/cost/location
manually or with another update-only enrichment CSV. Do not enable opening stock
for an item with operational stock or history.

Expiry and lot-expiry data are intentionally outside this workflow.
