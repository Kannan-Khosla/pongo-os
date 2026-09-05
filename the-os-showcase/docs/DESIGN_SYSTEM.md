# Design system

The visual direction combines high-opacity liquid glass for structure with selective neumorphic elevation on controls and compact objects. The approach keeps text contrast and operational clarity ahead of spectacle.

## Hierarchy

1. Editorial sales narrative: large, tightly tracked headings and concise explanatory copy.
2. Product proof: the oversized interactive OS window is the visual anchor.
3. Operational evidence: dense but calm tables, statuses, progress, and audit language.
4. Detail on demand: drawers, local modal, expandable architecture note, and live states.

## Tokens

| Role | Token | Value |
|---|---|---|
| Canvas | `--canvas` | `#f5f7ff` |
| Primary text | `--ink` | `#10172a` |
| Secondary text | `--muted` | `#58657c` |
| Primary accent | `--accent` | `#6868e8` |
| Aqua accent | `--aqua` | `#55c7d1` |
| Blue accent | `--blue` | `#69aaf0` |
| Success | `--success` | `#21765f` |
| Glass blur | `--blur` | `22px` |
| Content width | `--container` | `1260px` |
| Product width | `--demo-width` | `1440px` |
| Radius range | `--radius-sm` → `--radius-xl` | `12px` → `42px` |
| Motion | `--motion-fast` → `--motion-slow` | `180ms` → `520ms` |

Typography uses an Inter-first system stack with no remote font request. Icons come from Lucide React; CSS gradients and shapes provide all other imagery.

## Components

- `GlassPanel`: readable high-opacity surface with blur when supported and an opaque fallback.
- Buttons: primary gradient, elevated soft secondary, and low-emphasis text variants.
- Status chips: label plus colored dot; color never carries meaning alone.
- Module tabs: vertical on wide screens, horizontally scrollable on mobile, with arrow/Home/End keyboard behavior.
- Data surfaces: semantic tables, compact metric cards, progress tracks, and lightweight SVG/CSS charts.
- Overlays: focus-managed modal and closeable product/order drawers.

## Motion and accessibility

- Entrance motion uses opacity and short vertical translation only.
- Hover motion stays within two to four pixels.
- No looping decorative animation is required to understand the page.
- Reduced-motion preference disables smooth scrolling, animation, and meaningful transition duration.
- Interactive targets are generally at least 40–48px with a high-contrast focus ring.
- Mobile navigation exposes `aria-expanded`; transient messages use polite live regions.

