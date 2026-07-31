# Pongo OS redesign v2 — read-only baseline

Captured on 2026-07-17 before any redesign artifact was created.

## Repository structure

| Area | Purpose | Notes |
| --- | --- | --- |
| `frontend/` | React staff interface | Vite, React 19, hash navigation, Lucide React |
| `backend/` | FastAPI operational API | SQLAlchemy, Alembic, PostgreSQL target; local SQLite supported |
| `docs/` | Product, API, workflow, and UI references | Includes Zenventory workflow screenshots used only as reference |
| `design-system/` | Conceptual design-system artifacts | The v2 source of truth is isolated under `design-system/pongo-os-v2/` |

The codebase knowledge graph was already indexed as `pongoOS` (2,841 nodes, 13,916 edges). It reports 154 source files, with the frontend concentrated in four JavaScript/JSX files, one CSS file, and one HTML entry point.

## Frontend stack and entry points

- Build: Vite 7 (`frontend/vite.config.js`).
- Runtime: React 19 and `react-dom` 19.
- Icons: `lucide-react`.
- Tests: Vitest 4, jsdom, Testing Library, `@testing-library/jest-dom`, and `@testing-library/user-event`.
- HTML entry: `frontend/index.html` → `frontend/src/main.jsx` → `frontend/src/App.jsx`.
- Global styles: `frontend/src/App.css`.
- Small exported primitives: `frontend/src/components.jsx` (`Button`, `DataTable`, `FilterBar`).
- Routing: custom `window.location.hash` parsing in `parseHashRoute`; no router dependency.
- Application shell: `App` → `Sidebar`, `TopHeader`, `PageHeader`, `PageBody`.
- API boundary: browser calls the Pongo backend through `VITE_API_BASE_URL`; no direct WooCommerce browser access.

## Frontend size at baseline

| File | Lines | Role |
| --- | ---: | --- |
| `frontend/src/App.jsx` | 10,979 | Routes, API state, pages, workflows, components, formatting, CSV exports |
| `frontend/src/App.css` | 5,193 | Tokens, shell, page-specific styles, state and responsive rules |
| `frontend/src/App.test.jsx` | 1,048 | 39 UI behavior tests |
| `frontend/src/components.jsx` | 41 | Three simple shared primitives |
| `frontend/src/main.jsx` | 10 | React bootstrap |
| `frontend/src/test/setup.js` | 5 | Test setup |

## Local launch readiness

`frontend/node_modules/` is present and `npm run dev` is configured for `127.0.0.1`. The shell can launch without changing configuration. Data-backed views still need the FastAPI service at the configured API base URL; otherwise their existing error and empty states appear. No production build was run because that would rewrite `frontend/dist/`, outside the permitted artifact directories.

## Pre-existing uncommitted changes

These changes existed before the redesign task and were preserved:

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
?? docs/CODEX_REDESIGN_PROMPT.md
?? docs/FIRST_TIME_WOO_MIGRATION.md
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.12 PM.png
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.19 PM.png
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.25 PM.png
?? docs/ui-reference/pongo-os/Screenshot 2026-07-12 at 8.53.45 PM.png
?? docs/ui-reference/redesign/
```

The exact Unicode filename rendering for four screenshots is normalized above for readability. Git remains the source of truth.

## Files reviewed

- Complete frontend surface: `index.html`, `main.jsx`, `components.jsx`, `App.jsx`, `App.css`, `App.test.jsx`, test setup, package manifest, and Vite config.
- Product and workflow sources: `README.md`, `docs/UI_REFERENCE.md`, `docs/FRONTEND_QA.md`, `docs/ORDER_WORKFLOW.md`, `docs/INSIGHTS.md`, `docs/BUSINESS_DASHBOARD.md`, `docs/PRD.md`, `docs/MIGRATION_MAP.md`, `docs/API_SPEC.md`, and relevant CSV/database decisions.
- Reference assets: `docs/ui-reference/pongo-os/` and `docs/ui-reference/zenventory_images/`. These are Zenventory workflow references, not current Pongo visual identity.
- Graph discovery: all frontend render functions, entry points, route handling, state loaders, and major component relationships.

## Audit limitations

- The frontend and CSS contained substantial pre-existing edits, so this audit describes the working tree, not only committed `HEAD`.
- No real WooCommerce credentials, customer data, or live API data were inspected.
- Reference screenshots show the prior Zenventory inspiration. Repository source and documentation—not those screenshots—define current Pongo behavior.
- Placeholder destinations are recorded as placeholders rather than treated as implemented capabilities.
