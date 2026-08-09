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
- Settings must show WooCommerce staging status, the dry-run/live badge, the
  staging-only writeback warning, and `Dry Run Send` or `Send to Staging`
  labels without displaying secrets.
- Settings may show whether the WooCommerce webhook receiver is enabled,
  configured, and its last safe delivery status, but must never show the
  webhook secret.
- The internal new-order notice fits within the viewport at laptop and mobile
  widths and does not cause horizontal page overflow.

## Interaction Rules

- Every visible action button works, opens a real modal, navigates somewhere
  real, or is intentionally disabled.
- No fake future controls are left clickable.
- Placeholder future controls must be disabled with `title="Not available yet"`.
- Barcode scanners are treated as keyboard input across Pongo OS. Search and
  filter text fields that have Apply/Search/Refresh actions should submit on
  Enter so staff can scan a SKU/barcode directly into the current page.
- Items and every Inventory subpage provide an on-demand phone-camera scanner
  for QR, UPC, EAN, and Code 128 values. It must prefer the rear camera,
  require HTTPS outside local development, stop the camera when closed, and
  pass the decoded value immediately through the current page's existing
  search without changing stock.
- The phone-camera scanner must show actionable permission/device errors and
  keep a manual SKU/barcode search fallback available. Validate it on current
  iPhone Safari and Android Chrome before each production release that changes
  the scanner or authentication flow.
- Reports render only the selected report, not all report tables at once.
- Insights renders only the selected dashboard tab, loads tab data on demand,
  shows data quality warnings, and does not show fake export buttons.
- Dashboard is the business home page. Inventory Overview is the renamed
  operational command center and must remain reachable from the sidebar.
- Items detail keeps stock-changing actions routed to receiving, adjustment,
  or cycle count workflows. Transfer UI is hidden from active frontend
  workflows.
- Inventory uses sidebar subpages, not top tabs: All Inventory, Inventory by
  Location, Low Stock, Expiring Stock, Par Level, and Stock Movements.
- Orders uses Zenventory-style sidebar sub-navigation. Open Orders, Allocate,
  Pick Orders, Completed Orders, and Order History are separate views, not one
  dumped screen.
- Pick Orders uses an arrow-driven order queue and a focused manual quantity
  sheet. It must not require barcode scanning or show a claim control.
- Pick Orders is an inline page rather than a modal/card overlay. Its queue
  omits order source, state, SKU, and allocated columns, and fully picked orders
  disappear from the queue.
- Pick Orders rows are selectable and the bulk Actions menu contains only Pick
  Selected and Unpick Selected. Open Orders rows are selectable and its bulk
  menu contains Mark as completed, Print, and Unpick all.
- Orders sidebar subpage links update the route and active state immediately on
  one click. Each subpage loads only its own required data, and stale Open
  Orders responses must not overwrite the Pick Orders queue.
- Allocate paginates Orders by exception line and Items by complete item group.
  Item totals and affected-order drill-downs must never be split by a line-page
  boundary; its export always contains the complete applied filter.
- Open Orders uses the Zenventory-style Open Customer Orders composition:
  dedicated order/customer/item/warehouse filters, Search/Clear, record and
  page-size rails, a dark Filters/Actions band, a table rendered directly in
  the page flow, a body-level row action menu, and an accessible printable
  customer-order dialog. The table has no nested scrollbar; narrow viewports
  render each order as an inline responsive card. The grid
  omits Order Source, Company, State, ZIP, Ship From, and Shipped columns.
- Allocation, pick, and legacy fulfillment/completion history sections belong
  inside Order History, not Open Orders.
- The first event request uses `initialize=true` and establishes the current
  cursor without showing stale notifications. Later polling uses
  `after_id=next_after_id`, drains while `has_more=true`, and never skips a
  paginated event by jumping directly to `latest_event_id`.
- The event feed is polled globally every 15 seconds while the document is
  visible and on focus/visibility changes. A later newly created order shows
  one internal staff notice; replayed deliveries and repeated feed reads must
  not show it again.
- The new-order notice uses a polite, atomic live region, has visible Dismiss
  and View Open Orders actions, does not auto-dismiss, and does not move focus
  away from a scanner or text input.
- Multiple unseen order events may be grouped into one notice. Dismissing a
  notice must not move the webhook cursor backward or make it reappear.
- The header Bell shows the unread order count and session-only notification
  history. Opening it marks current alerts read, Escape/Close dismisses the
  popover, and its View Open Orders action closes the popover.
- A quick-sync result with nonzero `created_count` produces a fallback notice;
  repeating the same `sync_run_id` must not announce it twice.
- The notice is local Pongo UI feedback only. It must not call WooCommerce,
  request browser-notification permission, or send customer email/SMS/push.

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
- Inventory Overview
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
- Insights

For each page, confirm consistent buttons, polished inputs/selects, table
overflow contained inside cards, visible empty/loading/error states, no default
purple Quick Action links, and no dominant old teal/coral styling.
