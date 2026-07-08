# Frontend QA Checklist

Use this checklist before calling a Pongo Inventory OS frontend pass complete.

## Visual And Layout

- No horizontal body/page overflow at laptop widths around 1440px and 1280px.
- Sidebar and topbar align; content does not hide behind the sidebar.
- Pongo blue `#0f149a` is the primary brand color.
- Soft peach (`#FFF3EC`/`#FCE9D9`) is used for secondary surfaces and accents.
- Buttons use consistent primary, muted, action, icon, and disabled states.
- Tables are inside `.table-scroll` containers, not widening the whole page.
- Empty, loading, error, and disabled states are visible and readable.
- Forms use aligned labels above fields and consistent spacing.
- Phase 1 polish uses the existing React/Vite app and does not rewrite routing,
  backend behavior, auth, or WooCommerce writeback.
- Core polish classes are `.btn`, `.btn-primary`, `.btn-secondary`,
  `.btn-danger`, `.btn-ghost`, `.btn-soft`, `.btn-sm`, `.btn-md`,
  `.btn-icon`, `.btn-disabled`, `.btn-group`, `.action-bar`,
  `.table-card`, `.table-toolbar`, `.table-scroll`, `.data-table`,
  `.table-actions`, `.table-footer`, `.table-empty`, `.status-pill`,
  `.form-card`, `.form-grid`, `.form-row`, `.field`, `.field-label`,
  `.input`, `.select`, `.textarea`, `.filter-card`, `.filter-grid`,
  `.filter-actions`, `.help-text`, and `.error-text`.
- Tables may scroll inside their table card; the page itself should not
  horizontally scroll.

## Interaction Rules

- Every visible action button works, opens a real modal, navigates somewhere
  real, or is intentionally disabled.
- No fake future controls are left clickable.
- Placeholder future controls must be disabled with `title="Not available yet"`.
- Barcode scanners are treated as keyboard input across Pongo OS. Search and
  filter text fields that have Apply/Search/Refresh actions should submit on
  Enter so staff can scan a SKU/barcode directly into the current page.
- Reports render only the selected report, not all report tables at once.
- Items detail keeps stock-changing actions routed to receiving, transfer,
  adjustment, or cycle count workflows.
- Orders uses Zenventory-style sidebar sub-navigation. Open Orders, Allocate
  Orders, Pick Orders, Fulfillment, Completed Orders, and Order History are
  separate views, not one dumped screen.
- Pick Scanner belongs only inside Pick Orders.
- Allocation, pick, and fulfillment history sections belong inside Order
  History, not Open Orders.

## Commands

```bash
cd frontend
npm run build
npm test -- --run
```

```bash
backend/.venv/bin/python -m pytest backend/tests -q
```

Record both frontend commands and the backend pytest result before marking the
frontend QA pass complete.

## Pages To Inspect

- Dashboard
- Items
- Inventory
- Locations
- Receiving
- Scanner
- Orders
- Cycle Count
- Reports
- Settings
- Routes

For each page, confirm consistent buttons, polished inputs/selects, table
overflow contained inside cards, visible empty/loading/error states, no default
purple Quick Action links, and no dominant old teal/coral styling.
