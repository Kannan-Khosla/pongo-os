# Pongo OS Visual Redesign: Master Prompt for Codex

You are performing a visual reskin of the Pongo OS frontend. This is a styling-only project. The app is feature-complete and near production. Your job is to make it look like the new Pongo OS design system without changing what it does.

## Mission

Re-theme the entire frontend in `frontend/` to the "Pongo OS Command" design language defined below. Every page, modal, table, form, and button keeps its exact current functionality, data, and text. Only appearance changes.

A live reference mockup of the target design is at `docs/ui-reference/redesign/pongo-os-preview.html`. Open it in a browser and study it before writing any code. Match the "Command" direction (the default): dark indigo sidebar and top bar, light workspace, orange used only for live/active states.

## Definition of done

1. `npm test` passes in `frontend/` with zero test modifications (see exception in Protected Surface rule 5).
2. `npm run build` succeeds.
3. Every page renders, every modal opens, every form submits, every table loads, exactly as before.
4. The app visually matches the design system below.

## Protected surface: never change these

1. **All JavaScript logic.** Hooks, state, effects, event handlers, fetch calls, `API_BASE_URL`, polling intervals, data transforms, routing logic, conditional rendering conditions. If a line contains logic, do not touch it.
2. **The backend.** Nothing outside `frontend/` may be modified, except you may read `docs/` for reference.
3. **Component names, props, and file names.** Do not rename, split, or merge `App.jsx`, `components.jsx`, or any function inside them. No refactoring into modules this pass, even though it is tempting. Reskin only.
4. **All visible text.** Headings, labels, button text, placeholder text, empty-state text, status strings, ARIA labels and roles. The test suite queries by role, text, and placeholder. Changing a label breaks a test.
5. **These CSS class names, which tests query directly:** `.nav-link` and `.nav-link.active`, `.table-wrap`, `.table-card`, `.table-scroll`, `.page-tabs` and `.page-tabs .tab`, `.pick-list-panel` and `.wide-panel`. Keep these classes on the same elements. You may add additional classes next to them, and you may fully restyle them, but the names must remain. If any other test fails after a styling change, fix your styling, not the test. The only permitted test edit is a snapshot update if a snapshot test exists, and you must call it out in your final summary.
6. **DOM order where logic depends on it.** You may add wrapper elements and classes for styling, but never remove or reorder elements that conditional logic or tests depend on. When in doubt, style the existing element instead of restructuring.
7. **No new runtime dependencies.** No Tailwind, no component libraries, no icon packages. Plain CSS plus inline SVG icons only. Google Fonts via a `<link>` in `frontend/index.html` is the single allowed external addition.

## Method: work in phases, verify after each

Run `npm test` and `npm run build` after every phase before moving on. Commit after each passing phase so you can roll back.

### Phase 0: Baseline
Run the test suite and build. Record the passing state. Take note of every page and modal in the app by reading `App.jsx` top to bottom (it contains all pages: dashboard, insights, items, inventory, locations, orders, picking, integrations, settings, and their modals).

### Phase 1: Token foundation
Create `frontend/src/tokens.css` containing the design tokens block below, verbatim. Import it in `frontend/src/main.jsx` before `App.css`. Add the fonts to `frontend/index.html`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600;650;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
```

### Phase 2: Restyle by selector, not by renaming
Rewrite the rules in `App.css` to implement the new design while keeping the existing selectors. The strategy is: the JSX already has 1,100+ classNames; change what those classes look like, not what they are called. Replace every raw hex value in `App.css` with a `var(--...)` token. When an old color has no obvious token, map it by meaning: backgrounds to surface tokens, text to text tokens, greens to success, reds to danger, ambers to warning, oranges that indicate activity to the live/orange tokens, blues to primary.

### Phase 3: Shell
Restyle the `Sidebar`, `TopHeader`, `PageHeader`, and `PageBody` components to match the mockup shell:
- Sidebar: `--ink-950` background, white logo area reading Pongo OS, nav links in `--ink-200` at 13.5px weight 500, hover `--ink-800`, active `--ink-700` background with a 2.5px `--orange-500` left edge and white text. Keep every existing nav link and its text. You may add small uppercase group eyebrows (11px, letterspaced, `--ink-400`) to visually group existing links, provided every existing link remains intact.
- Top header: 56px, `--ink-900` background, existing content restyled onto it. Notification and sync elements become chips/pills per the component spec.
- Page headers: titles in Space Grotesk 24px weight 600, meta line 13px `--text-secondary`, actions right-aligned with one primary button maximum.
- The workspace area gets `--surface-app` background with 24px padding and is the only scroll container.

### Phase 4: Core components
Apply the component specs below across all pages. Work page by page in this order: Dashboard, Orders, Picking, Inventory, Items, Locations, Insights, Integrations, Settings, then all modals.

### Phase 5: Gap filling
For any UI element that exists in the app but has no explicit spec below (a particular button, filter, badge, or panel), design it yourself using these derivation rules:
- Colors only from tokens. Never introduce a new hex value.
- Surfaces: white card, 1px `--border-default`, 12px radius, `--shadow-1`.
- Controls: 8px radius, 13px text at weight 550, 8px 14px padding minimum, visible focus ring.
- Identifiers (SKUs, order numbers, bin codes, quantities in tables, timestamps): JetBrains Mono.
- Status coloring by meaning: good/complete = success tokens, attention = warning tokens, broken/blocked = danger tokens, informational = info tokens, in-progress/live = orange tokens, neutral/inactive = neutral tokens.
- One primary action per view; everything else secondary or ghost.
- Hover states shift the surface one step; transitions 120ms to 180ms ease-out.
- When unsure, find the nearest equivalent in `docs/ui-reference/redesign/pongo-os-preview.html` and match it.

### Phase 6: Verification
Run the full test suite and build. Then start the dev server and click through every page, open every modal, submit at least one form, sort at least one table, and confirm the WooCommerce sync page renders its status correctly. Fix any visual regressions. Produce a final summary listing: files changed, test results, build result, and any deviations from this spec with reasons.

## Design tokens (paste verbatim into `frontend/src/tokens.css`)

```css
:root {
  /* brand */
  --pongo-blue-50:#EEF4FE; --pongo-blue-100:#D8E6FC; --pongo-blue-300:#7FAAF0;
  --pongo-blue-500:#1863DC; --pongo-blue-600:#1252BC; --pongo-blue-700:#0F429A;
  --pongo-blue-900:#0F149A;
  --orange-100:#FFEEDD; --orange-300:#FFB26B; --orange-500:#FD9B4D;
  --orange-600:#EF7937; --orange-700:#C95B22;
  /* ink chrome */
  --ink-950:#070A1F; --ink-900:#0B0F2E; --ink-800:#131A45;
  --ink-700:#1C2560; --ink-400:#6B74A8; --ink-200:#B9BFDE;
  /* neutrals */
  --n-0:#FFFFFF; --n-50:#F7F8FC; --n-100:#EEF0F7; --n-200:#DFE3EE;
  --n-400:#9AA1B8; --n-500:#6E7690; --n-700:#3E4560; --n-900:#171B2E;
  /* status */
  --success-500:#16A26B; --success-50:#E7F7F0; --success-700:#0E7A4F;
  --warning-500:#D9820B; --warning-50:#FDF3E3; --warning-700:#A05E04;
  --danger-500:#DE3B4B;  --danger-50:#FDEBED;  --danger-700:#B22432;
  --info-500:#0E93B4;    --info-50:#E5F6FA;
  /* semantic */
  --surface-app:var(--n-50);
  --surface-card:var(--n-0);
  --surface-inset:var(--n-100);
  --border-default:var(--n-200);
  --border-strong:#C4CADB;
  --text-primary:var(--n-900);
  --text-secondary:var(--n-500);
  --text-disabled:var(--n-400);
  --surface-chrome:var(--ink-900);
  --surface-chrome-deep:var(--ink-950);
  --chrome-hover:var(--ink-800);
  --chrome-active:var(--ink-700);
  --chrome-border:rgba(255,255,255,.08);
  --chrome-text:#FFFFFF;
  --chrome-text-dim:var(--ink-200);
  --chrome-text-faint:var(--ink-400);
  /* elevation */
  --shadow-1:0 1px 2px rgba(11,15,46,.06);
  --shadow-2:0 4px 12px rgba(11,15,46,.08);
  --shadow-3:0 12px 32px rgba(11,15,46,.14);
  --glow-live:0 0 0 3px rgba(253,155,77,.22);
  /* type */
  --font-display:"Space Grotesk",sans-serif;
  --font-ui:"Inter",sans-serif;
  --font-mono:"JetBrains Mono",monospace;
  /* shape and motion */
  --radius-control:8px; --radius-card:12px; --radius-overlay:16px; --radius-pill:999px;
  --ease-out:cubic-bezier(.16,1,.3,1);
  --dur-fast:120ms; --dur-base:180ms; --dur-slow:280ms;
}
```

## Component specs

**Typography roles.** Page titles: Space Grotesk 24px/600. Section headings: Inter 17px/650. Card titles: Inter 14px/600. Body: Inter 14px/450. Table text: Inter 13.5px/450. Labels and eyebrows: Inter 12px/550, uppercase eyebrows get 0.06em tracking. Big stat numbers: Space Grotesk 28 to 34px/650 with tabular numerals. All identifiers and table quantities: JetBrains Mono 13px/500.

**Buttons.** Primary: `--pongo-blue-500` background, white text, hover `--pongo-blue-600`, active `--pongo-blue-700` with scale(0.99). Secondary: white background, `--border-default` border, `--shadow-1`. Ghost: transparent, `--text-secondary`, hover `--surface-inset`. Danger: `--danger-500`. Live (only for actions inside an active operational task like picking): `--orange-600`, hover `--orange-700`. All: 8px radius, 13px/550 text, 8px 14px padding, 120ms transitions, focus ring `0 0 0 2px` `--pongo-blue-500` at 2px offset.

**Tables.** Container: white card, 12px radius, 1px border, overflow hidden. Header cells: `--surface-inset` background, 11px/600 uppercase letterspaced `--text-secondary`, 9px 14px padding. Body cells: 10px 14px padding, 1px bottom border. Row hover: `--surface-inset`. Selected row: `--pongo-blue-50` background with a 2.5px inset `--pongo-blue-500` left edge. Numeric columns right-aligned with tabular numerals. Keep every existing column and cell.

**Status pills.** 999px radius, 11.5px/600, 3px 10px padding, tinted background with darker text of the same hue. Map every existing status string in the app to a pill: new/pending = blue tint, allocated = blue outline, picking/in-progress/syncing = orange tint with a small pulsing dot, packed = info tint, shipped/complete/success/in-stock = success tint, low = warning tint, out/error/failed/exception = danger tint, inactive/archived = neutral tint, unmapped = dashed neutral border. Do not change the status text itself.

**Cards.** White, 1px `--border-default`, 12px radius, `--shadow-1`, 18px 20px padding. Clickable cards lift on hover: `--shadow-2` and translateY(-1px), 180ms.

**Forms and inputs.** 8px radius, 1px `--border-default`, white background, 8px 12px padding, 13.5px text. Focus: border `--pongo-blue-500` plus focus ring. Labels above fields, 12px/550. Error text `--danger-700` below the field. Keep all existing labels and validation behavior.

**Modals.** Overlay `rgba(7,10,31,.4)`. Panel: white, 16px radius, `--shadow-3`, max-width per content, header with title and close button, footer with actions right-aligned, primary on the right. Entry animation: fade plus 6px rise, 280ms ease-out.

**Tabs.** Text tabs with a 2px `--pongo-blue-500` underline on the active tab, active text `--pongo-blue-500`, inactive `--text-secondary`, counts in mono 11px.

**Filters and toolbars.** Applied filters render as chips: `--pongo-blue-50` background, `--pongo-blue-500` text, 999px radius, with a removal x. Search inputs get a leading search icon.

**Notifications and toasts.** Toast: dark `--ink-900` surface, white text, 12px radius, `--shadow-3`, status-colored leading dot. Alert banners: status-50 background, status-700 text, 1px status-tinted border, 10px radius.

**Sync and live indicators.** Anything representing an in-progress sync or live operation gets a 7px orange dot with a soft glow and a 1.6s opacity pulse. The app's WooCommerce sync status display becomes a chip: `--chrome-hover` background on dark surfaces or white card on light, showing a status dot plus concise text.

**Empty states.** Centered, 90px vertical padding: a 64px rounded glyph tile on `--surface-inset`, Space Grotesk 19px heading, 13.5px `--text-secondary` explanation, one primary action button.

**Motion rules.** 120ms hover, 180ms reveals, 280ms overlays, all `--ease-out`. Loading skeletons over spinners where a spinner currently exists in a table or card context: `--surface-inset` blocks with a 1.4s shimmer. Respect `prefers-reduced-motion` by disabling shimmer and pulses.

**Accessibility floor.** Never remove focus outlines. Text on tinted pills uses the -700 shade of its hue. Body text minimum 13px. Status is always dot plus text, never color alone. Interactive targets minimum 34px on desktop surfaces.

## Final report

End with: list of files changed, confirmation that tests and build pass, screenshots or descriptions of each redesigned page, and an explicit list of any place you deviated from this spec and why.
