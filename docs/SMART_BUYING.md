# Smart Buying Intelligence

Smart Buying is a purchasing planning workspace inside Pongo OS. It uses a deterministic September 9, 2026 reference snapshot and does not change operational inventory, orders, subscriptions, supplier accounts, or inboxes. The current snapshot is synthetic; live supplier ingestion and forecasting adapters are not connected.

## Open Smart Buying

Hosted route: **https://inventory.pongo.ca/#/smart-buying/overview** (staff login).

Local frontend: **http://127.0.0.1:5173/#/smart-buying/overview**

From the repository root, use separate terminals:

```sh
backend/.venv/bin/python backend/scripts/run_smart_buying_local.py
```

```sh
npm run dev --prefix frontend -- --host 127.0.0.1 --port 5173
```

The backend launcher creates and migrates a fresh SQLite database in a temporary directory. It bypasses repository `.env` files, clears integration credentials from the child process, disables WooCommerce reads/writes/background jobs/webhooks, disables registration, and binds to loopback only. Authentication is disabled only in that disposable development process. Normal application authentication is unchanged. Stop each terminal with Ctrl-C. Run the launcher again for another empty local workspace.

The Smart Buying snapshot works independently of operational database contents. The backend is needed for authentication/bootstrap and actual PDF/CSV exports. No required environment variables were added. Optional `VITE_SMART_BUYING_ENABLED=false` disables the workspace; it does not enable a real integration.

## Screens and walkthrough

1. **Overview:** review proposed cash, savings, margin lift, stockout protection, confidence, demand chart, supplier allocation, subscriptions, risks, financial comparison, activity, and Buying Copilot.
2. **Purchase Plan:** choose Balanced, Cash Conservative, Growth, Deal Maximizer, or Subscription First. Adjust horizon, safety, budget, quantities, exclusions, or pins. Optimize the plan or optimize to the cash budget. Accept the recommendation and inspect each supplier draft.
3. **Forecast:** switch 30/60/90 days, inspect 20 SKUs, search identifiers, filter supplier/brand/category/promotions/priority, and open a product explanation. The drawer shows sellable stock, allocations, inbound, organic demand, renewals, policy target, safety, case rounding, promotion adjustments, and evidence.
4. **Supplier Deals:** inspect 17 offers from four illustrative supplier relationships. Filter by supplier, source, or type, review dates/minimums/confidence/source evidence, and apply an eligible offer within the 90-day consumption ceiling.
5. **Opportunities:** compare exact before/after basket cash and savings for actionable quantities. Price breaks, freight, and GST are recalculated when cases change.
6. **Draft Purchase Orders:** preview lines, quantities, costs, discounts, retail value, margin, freight, GST, and totals. Edit, copy, export PDF/CSV, and approve locally. **Preview Send** displays a confirmation explaining that nothing was transmitted.
7. **Supplier Intelligence:** review supplier scorecards, lead times, fill rates, discounts, spend, savings, and source records. Expand portal/email/PDF evidence without contacting a source.
8. **Scenario Simulator:** compare horizon, organic demand growth (-20% to +30%), safety stock, budget, and strategy. Applying a scenario replaces unpinned manual quantities and retains exclusions and pinned quantities. The preview uses the same retained lines.

Run buying analysis gives a short local progression through sales, renewals, offer terms, coverage, and allocation. Reset buying session returns all inputs to the original snapshot. Changes and approvals live only in memory; navigating between Smart Buying views preserves them, while a browser reload or leaving the module starts a new session. Any plan change invalidates local approval.

## Architecture and data contract

- `frontend/src/SmartBuying.jsx`: module state, overview, financial analysis, SKU explanation, draft PO, export requests, and local analysis progression. Lazy-loaded from the existing hash router.
- `frontend/src/SmartBuyingPlanning.jsx`: forecast chart, subscription breakdown, strategy controls, filterable SKU tables, supplier groups, and scenarios.
- `frontend/src/SmartBuyingSuppliers.jsx`: deals, source evidence, supplier scores, opportunities, copilot, and bounded deal application.
- `frontend/src/smartBuyingData.json`: **one shared dataset**, consumed by both frontend calculations and backend export validation. Twenty products, four suppliers, seventeen promotions, six ingestion examples, activity, and explicit subscription schedule assumptions. Supplier IDs remain distinct from brand IDs/names. Barcode strings preserve leading zeros.
- `frontend/src/smartBuyingEngine.js`: pure demand, recommendation, pricing, grouping, budget, financial, risk, and predetermined copilot functions. No clock, randomness, fetch, storage, or operational writes.
- `backend/app/schemas/smart_buying.py`: bounded export request contract.
- `backend/app/services/smart_buying.py`: reads the shared snapshot, validates the proposed draft against its products and offers, and produces CSV in memory.
- `backend/app/api/routes/smart_buying.py`: read-only snapshot and export endpoints. PDF uses the existing `pdf_exports.tabular_pdf_bytes` renderer and the same validated CSV.
- `backend/scripts/run_smart_buying_local.py`: isolated local backend launcher. No production setup changes.

The feature reuses React, Lucide, the installed modular ECharts renderer, current Pongo blue/peach styling, sidebar/subnavigation, auth/API fetch conventions, table containers, and backend PDF tools. No new package, database model, migration, external service, or vendor account is required.

### API

| Method | Path | Result |
| --- | --- | --- |
| GET | `/api/smart-buying/snapshot` | Complete versioned planning snapshot |
| POST | `/api/smart-buying/export/csv` | Validated local draft CSV attachment |
| POST | `/api/smart-buying/export/pdf` | Validated local draft PDF attachment |

Export requests contain `po_number`, `supplier_id`, `as_of`, `expected_delivery`, `freight`, `tax`, and lines with `product_id`, `cases`, `units`, `unit_cost`, fractional `discount`, `effective_cost`, `line_total`, and `retail_value`. The server retrieves product names/SKUs from the snapshot and checks supplier ownership, dates, duplicate products, bounds, MOQ, case units, promotion eligibility, arithmetic, freight, and tax. Invalid requests receive 422. Exports are marked as planning drafts, use `Cache-Control: no-store`, and create no database records. The two exact export POST paths are allowlisted for the existing read-only preview role; ordinary staff authentication and existing SameSite session-cookie behavior are unchanged.

There is deliberately no supplier transmission endpoint. Approval is local UI state. Existing receiving remains direct receiving without purchase orders.

## Calculation rules and honest limits

- Historical 30/60/90-day sales are cumulative **organic-only** units. Weighted daily organic demand uses 50% latest month, 30% preceding month, and 20% oldest month. Organic growth changes that rate; confirmed renewals are added once.
- The synthetic subscription schedule has 257 active subscriptions, one sellable unit each, every 30 days: 257/514/771 units over the three horizons. This is explicit reference scheduling, not a live subscription integration.
- Forecast demand is independent of buying strategy. `targetOrganicUnits` expresses the strategy's inventory policy, so Cash Conservative reduces the stocking target without pretending customers buy less.
- Sellable stock is physical stock minus allocations, floored at zero. Replenishment subtracts sellable stock and inbound from the stocking target, renewals, and safety stock, then rounds to cases and MOQ.
- Promotion dates use the fixed snapshot date. Eligible unit minimums and supplier basket thresholds must be met. Buy-X/get-Y offers count complete earned free cases. Extra promotion inventory must fit the selected window, capped at 90 days; offer application preserves pins and exclusions.
- Manual changes preserve the rest of the current basket and exit automatic budget allocation. Changing horizon, strategy, safety, or organic growth recalculates unpinned, nonexcluded quantities; changing the budget alone retains the basket until optimization. The cash warning shows any resulting overage. Excluding and re-including an SKU restores its prior requested cases.
- Budget allocation is deterministic and greedy at case level. It includes freight and GST. Pinned quantities take precedence and can exceed budget, which is explicitly shown. This 20-SKU heuristic is not a global mathematical optimum for interacting rebates/freight thresholds.
- Purchase cash includes estimated 5% GST and freight. Gross profit/margin includes freight but excludes recoverable GST. Rebate cash treatment is a planning assumption; real payment timing needs verification.
- The financial baseline prices the **same basket** at regular cost, with recalculated freight/GST. Stockout risk separately compares no replenishment with the proposed buy. Overstock avoided compares against a full 90-day restock ignoring existing stock; it is not measured historical company waste.
- Revenue supported and projected COGS use a 90-day horizon. Stockout protection is a horizon shortage metric; the separate delivery risk identifies stock that could run out before the supplier arrives.
- Inventory value uses synthetic current quantities and costs; incoming stock is assumed to arrive by supplier lead time. Scorecards, confidence, activity, and relationships are illustrative. Confidence is not statistically calibrated.
- Dashboard currency rounds to whole dollars for readability. Draft PO prices and totals retain cents, with six-decimal effective-unit precision validated for fractional case promotions.

Initial snapshot: **$42,854.10** purchase cash, **$3,665.65** supplier discounts, approximately **40.8%** purchase margin and **71 days** of weighted coverage. Default budget optimization selects **$39,951.76** including GST; it protects 17 of 19 horizon shortages and covers known renewals. These are computed totals, not separate dashboard fixtures.

## Production integration path

Keep the current data boundary, replacing the bundled fixture with an authenticated normalized snapshot. Move authoritative recommendation execution and draft persistence to the backend when decisions become operational.

| Capability | Next implementation |
| --- | --- |
| Supplier websites / portals | Explicitly authorized, bounded source jobs with timeouts, pacing, resumable batches, observation timestamps, and stop conditions for CAPTCHA/denial/throttling. No credentials in frontend code. |
| Supplier email | Separately authorized narrow mailbox/attachment access, source provenance, content hashing and deduplication, quarantined unknown inputs, no send permissions required for ingestion. |
| Promotion PDFs | Reuse installed PDF extraction support; retain source page/text and raw units/prices; normalize dates, pack sizes, threshold scope, currency and rebates; review uncertain extractions. |
| Real forecasting | Map current InventoryItem/location stock, allocations/open orders, reporting sales snapshots, and official subscription snapshots through a read-only adapter. Backtest against stockouts, exclude cancelled renewals, and calibrate seasonality/confidence. |
| Supplier SKU mapping | Separate supplier, brand, supplier SKU, Pongo SKU, barcode, recipe and size. Normalize `24/85g` packs to sellable cans. Preserve raw evidence; unmatched/uncertain cost remains null and requires review. Never overwrite Pongo-owned item fields automatically. |
| Real POs / sending | Persist immutable draft revisions, staff approvals, audit events and transmission status. Add an explicitly authorized sender with idempotency and reconciliation. Existing stock, receiving and Woo writeback safeguards remain separate. |

The referenced supplier task established Pan/Pacific Pet portal lookups, barcode preservation, exact recipe/size matching, unit-price normalization, and incomplete-match handling. Those lessons inform the source contracts. Its live supplier output and credentials are not copied into this snapshot. Pacific Pet, Petcurean, Royal Canin, and Anipet relationships/offers here are synthetic.

## Safety and verification

No WooCommerce writes, operational stock changes, order-state changes, subscription changes, emails, supplier crawling, inbox reads, supplier orders, or external transmission were added. All Smart Buying mutations are in-memory UI actions. The only requests are to the local app for authentication and generated documents. Deployment uses the existing authenticated Heroku application, release process, and worker configuration. The isolated local launcher is never the production entrypoint.

Baseline: 203 frontend tests; frontend build passed; 629 backend tests passed and 14 PostgreSQL-only checks skipped. New coverage checks shared financial reconciliation, strategies/forecasts, case rounding, budget/pins, offer thresholds, safe supplier interactions, navigation, drawers, scenario application, approval invalidation, analysis progression, export failure/retry/cleanup, server validation/auth, PDF/CSV structure, and absence of operational writes/external connections.

Frontend regression: 240 passed across 12 test files; production build passed. Backend regression: 650 passed, 14 PostgreSQL-only skipped; 120 generated frontend supplier drafts reconciled with backend validation. Responsive browser checks covered all eight views at 375px, plus overview and plan at 768/1024/1440px, with no document overflow. Existing light-only Pongo theme retained; keyboard focus, Escape, reduced-motion handling, and export states are covered. No standalone lint/typecheck command is configured for the existing JavaScript frontend. The production build reports the pre-existing large-chunk warning.

## Release verification

The release candidate preserves the already deployed reporting and Google Sheets fixes from `a3093028`; it does not revert their filters or export error handling. It adds no schema migrations or runtime dependencies. The test dependency Vitest is updated to 4.1.11 to address [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9). The GitHub release gate covers dependency audits, PostgreSQL concurrency, migration recovery, backup/restore, frontend tests/build, and the existing browser contract chain.

Production is deployed through the existing Heroku `Procfile`, with staff authentication and both web/worker processes retained. A managed backup precedes deployment. Before release, `/health` is healthy; `/ready` already reports inventory cost, duplicate barcode, missing location, and alert-webhook issues. Post-deployment checks compare these existing conditions with the recorded baseline.
