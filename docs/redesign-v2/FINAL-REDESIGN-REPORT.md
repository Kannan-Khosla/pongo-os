# Pongo OS v2 — final redesign report

## 1. Executive summary

This exploration audited the complete working-tree frontend and proposes a new, scalable operating-system identity without changing the application. The strongest current asset is not the visual layer; it is the depth of safe operational workflows already present. The main problem is structural growth around a fixed Zenventory-inspired shell, several page-specific visual dialects, duplicated tables and long multi-workflow pages.

The selected direction, **Pongo Command Nexus**, places a 76 px deep-indigo module rail and 228 px contextual rail around a bright, data-dense workspace. A 64 px command bar provides global search and scanner entry. Routine record details retain list context in a right drawer; operational sessions use scan-first workspaces; guarded stock or integration mutations show consequence before commit. Warm orange has one semantic job: live work, scanning, attention and progress.

The deliverable is design exploration only: ten routed static preview screens, an order-detail drawer, local interactions, all major component and state demonstrations, a conceptual design system and ten audit/design documents. It makes no API requests and contains no credentials or real customer data.

## 2. Audit totals

| Measure | Result |
| --- | ---: |
| Route patterns audited | **29** |
| Page/subpage destinations audited | **29** |
| Render-level UI components/primitives audited | **133** |
| End-to-end workflows mapped | **34** |
| Design concepts explored | **3** |
| Routed preview screens | **10** |
| Additional record-detail treatment | **1 order drawer** |
| Required documentation files | **11** (this report included) |
| Total isolated artifacts | **16** (including preview files and design-system master) |

Counts are based on the current hash route parser, 130 capitalized render functions in `frontend/src/App.jsx`, three exports in `frontend/src/components.jsx`, and the journey map in `03-WORKFLOW-AND-STATE-MAP.md`.

## 3. Main problems found

1. **The global shell is not responsive.** A fixed 280 px sidebar consumes small-screen workspace while body overflow is hidden.
2. **Focus behavior is incomplete in overlays.** Initial focus exists in places, but trapping and return focus are inconsistent.
3. **Navigation has outgrown the original hierarchy.** Thirteen top-level destinations, nested order/inventory views and a complete Woo operations console under Settings obscure where work belongs.
4. **Two dashboards compete to be home.** Business Dashboard and Inventory Overview/Command Center split the product's front door.
5. **The UI has several dialects.** General panels, Items, Business, Zen-style Orders, Picking and Reports use different table, spacing and action rules.
6. **Tables and state surfaces are repeatedly implemented.** Loading, error, row actions, responsive adaptation and pagination vary by module.
7. **Action hierarchy is too flat.** High-risk and routine actions often appear as equal peers.
8. **Long pages lose workflow context.** Receiving, cycle count, route planning, history and integrations stack entry, summary, table and detail regions vertically.
9. **Static text is sometimes given tab semantics.** This creates false interaction cues for assistive technology.
10. **The visual identity still reads as an inventory-specific Zenventory descendant.** It undersells the broader commerce and operations platform.

Current strengths to preserve are native form controls, visible focus, verbal empty states, preview-before-commit, scanner Enter behavior, strong stock/Woo safety copy and persistent audit intent.

## 4. Concept selection

Three directions were evaluated: **Command Nexus** (93/100), **Signal Grid** (82/100) and **Orbit Workspace** (86/100). Command Nexus won because it supports warehouse density, management intelligence, future modules, responsive drill-down and a distinct Pongo identity without becoming a free-form card board or slowing repeat work.

The concept intentionally avoids a configurable dashboard engine, speculative personalization, heavy glass, neon/HUD effects and new product capability. It reorganizes existing behavior into seven reusable screen patterns: Command Center, queue + detail, operational session, entity workspace, report canvas, integration console and settings form.

## 5. Design-language decisions

- **Identity:** deep-indigo operational frame, bright work canvas, thin warm live-state signal.
- **Brand anchor:** Pongo blue `#0F149A`; orange `#E86732` is not a generic primary-action color.
- **Typography:** IBM Plex Sans-style interface stack plus IBM Plex Mono-style identifiers; tabular numerics for quantities, dates, IDs and money.
- **Density:** 40 px desktop controls/rows, 44 px touch controls, compact panels inside strong grouping.
- **Geometry:** 8–18 px radii by role, fine borders, restrained card elevation and directional drawer shadow.
- **Navigation:** global module rail + module-specific contextual rail + command/search bar.
- **Details:** right drawer for routine inspection/editing; short modal only for decisions or guarded mutations.
- **Tables:** sticky header, selected leading edge, visible filter chips, contained overflow and mobile record-card adaptation.
- **States:** structured skeleton, actionable empty/error states, semantic status dot + text and polite toast confirmation.
- **Motion:** 140–280 ms functional transitions and one restrained 2.4 s live pulse, all collapsed by `prefers-reduced-motion`.

## 6. Proposed information architecture

- Merge Dashboard and Inventory Overview into **Command Center**, with distinct business and operations bands.
- Group work into **Command, Commerce, Warehouse, Intelligence and System**.
- Promote **Picking** to a visible Commerce destination.
- Rename Items to **Catalog** in the proposal while retaining every current item route and workflow.
- Keep six inventory views as tabs under **Inventory**, with By Location becoming a location-navigator workspace.
- Rename the current Woo-heavy Settings page to **Integrations / WooCommerce**; reserve honest Settings areas for Company, Users, Warehouses and System.
- Group thirteen Insights tabs into seven business domains while preserving all datasets.
- Make scan/identifier resolution available from the global command field as well as dedicated floor flows.

Every one of the 29 current destination patterns is mapped in `08-INFORMATION-ARCHITECTURE.md`.

## 7. Preview delivered

Routed screens:

1. Command Center
2. Open Orders / allocation/history variants
3. Pick station
4. All Inventory / low-stock/par/movement variants
5. Inventory by Location
6. Direct Receiving
7. Insights
8. Integrations / WooCommerce
9. Settings
10. Component gallery

The order-detail requirement is demonstrated as a structured right drawer with fictional customer identity, status, line items, quantities, fulfilment method, due information, audit timeline and next action.

Local-only interactions include screen navigation, context collapse, mobile navigation, command dialog, order drawer, row/bulk selection, tabs, filter-chip removal, toasts, scanner success/failure, quantity controls, settings validation, guarded typed confirmation, receiving preview/commit and populated/loading/empty/error state switching. All content lives in browser memory and resets on reload.

## 8. Responsive behavior

The prototype CSS demonstrates:

- **Above 1260 px:** full 76 + 228 px rails and wide multi-column workspace.
- **981–1260 px:** narrower context rail, two-column metrics and guards.
- **761–980 px:** icon module rail and overlay context navigation; split workspaces become one column.
- **760 px and below:** both rails become off-canvas; command utilities compact; grids stack; tables become labelled record cards; dialogs/drawers fill available width.
- **390 px and below:** one-column records and tighter chart/table priority.

The CSS includes body-level overflow protection, internal table scrolling before card conversion, `100dvh` overlay handling and reduced-motion rules. Automated visual verification at the requested viewport matrix remains open because no in-app browser was available in this session.

## 9. Accessibility findings

- Measured core text and semantic color pairs pass WCAG AA: primary text 17.47:1, secondary 7.40:1, caption 4.66:1, primary button 13.23:1; semantic pills range from 5.18:1 to 5.90:1.
- Native buttons, inputs, selects and tables are used; no clickable divs.
- The shell provides a skip link, named landmarks and a 3 px `:focus-visible` ring.
- Dialogs receive initial focus, Escape closes them and focus returns to the trigger.
- Statuses use dot + text; charts have sentence-level labels and backing values/table data.
- Forms use visible labels, help text, inline errors and `aria-describedby`.
- Scanner and bulk-selection results use live regions.
- `prefers-reduced-motion` removes pulse, shimmer and transitions.

Open items for a future implementation are a full shared focus trap with inert background, automated browser/axe validation, 200% zoom testing, real screen-reader passes, and keyboard grid navigation for power users.

## 10. UI/UX Pro Max recommendations used

The required design-system search and focused product/style/color/typography/UX/chart/web/React searches informed:

- the data-dense dashboard base;
- drill-down navigation that preserves context;
- real-time monitoring cues without a dark work canvas;
- line charts for trends and horizontal bars for comparison;
- compact filterable tables with mobile record adaptation;
- semantic controls, skip navigation, visible focus and reduced motion;
- actionable loading, empty and error states after a 300 ms threshold.

Enterprise marketing gateway patterns, neon HUD/vaporwave, heavy glass, all-mono typography and orange as a generic CTA were explicitly rejected.

## 11. Important design decisions and open approvals

Human approval is still required for:

1. Merging the two current dashboards into one Command Center.
2. Promoting Picking and renaming Items to Catalog.
3. Splitting WooCommerce operations from general Settings.
4. Adopting the two-rail desktop shell and its tablet overlay behavior.
5. Using the proposed “P” command glyph pending a formal brand/wordmark decision.
6. Selecting a font delivery approach; the prototype deliberately falls back to installed system fonts and makes no external font request.
7. Choosing default table density and which secondary columns collapse on mobile per role.
8. Defining the operational approval gate—not a visual choice—for eventual WooCommerce stock writeback.

## 12. Recommended future implementation phases

No implementation is started by this deliverable. If the concept is approved:

1. Validate IA and screen flows with warehouse and management staff using the static prototype.
2. Build tokens, shell, navigation, field, status, table, overlay and state primitives behind an internal feature flag.
3. Migrate Command Center, Orders and Inventory as the first coherent vertical slice.
4. Migrate Picking, Receiving, Cycle Count and Scanner with floor-device usability tests.
5. Migrate Insights, Reports, Routes, Integrations and Settings.
6. Run accessibility, performance, visual-regression and role-permission validation before rollout.

## 13. Files created

```text
docs/redesign-v2/
├── 00-BASELINE.md
├── 01-ROUTE-AND-PAGE-INVENTORY.md
├── 02-COMPONENT-INVENTORY.md
├── 03-WORKFLOW-AND-STATE-MAP.md
├── 04-CURRENT-UI-UX-AUDIT.md
├── 05-UI-UX-PRO-MAX-RESEARCH.md
├── 06-DESIGN-CONCEPTS.md
├── 07-DESIGN-LANGUAGE.md
├── 08-INFORMATION-ARCHITECTURE.md
├── 09-ACCESSIBILITY-REVIEW.md
├── FINAL-REDESIGN-REPORT.md
└── preview/
    ├── README.md
    ├── index.html
    ├── preview.js
    └── styles.css

design-system/pongo-os-v2/
└── MASTER.md
```

## 14. Verification and working-tree boundary

`git status --short` after prototype completion (the new directories are collapsed by Git; the per-file list above is exhaustive):

```text
 M README.md
 M backend/app/api/routes/import_jobs.py
 M backend/app/api/routes/items.py
 M backend/app/api/routes/woocommerce.py
 M backend/app/models/imports.py
 M backend/app/models/inventory.py
 M backend/app/schemas/items.py
 M backend/app/schemas/woocommerce.py
 M backend/app/services/woocommerce_client.py
 M backend/app/services/woocommerce_remap.py
 M backend/app/services/woocommerce_sync.py
 M backend/app/services/woocommerce_writeback.py
 M backend/tests/test_mvp_hardening_api.py
 M backend/tests/test_woocommerce_sync_api.py
 M backend/tests/test_woocommerce_writeback_api.py
 M docs/.DS_Store
 M docs/API_SPEC.md
 M docs/BUILD_PLAN.md
 M docs/CSV_COLUMNS.md
 M docs/DATABASE_SCHEMA.md
 M docs/DECISIONS.md
 M docs/STAGING_WOOCOMMERCE_TESTING.md
 M docs/WOOCOMMERCE_SYNC.md
 M docs/ui-reference/.DS_Store
 M frontend/src/App.css
 M frontend/src/App.jsx
 M frontend/src/App.test.jsx
?? .claude/
?? .codex/
?? Makefile
?? backend/alembic/versions/20260715_0020_item_enrichment.py
?? backend/app/services/item_enrichment.py
?? backend/scripts/
?? backend/tests/test_item_enrichment_api.py
?? backend/tests/test_reset_local_db.py
?? design-system/
?? docs/CODEX_REDESIGN_PROMPT.md
?? docs/FIRST_TIME_WOO_MIGRATION.md
?? docs/redesign-v2/
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.12 PM.png
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.19 PM.png
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.25 PM.png
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.45 PM.png
?? docs/ui-reference/redesign/
```

`git diff --stat` after completion:

```text
 README.md                                       |  24 ++
 backend/app/api/routes/import_jobs.py           |   5 +-
 backend/app/api/routes/items.py                 |  37 +-
 backend/app/api/routes/woocommerce.py           |  28 +-
 backend/app/models/imports.py                   |   2 +
 backend/app/models/inventory.py                 |   6 +-
 backend/app/schemas/items.py                    |   3 +
 backend/app/schemas/woocommerce.py              |  25 ++
 backend/app/services/woocommerce_client.py      |   1 +
 backend/app/services/woocommerce_remap.py       | 105 ++++-
 backend/app/services/woocommerce_sync.py        | 179 ++++++--
 backend/app/services/woocommerce_writeback.py   |  93 ++++-
 backend/tests/test_mvp_hardening_api.py          |  19 +
 backend/tests/test_woocommerce_sync_api.py       |  80 +++-
 backend/tests/test_woocommerce_writeback_api.py  |  44 ++
 docs/.DS_Store                                  | Bin 10244 -> 10244 bytes
 docs/API_SPEC.md                                |  25 ++
 docs/BUILD_PLAN.md                              |  19 +
 docs/CSV_COLUMNS.md                             |  31 +-
 docs/DATABASE_SCHEMA.md                         |  18 +
 docs/DECISIONS.md                               |  25 ++
 docs/STAGING_WOOCOMMERCE_TESTING.md             |  17 +
 docs/WOOCOMMERCE_SYNC.md                        |  31 ++
 docs/ui-reference/.DS_Store                     | Bin 8196 -> 10244 bytes
 frontend/src/App.css                            |  73 ++++
 frontend/src/App.jsx                            | 527 +++++++++++++++++-------
 frontend/src/App.test.jsx                       | 100 ++++-
 27 files changed, 1297 insertions(+), 220 deletions(-)
```

That tracked diff stat is **identical to the Phase 0 baseline**: 27 files, 1,297 insertions and 220 deletions. Those production/backend/frontend/documentation changes and the unrelated untracked files existed before this task and were preserved. The only task-created paths are `docs/redesign-v2/**` and `design-system/pongo-os-v2/**`. There were no unexpected changes and **no production application file was modified by this redesign task**.

## 15. QA completed and limitation

Completed checks:

- JavaScript syntax validation with `node --check`.
- A jsdom interaction smoke test across all ten screens, the order drawer, command dialog, bulk selection, scanner success and all four state modes (zero runtime errors; exactly one `h1` per screen).
- Local HTTP checks for `index.html`, `styles.css` and `preview.js` (all returned 200).
- HTML duplicate-ID and local asset-reference checks.
- Cross-check of every referenced inline icon and every screen destination.
- Static interaction-action map review.
- Core contrast calculation.
- Presence checks for four responsive breakpoints and reduced-motion handling.
- Final artifact inventory and Git-boundary reconciliation against the recorded baseline.

Limitation: the prescribed in-app browser runtime reported **zero available browsers**, including after its documented troubleshooting check. Consequently, visual viewport screenshots, actual hover/focus rendering, 200% browser zoom and automated browser accessibility inspection could not be completed in this session. Those checks are explicitly not claimed as passed and remain required before implementation approval.
