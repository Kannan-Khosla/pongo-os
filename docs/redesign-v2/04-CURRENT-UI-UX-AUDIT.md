# Current UI/UX audit

## Executive diagnosis

Pongo OS already contains unusually complete operational workflows and generally good safety copy. Its primary design debt is structural: the interface grew page by page around a fixed Zenventory-inspired shell, so mature capabilities now compete inside a navigation and component language sized for an earlier inventory MVP.

## Ranked findings

| Severity | Finding and repository evidence | User impact | Recommended design response |
| --- | --- | --- | --- |
| **Critical** | **Global shell does not adapt to mobile.** `.sidebar` stays 280 px with no shell-level media rule; `.app-shell` remains a row and `body` hides horizontal overflow in `App.css`. | Small screens lose usable workspace even where individual tables adapt. | Replace with desktop module/context rails, tablet rail, and mobile off-canvas navigation; validate 320–1440 px. |
| **Critical** | **Modal focus is incomplete.** `OpenOrderDetailPanel` receives initial focus and Escape handling, but most `import-modal` instances lack focus trap, return focus and Escape behavior. | Keyboard and screen-reader users can move behind dialogs or lose their place. | One modal/drawer primitive with focus trap, inert background, initial/return focus, Escape and scroll containment. |
| **High** | **No reduced-motion contract.** `App.css` contains transitions and live animation patterns but no `prefers-reduced-motion`. | Motion-sensitive users cannot opt out; future motion would amplify the gap. | Define reduced-motion tokens and disable nonessential transforms/pulses. |
| **High** | **Navigation overload and weak architecture.** `navItems` has 13 top-level entries plus 11 Inventory/Orders children; Settings contains a complete Woo console. | Users must remember where operational work, analysis and configuration live. | Group into Command, Operations, Intelligence and System; use contextual second-level navigation. |
| **High** | **Dashboard identity is split.** `#dashboard` is the business dashboard while `#inventory-overview` renders the operational “Command Center”. | “Dashboard”, “Command Center”, and “Inventory Overview” do not establish one clear home. | Make Command Center the home with Business and Operations lanes; keep deep dashboards in Intelligence. |
| **High** | **Multiple visual dialects.** General `.content-panel`/`TableShell`, `.items-page-pro`, `.business-*`, `.zen-orders-*`, pick workspace and report-specific layouts coexist in one CSS file. | Moving between modules feels like changing products; interaction rules must be relearned. | One shell, one table grammar, one form grammar, and explicit workflow templates. |
| **High** | **Static elements use tab semantics.** `PageHeader` renders noninteractive strings as `<span role="tab">`; several header “tabs” are descriptive phases, not navigation. | Screen readers receive false interaction cues. | Use links/buttons only for real tabs; use a stepper or plain labels for process stages. |
| **High** | **Action hierarchy is frequently flat.** Items presents up to eight peer actions; Settings and Routes expose multiple preview/commit/refresh actions simultaneously. | Routine users must parse high-risk and low-risk actions on every visit. | One primary action per view, secondary actions nearby, rare/bulk/safety actions in scoped menus or guarded sheets. |
| **High** | **Settings misrepresents scope.** `WooCommerceSettingsPage` includes catalog sync, order sync, writeback queue, remap and run history under the generic Settings route. | Integration operations are hard to find and system settings appear absent. | Move WooCommerce to Integrations; reserve Settings for profile, warehouses, preferences and safety policy. |
| **High** | **Tables are implemented several ways.** `TableShell`, `DataTable`, `InventorySummaryTable`, `ReceivedInventoryTable`, `OpenOrdersTable`, pick tables and preview tables duplicate structure. | Sorting, mobile behavior, empty/loading states and action placement vary. | Canonical data-grid pattern with density, sticky headers, selection, mobile card fallback and state slots. |
| **High** | **Error recovery is inconsistent.** Most API failures become a top-level `.api-error` strip; field errors are usually aggregated and retry is not always adjacent. | Users may not know what to correct and can lose workflow momentum. | Inline validation, retained input, retry beside failed region, and recovery guidance. |
| **Medium** | **Information density lacks priority.** Dashboard metric strips, report summaries and Settings safety cards give many values equal size and weight. | Exceptions and next actions are slower to spot. | Use priority lanes, smaller supporting metrics and progressive disclosure. |
| **Medium** | **Typography relies heavily on bold weight.** Sidebar links, labels, metrics and helper text often use 700–900 weights; page title scale is modest. | Hierarchy becomes weight-only and dense pages feel louder than necessary. | Use a disciplined type scale, regular body copy, medium labels, tabular numerics and fewer all-caps accents. |
| **Medium** | **Warm accent has no semantic job.** Peach is used for page background, tab hover, nav indicator, badges and decorative gradients. | Brand accent does not consistently communicate live/active work. | Reserve warm orange/peach for live operations, scan focus, progress and attention. |
| **Medium** | **Responsive behavior is page-specific.** Open Orders becomes cards at 900 px, while many other tables only scroll and the shell never changes. | Mobile behavior is unpredictable by module. | Define table adaptation by column priority and a shared responsive shell. |
| **Medium** | **Scanner feedback is too quiet.** `ScannerResult` appears below forms and exposes raw response JSON as a routine disclosure. | Warehouse users may not recognize pass/fail instantly and see implementation detail. | Large success/error field, text + icon + tone, persistent current item, optional diagnostics. |
| **Medium** | **Long pages lose context.** Receiving, cycle count, routes, settings and history vertically stack entry, summary, tables and detail. | Users scroll away from the action, selected entity or completion state. | Split workspaces, sticky session summaries and right-side detail panels. |
| **Medium** | **Future placeholders resemble real screens.** Categories, Commodities, Location Stock and Expiring Stock are routable. | Users can mistake roadmap items for broken features. | Remove from primary navigation or show an explicit capability-status page. |
| **Low** | **Product identity is still inventory-specific.** Brand mark is “PI” and subtitle is “Inventory OS”. | The shell undersells expansion into orders, fulfilment, intelligence and routes. | Use “Pongo OS” and a distinctive Pongo glyph/wordmark treatment. |
| **Low** | **Legacy copy remains.** Allocation history says “Picking is not built yet” although Pick Orders exists. | Trust erodes when status copy is stale. | Add content QA and centralize workflow terminology. |

## Current strengths to preserve

- Pongo blue is already centralized as a token and focus states are visible.
- Most interactive elements are native buttons, links, inputs and labels.
- Wide tables are generally contained rather than causing body-level overflow.
- Empty tables communicate their state instead of leaving blank space.
- Scanner Enter behavior, input modes and native date controls support operational speed.
- Stock, allocation, pick, completion and Woo writeback safety boundaries are clearly explained.
- Preview-before-commit exists in receiving, cycle count, sync, remap, allocation and routes.
- New-order notifications provide both transient feedback and persistent history.

## Root design response

The redesign does not need more component types. It needs fewer, clearer screen patterns: command center, queue + detail, operational session, entity workspace, report canvas, audit ledger and settings/integration form. Those seven patterns cover nearly every current route.
