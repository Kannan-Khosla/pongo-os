# UI/UX Pro Max research

## Required design-system search

Query:

```text
enterprise commerce operating system inventory orders fulfilment analytics futuristic technical vibrant premium data dense
```

The installed skill returned:

- Pattern: **Enterprise Gateway**. Its marketing-site structure was rejected for the staff application, but the role/industry path idea informed contextual navigation.
- Style: **Data-Dense Dashboard** with compact grid, KPI cards, tables, filters, row highlighting, tooltips and loading feedback.
- Palette recommendation: primary `#1E40AF`, secondary `#3B82F6`, amber CTA `#F59E0B`, background `#F8FAFC`, blue text.
- Typography: Fira Code + Fira Sans for technical data precision.
- Anti-patterns: ornate treatment and absent filtering.
- Delivery checks: SVG icons, 150–300 ms feedback, 4.5:1 contrast, visible focus, reduced motion and 375/768/1024/1440 responsive verification.

## Focused searches

| Domain / query | Returned guidance | Pongo interpretation |
| --- | --- | --- |
| `product`: enterprise SaaS operations command center inventory fulfilment | SaaS data-dense and real-time monitoring; trust blue with accent contrast | Use enterprise clarity, but avoid marketing gateway patterns in the app |
| `style`: industrial utilitarian data dense futuristic premium | Data-Dense Dashboard, Drill-Down Analytics, Real-Time Monitoring; HUD and liquid-glass also appeared | Select the first three; reject HUD neon, vaporwave, skeuomorphism and heavy glass for accessibility/fit |
| `color`: indigo blue warm orange enterprise SaaS dashboard | Trust blue/indigo plus orange/amber CTA families | Anchor on required `#0F149A`; reserve warm accent for live work, not generic decoration |
| `typography`: technical enterprise readable dense interface | Lexend + Source Sans 3, Inter, Fira Code + Fira Sans, IBM Plex Sans | Use IBM Plex Sans-style technical clarity with a mono identifier face; avoid all-mono headings |
| `ux`: data tables, filters, drawers, modals, keyboard, accessibility, responsive | Mobile table cards/scroll; logical keyboard order; skip link; bulk selection; visible focus; input modes | Becomes the shared grid, skip link, 44 px targets and keyboard contract |
| `ux`: scanner feedback, loading, empty, error, operational status, motion | Feedback after 300 ms, actionable empty/error states, aria-live errors, reduced motion, one or two key animations | Large scan result, skeletons, retry actions and restrained live pulse |
| `chart`: inventory revenue orders trend forecasting comparison | Line for time trends; bar for category comparison; radar only with caution and table alternative | Use line/sparkline and horizontal bars; omit radar from the preview |
| `web`: semantic keyboard modal responsive data table focus | Native elements, semantic input types, confirm destructive actions, visible focus, inline errors | No clickable divs; dialog focus discipline; field-level validation |
| `html-tailwind` stack: dashboard forms tables responsive accessibility | Reduced motion, focus-visible, consistent 40 px inputs | Applied in vanilla CSS; no Tailwind or runtime dependency added |
| `react`: dashboard performance state hooks large tables | Conditional loading, derived state, lazy initialization | Recorded for a future implementation; not relevant to static prototype code |

No focused search used fabricated recommendations. The installed database did not document an `icons` or `gsap` domain in its supported domain list, so those were not treated as authoritative sources. The existing Lucide icon family and CSS-native motion are the minimal, consistent choices.

## Selected synthesis

Design dials:

- Variance **8/10**: materially different shell, navigation and workspace composition.
- Motion **6/10**: controlled page, drawer, toast, selection and live-state motion.
- Density **8/10**: 40 px rows, compact filters and high information visibility with strong grouping.

Applied recommendations:

1. Data-dense 12-column workspace and compact operational components.
2. Drill-down navigation that preserves context in a secondary rail and detail drawer.
3. Real-time status signals using text, icon and restrained warm accent.
4. Line and bar visualizations with values/labels and non-color alternatives.
5. Canonical responsive table behavior instead of per-page improvisation.
6. Semantic controls, visible focus, reduced motion and actionable state surfaces.

Rejected recommendations:

- Enterprise marketing gateway structure, contact-sales CTAs and logo carousels.
- Neon HUD, vaporwave, gaming cues, thin glowing lines and all-dark workspaces.
- Heavy glass, animated blur and effects that reduce contrast or performance.
- All-monospace typography or orange as a general-purpose primary action color.
