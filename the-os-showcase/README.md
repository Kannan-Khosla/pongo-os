# The-OS interactive showcase

A standalone, fictional product landing page and interactive operations showcase. It translates the implemented capabilities of the adjacent Pongo OS repository into an unbranded sales narrative for **The-OS**, using only synthetic **Northstar Commerce** data.

This is not an authenticated application, production deployment, API client, or replacement for the existing frontend. It has no backend dependency and performs no remote writes.

## Run locally

```bash
cd the-os-showcase
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://127.0.0.1:5173`).

## Verify

```bash
npm test
npm run lint
npm run typecheck
npm run build
```

## Project structure

```text
the-os-showcase/
├── docs/                  audit, design system, wireframe, and QA notes
├── src/
│   ├── components/        reusable local UI primitives
│   ├── demo/              ten interactive product modules
│   ├── mock-data/         fictional Northstar Commerce data
│   ├── sections/          landing-page narrative sections
│   ├── App.jsx            page composition and local modal state
│   ├── styles.css         foundation and product-demo styling
│   └── narrative.css      narrative sections and responsive rules
├── index.html
└── vite.config.js
```

## Interaction architecture

All interaction state is held in React components. Filters use in-memory arrays; drawers and the walkthrough message are local overlays; receipt, pick, route, sync, report, and insight changes are simulations reset by reload. CSV buttons report a local preparation state and never create or transmit a file.

The interface uses semantic controls, visible focus states, keyboard-operable module tabs, Escape-to-close dialogs, a skip link, live status regions, and a `prefers-reduced-motion` fallback. The layout supports wide desktop, laptop, tablet, and narrow mobile widths.

## Adding a module

1. Add fictional data to `src/mock-data/data.js` if needed.
2. Add one component under `src/demo/`.
3. Register its label, icon, and component in `InteractiveOSWindow.jsx`.
4. Add one interaction test to `src/App.test.jsx`.

Keep additions local-only and avoid claims not supported by the audited source product. See [FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) and [DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md).

