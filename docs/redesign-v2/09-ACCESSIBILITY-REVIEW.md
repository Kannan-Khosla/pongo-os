# 09: Accessibility Review

Review of the proposed design language (07) and the interactive preview against WCAG 2.1 AA and the ui-ux-pro-max accessibility rules. Structure: what the design guarantees, how the preview demonstrates it, and open concerns for implementation.

## 1. Contrast

- Workspace text: `--ink` (`#17182B`) on white is 17.47:1; secondary `--ink-650` (`#51546D`) is 7.40:1; caption `--ink-500` (`#70738A`) is 4.66:1. All pass AA at the sizes used in the preview.
- Chrome text: white on `--pongo-900` (`#0B0E68`) is 16.45:1. Reduced-opacity chrome labels are decorative grouping cues duplicated by full-size navigation labels.
- Primary actions: white on `--pongo-800` (`#0F149A`) is 13.23:1.
- Status pills pair semantic text with a light semantic tint; measured pairs are 5.18:1 (`live`), 5.63:1 (`warning`), 5.89:1 (`danger`) and 5.90:1 (`info`).
- Charts: series meet 3:1 against the card surface; series are additionally distinguished by line style (solid vs dashed), not color alone.
- Open concern: the brand anchor `#0F149A` on dark chrome is reserved for gradients and never for text; implementation should lint token pairs to keep this rule.

## 2. Keyboard navigation

- Every interactive element in the preview is a native `button`, `a`, `input`, `select`, or `textarea`; no clickable divs.
- Visible focus: global `:focus-visible` ring (3px blue, 2px offset) on light and dark surfaces.
- A skip link ("Skip to main content") is the first focusable element.
- Tables: sortable headers are buttons; row overflow menus are buttons with `aria-label`s naming the record.
- Open concern: full roving-tab-index grid navigation (arrow keys between cells) is specified as a future enhancement, not demonstrated.

## 3. Semantic structure

- Landmarks: `nav` (modules), `header` (command bar), `main` (workspace), `aside` (detail drawer with `role="dialog"`).
- One `h1` per screen; sections use real headings; eyebrows are presentational and never replace headings.
- Tabs use `role="tablist"`/`role="tab"` with `aria-selected`; the redesign removes the current app's static non-interactive elements with tab roles entirely (every tab navigates).
- Status is always dot plus text inside the pill; boolean values render as text with icon, never color alone.

## 4. Overlays and focus behavior

- Drawer and modals: `role="dialog"`, `aria-modal="true"`, labelled by their titles; Escape closes; scrim click closes; focus moves to the dialog on open and returns to the trigger on close (implemented in preview.js).
- Toasts: `aria-live="polite"` region, never steal focus, persist on hover and keyboard focus.
- The live notification pattern from the current product (polite live region, atomic) is preserved as-is because it is already correct.
- Open concern: the preview implements focus capture (initial focus plus return focus plus Escape); a production build should add a full focus trap (wrap at ends) in the shared primitive.

## 5. Touch targets and floor ergonomics

- Desk surfaces: 36px controls with 8px spacing (above the 24px WCAG 2.2 minimum, below the 44px mobile ideal, acceptable for pointer-first desk use).
- Floor surfaces (Picking, Scan, Receiving): 40-48px controls, oversized quantity steppers (38px buttons), bin location at 27px mono; on under-768px layouts all primary actions are 44px.
- Mobile navigation targets are 44px rows.

## 6. Motion

- `prefers-reduced-motion: reduce` collapses all animation: pulse becomes a static gradient edge, scan sweep is removed, shimmer becomes flat, transitions drop to near-zero duration.
- No animation blocks input; no animation exceeds 280ms except the ambient pulse (which is decorative and disabled under reduced motion).
- Scanner failure feedback is shake plus color plus text message, so the message carries the meaning without motion.

## 7. Forms and errors

- Labels are visible above every field (no placeholder-only labels anywhere in the redesign).
- Errors render below the field with icon plus text and `aria-describedby` linkage in the settings demo; error text meets 4.5:1.
- Destructive actions use the danger color plus a typed confirmation ("Type RESET") and never sit beside primary actions.
- Helper text is persistent, not tooltip-only.

## 8. Data and charts

- Every chart in the preview carries a `role="img"` with a sentence-level `aria-label` describing the takeaway, and sits beside its backing data table (Insights) or text list (donut composition).
- Numeric table columns are right-aligned with tabular figures to support scanning by magnification users.

## 9. Screen-reader review of key flows

- Order drawer: dialog announcement includes order id and statuses (pill text); timeline is a text list.
- Picking: progress is a `progressbar` with value text "3 of 8"; scan result messages are `role="status"`.
- Bulk selection: checkboxes are labelled per row ("Select order #1051"); the bulk bar announces count via text change in a live region.

## 10. Compromises and remaining concerns

1. Chrome eyebrow labels at 10px are below ideal text size; they are decorative group labels with adjacent full-size items, but a browser zoom-level audit must still confirm usability at 200% zoom.
2. Dense table mode (32px rows) reduces target size below 36px; it is opt-in and desk-only, and row actions retain 30px minimum targets. Documented as a conscious tradeoff.
3. The preview's focus management is initial-focus plus return-focus; production must upgrade to a complete trap and inert background (`inert` attribute) in the shared overlay primitive.
4. Live "pulse" and blinking live dots are capped at one ambient animation per screen; users who find them distracting can rely on reduced-motion. A future per-user "calm mode" setting is recommended.
5. Color-vision check: `pongo-650` vs `live-500` differ in hue and lightness; status pills additionally carry dot plus explicit text. A tooling pass (for example Stark or axe) is still required on the implemented product.
6. Automated visual, zoom and assistive-technology browser checks could not run in this session because the in-app browser runtime reported no available browsers. Syntax, markup, asset, token and responsive-rule checks were completed; browser visual sign-off remains open.
