# Pongo OS v2 — Command Nexus master design system

Status: conceptual source of truth for the isolated redesign preview. It is not connected to production code.

## Product promise

Pongo OS is the calm command layer for pet-commerce operations: dense enough for warehouse work, legible enough for management, and explicit about risk, state and auditability.

## Principles

1. **Exceptions first.** Show what needs action before general metrics.
2. **Context stays put.** Preserve module, selected entity and workflow progress during drill-down.
3. **Fast by keyboard.** Search, scan and repeat operations require no pointer.
4. **Risk is explicit.** Stock and integration mutations show scope, before/after and audit outcome.
5. **Dense, not crowded.** Use compact rows and controls inside strong grouping.
6. **One component grammar.** The same state, table and form language applies everywhere.

## Signature shell

- **Module rail:** 76 px deep-indigo spine for global domains.
- **Context rail:** 228 px module-specific destinations, queue counts and environment state.
- **Command bar:** 64 px global search/command field, current warehouse, live signals and user utilities.
- **Canvas:** 12-column fluid workspace on cool neutral `canvas-0`.
- **Detail drawer:** 420–520 px right panel; never obscures the selected-row context on wide screens.
- **Signal rail:** thin warm live-state accent used for scanning, in-progress work and warnings.

## Core tokens

```css
--pongo-950: #080a3d;
--pongo-900: #0b0e68;
--pongo-800: #0f149a;
--pongo-650: #3038cf;
--pongo-100: #e8eaff;
--pongo-50: #f3f4ff;
--live-700: #a83d12;
--live-500: #e86732;
--live-100: #ffe4d5;
--live-50: #fff6f0;
--cyan-600: #087da4;
--violet-600: #6e4bc6;
--canvas-0: #f4f5f9;
--surface-0: #ffffff;
--surface-warm: #fdfaf7;
--ink-900: #17182b;
--ink-650: #51546d;
--ink-500: #70738a;
--line-200: #dfe1ea;
--line-100: #eceef4;
--success-700: #08654d;
--success-100: #d8f3e9;
--warning-700: #8a5200;
--warning-100: #fff0c2;
--danger-700: #a52a22;
--danger-100: #fee4e2;
--info-700: #1757a6;
--info-100: #ddebff;
--focus: #5964ff;
```

- Pongo blue owns brand, selection and navigation.
- Warm orange owns live work, scanning, progress and attention—not ordinary primary buttons.
- Semantic states always include text/icon, never color alone.
- Body text must meet 4.5:1 contrast; large text and non-text controls meet WCAG AA.

## Typography

- Interface/display: `IBM Plex Sans`, then `Aptos`, `Segoe UI`, system sans.
- Identifier/numeric: `IBM Plex Mono`, then `SFMono-Regular`, `Consolas`, system mono.
- One interface family plus one identifier face only.
- Page title 28/34, section title 18/24, card title 14/20, body 14/21, label 12/16, table 13/18, metric 26/30.
- Use tabular numerics for quantities, money, order numbers and dates.

## Geometry

- Spacing: 4, 8, 12, 16, 20, 24, 32, 40.
- Radius: 8 controls, 10 compact panels, 14 cards/drawers, 18 hero/priority panels, pill only for tags.
- Borders: 1 px neutral; 2 px selection/focus; 3 px signal edge only for active operational work.
- Shadows: low-elevation `0 1px 2px rgba(14,16,50,.06)`; drawer `-16px 0 40px rgba(14,16,50,.14)`.

## Components

- Primary button: Pongo blue; one per view/region.
- Secondary button: white, neutral border; destructive action uses danger text only inside a guarded context.
- Inputs: 40 px desktop, 44 px touch; visible label; inline validation; focus ring never removed.
- Filters: query field + applied chips; advanced filters in a drawer on narrow screens.
- Data grid: 40 px rows, sticky header, sortable labels, selected-row wash, keyboard row action, contained scroll.
- Mobile records: column-priority cards with persistent identifier, status and primary action.
- Status tag: icon/shape + label; compact and sentence case.
- Drawer: routine view/edit details; modal: brief decision or guarded mutation only.
- Toast: transient confirmation; audit-impacting result also remains in the affected screen.
- Skeleton: mirrors final structure; no blank global spinner.
- Empty/error: explanation, scope and one valid recovery action.
- Charts: line for time, bar for comparison; direct labels and data-table alternative.
- Scanner: dominant focus field, current item, progress, large correct/incorrect result and manual fallback.

## Motion

- Micro feedback 120–180 ms; drawer/page/context change 220–280 ms.
- Ease-out on entry, ease-in on exit; no layout-shifting scale hover.
- Animate opacity/transform only where possible.
- Live pulse is 2.4 s and limited to one indicator per view.
- `prefers-reduced-motion: reduce` disables nonessential transitions, pulsing and smooth scrolling.

## Responsive contract

- >1260: full module and 228 px context rails; wide working canvas.
- 981–1260: full module rail, 196 px context rail, two-column working grid.
- 761–980: icon module rail; contextual rail as an overlay; compact working grid.
- ≤760: both rails off-canvas, single-column canvas, mobile record cards and full-height detail sheet.

## Never use

- Emoji as interface icons.
- Neon cyberpunk, random glow, heavy glass or all-dark data canvases.
- Static text styled with tab semantics.
- Color-only status, hover-only actions or unlabeled icon controls.
- More than one primary action in a local decision area.
- A modal for long routine browsing that belongs in a drawer or page.
