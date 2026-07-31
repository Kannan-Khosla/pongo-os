# Pongo OS v2 design language

## 1. Foundation

### Brand philosophy

Pongo OS is a confident operating layer rather than a generic dashboard. The interface should make staff feel that every order, item, stock movement and integration event is part of one coherent operational system. Its visual signature is the contrast between a deep-indigo command frame and a bright, precise work canvas, crossed by a restrained warm “signal” for active work.

### Design principles

1. Exceptions before summaries.
2. Preserve context during drill-down.
3. Optimize repeat work for keyboard and scanner input.
4. Communicate operational consequence before committing.
5. Keep density inside clear zones.
6. Use the same interaction grammar in every module.

### Surface hierarchy

| Level | Token | Use |
| --- | --- | --- |
| Chrome | `pongo-950`, `pongo-900` | Module and contextual navigation |
| Canvas | `canvas-0` | Page background and inter-panel space |
| Base | `surface-0` | Tables, forms, ordinary cards |
| Warm | `surface-warm` | Receiving, scanning and active-session context |
| Raised | white + drawer shadow | Drawers, menus, guarded dialogs |
| Selected | `pongo-50` + `pongo-650` edge | Selected row, active view, focused entity |

### Complete color tokens

| Family / token | Value | Purpose |
| --- | --- | --- |
| `pongo-950` | `#080A3D` | Deepest chrome |
| `pongo-900` | `#0B0E68` | Context navigation |
| `pongo-800` | `#0F149A` | Required Pongo brand anchor, primary action |
| `pongo-650` | `#3038CF` | Hover/selected emphasis |
| `pongo-100` | `#E8EAFF` | Selected surface |
| `pongo-50` | `#F3F4FF` | Quiet brand wash |
| `live-700` | `#A83D12` | Accessible live/attention text |
| `live-500` | `#E86732` | Active operational rail and graphic accent |
| `live-100` | `#FFE4D5` | Scan/progress surface |
| `live-50` | `#FFF6F0` | Warm workspace surface |
| `cyan-600` | `#087DA4` | Informational data series |
| `violet-600` | `#6E4BC6` | Secondary data series |
| `canvas-0` | `#F4F5F9` | App canvas |
| `surface-0` | `#FFFFFF` | Main component surface |
| `surface-warm` | `#FDFAF7` | Operational session surface |
| `ink-900` | `#17182B` | Primary text |
| `ink-650` | `#51546D` | Secondary text |
| `ink-500` | `#70738A` | Caption/disabled copy only at sufficient size |
| `line-200` | `#DFE1EA` | Standard border |
| `line-100` | `#ECEEF4` | Table separator |
| `success-700/100` | `#08654D` / `#D8F3E9` | Complete, correct scan, connected |
| `warning-700/100` | `#8A5200` / `#FFF0C2` | Review, partial, waiting |
| `danger-700/100` | `#A52A22` / `#FEE4E2` | Error, blocked, destructive consequence |
| `info-700/100` | `#1757A6` / `#DDEBFF` | Informational and read-only states |
| `focus` | `#5964FF` | 3 px focus ring with 2 px offset |
| `disabled` | `#ECEEF4` / `#8A8DA0` | Disabled surface/text; status also stated |

Hover darkens the owning family; active adds a 1 px inset; selected uses both fill and leading edge. Orange never becomes a generic success or primary button color.

### Typography

Use one interface family and one identifier family:

- Interface/display: `IBM Plex Sans`, `Aptos`, `Segoe UI`, system sans.
- Monospace: `IBM Plex Mono`, `SFMono-Regular`, `Consolas`, system mono.

| Role | Size / line / weight | Notes |
| --- | --- | --- |
| Page title | 28 / 34 / 600 | One `h1`; sentence case |
| Section title | 18 / 24 / 600 | Clear section landmarks |
| Card title | 14 / 20 / 600 | Avoid all-caps |
| Body | 14 / 21 / 400 | Default UI prose |
| Small body | 13 / 18 / 400 | Tables and compact metadata |
| Label | 12 / 16 / 550 | Persistent above controls |
| Eyebrow | 11 / 14 / 600 | 0.08 em tracking; sparing use |
| Button | 13 / 18 / 600 | Action-first wording |
| Table header | 11 / 16 / 600 | Sentence case; sortable icon |
| Table cell | 13 / 18 / 400 | 40 px row target |
| Identifier | 12 / 18 / 500 mono | SKU, barcode, order, route IDs |
| Metric | 26 / 30 / 600 | Tabular numerals |
| Caption | 12 / 17 / 400 | Never lighter than `ink-650` on white |

### Spacing, grid and geometry

- Spacing scale: 4, 8, 12, 16, 20, 24, 32 and 40 px.
- Desktop canvas: 12 columns, 16 px gap; max comfortable content width 1,680 px, but tables may use the full canvas.
- Tablet: 6 columns; mobile: 4 then 1 content column.
- Control heights: 40 px desktop, 44 px touch; compact icon buttons remain 40/44 px hit targets.
- Radius: 8 controls, 10 compact panels, 14 cards/drawers, 18 priority panels; pills only for tags.
- Border: 1 px neutral; selection/focus 2–3 px; no decorative thick outlines.
- Shadow: low elevation for cards; directional shadow for drawers; none on every table row.
- Gradient: deep indigo chrome only; one restrained orange-to-peach signal gradient for active operations.
- Iconography: Lucide-style 20 px outline icons, 1.75 stroke; 16 px in compact controls, 24 px in module rail. No emoji.
- Illustration: abstract operational diagrams only in large empty states; never decorative pet mascots in dense work areas.
- Charts: line/area for trends, horizontal bars for ranking, stacked bars for workflow stages; direct values and table alternative.

## 2. Layout system

### Desktop shell

The 76 px module rail holds global domains. The 228 px contextual rail exposes destinations within the selected domain and a compact environment/status footer. A 64 px command bar spans the workspace. Page content begins with breadcrumb, title, short status line and one primary action. A drawer opens beside content at 420–520 px when space permits.

### Tablet and mobile

- 981–1260 px: module rail remains icon-first; contextual navigation opens as an overlay; two-column cards remain where useful.
- 761–980 px: contextual navigation is off-canvas while the module rail remains available.
- At 760 px and below: both rails become an off-canvas sheet, the command search compacts, content becomes single-column, and data tables become column-priority record cards.
- Tables retain identifier, status, essential quantities and primary action. Secondary data remains available through record expansion.
- No fixed-height content panes that trap the viewport; drawers and modals use `max-height: 100dvh` and internal scrolling.

### Screen patterns

1. **Command Center:** priority lanes and supporting metrics.
2. **Queue + detail:** orders, items, exceptions, audit.
3. **Operational session:** receiving, picking, cycle count, scanner.
4. **Entity workspace:** item, location, order, route.
5. **Report canvas:** report library, filters, summary, chart/table.
6. **Integration console:** environment banner, runs, queue, audit.
7. **Settings form:** local navigation, grouped fields, sticky save state.

## 3. Component language and states

| Component | Treatment | Hover / active / focus | Disabled / loading / error / selected |
| --- | --- | --- | --- |
| Button | Pongo primary, border secondary, quiet/ghost, danger inside guarded context | Darken only; 1 px active inset; 3 px focus ring | Disabled label remains readable; spinner precedes stable label; no width shift |
| Icon button | 40/44 px square, 8 px radius, tooltip and label | Neutral wash; pressed background | Disabled at 45% with title; destructive icon never stands alone |
| Input/select | Visible label, 40/44 px control, 8 px radius | Border `pongo-650`; focus ring | Disabled neutral fill; inline error below and `aria-describedby`; valid state is not shown by green alone |
| Search | Command/search icon, clear control, scanner Enter support | Suggestion row highlight | Loading suggestion skeleton; no-results guidance; scan mode has live signal edge |
| Filters/chips | Essential filters inline; advanced in sheet | Chip remove button visible | Applied chips persist; invalid combinations explained |
| Card/metric | Fine border, clear title/value/caption; priority cards use signal edge | Subtle border color only if interactive | Skeleton matches card; critical metric uses icon/text, not fill alone |
| Data table | Sticky header, 40 px rows, contained scroll, selection checkbox, row menu | Row wash; keyboard row focus | Loading skeleton rows; empty/error full-width state; selected leading Pongo edge |
| Status tag | Icon/shape + sentence-case label | Tooltip only for extra detail | Semantic family; live tag may pulse unless reduced motion |
| Tabs/segments | Real buttons/links with active underline/fill | Clear hover and focus | Disabled stated; static phase labels become stepper, not tabs |
| Modal | Short decision or guarded mutation, 480–680 px | N/A | Focus trap, Escape, return focus; destructive consequence summary |
| Drawer | Routine detail/edit, 420–520 px desktop, full-height mobile | N/A | Loading skeleton, error with retry; selected row remains visible where possible |
| Tooltip | 300 ms intent delay, concise text | Appears on hover/focus | Never contains required information only |
| Toast | Bottom-right desktop, bottom mobile, 4–6 s | Pause on hover/focus | `aria-live`; errors persist until dismissed; audit result also remains in view |
| Alert | Icon, title, explanation, action | Action follows button pattern | `role=alert` for errors, `status` for nonurgent updates |
| Empty/error | Compact illustration/icon, reason, one valid next action | Action follows button pattern | Filter-empty differs from system-empty; retry retains input |
| Pagination | Result range, page size, previous/next; cursor variant where needed | Native control feedback | Disabled ends announced; mobile uses Load more when simpler |
| Chart | Direct labels, restrained grid, Pongo/cyan/violet series | Tooltip and series focus | Empty explanation; data table alternative; patterns/markers differentiate series |
| Scanner | Large focused field, current item, progress, success/failure stage | Scan field signal edge | Correct/incorrect text, icon and color; manual fallback; recent history |
| Command menu | Search destinations/actions, grouped by module | Arrow-key active row | Escape closes and returns focus; unavailable actions explain why |
| Integration panel | Environment and read/write state at top; run timeline | Row/detail hover | Blocked/failed actions show guard reason and recovery |
| Activity timeline | Immutable event cards along a rule | Focusable event opens detail | Type/status icon + text; empty state names expected events |
| Progress indicator | Step name, completed/current/upcoming, quantity fraction | N/A | Error attaches to step; live pulse optional; reduced motion static |

## 4. Motion language

- Navigation selection: 160 ms color and signal-edge transition.
- Page context: 220 ms fade/translate by 8 px; no full-screen choreography.
- Drawer: 240 ms ease-out entry, 180 ms ease-in exit.
- Modal: 180 ms opacity + 6 px translate; background fades separately.
- Table selection: 140 ms background/edge transition.
- Status update: 220 ms highlight wash, then stable state.
- Loading: skeleton shimmer only when motion is allowed; static gradient otherwise.
- Scanner: one 220 ms result flash and optional 2.4 s live pulse.
- Toast: 220 ms slide/fade, no bounce.
- Expand/collapse: 200 ms opacity/grid-row transition where supported.
- `prefers-reduced-motion: reduce` removes transforms, pulse, shimmer and smooth scrolling; state changes remain immediate and readable.

## 5. Accessibility requirements

- WCAG 2.2 AA contrast and 44 px touch targets at touch breakpoints.
- One `h1`, logical headings and named landmarks per screen.
- Skip link before the shell; keyboard order follows the visual hierarchy.
- Status never relies on color; charts use labels/markers and a table alternative.
- Dialog focus trap, initial focus, Escape, inert background and return focus.
- Input labels are persistent; errors are inline and announced.
- Tables use captions, scoped headers and mobile labels.
- Destructive/stock-changing actions provide confirmation and a reversible exit before commit.
