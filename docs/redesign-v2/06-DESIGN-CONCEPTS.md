# Design concepts

## Concept A — Pongo Command Nexus

- **Core idea:** a deep-indigo module spine and contextual navigator frame a bright operational canvas. A “signal rail” surfaces live work, warnings and sync status across modules.
- **Shell:** 76 px module rail + 228 px contextual rail + fluid canvas; top command field and utility cluster; optional right detail drawer.
- **Navigation:** four module groups—Command, Operations, Intelligence, System—with route-specific second-level links.
- **Workspace:** queue + detail, session, entity and report templates share one grid.
- **Color:** Pongo blue/deep indigo chrome, cool neutral canvas, restrained live orange, cyan/violet data accents.
- **Typography:** IBM Plex Sans-style UI, tabular numerics, mono identifiers.
- **Components:** precise 10–14 px radii, fine borders, soft elevation, clipped corner signal accents.
- **Tables:** sticky header, 40 px density, selection rail, action menu, column priority and mobile record cards.
- **Dashboard:** priority lanes for “Act now”, “In motion”, “Health” and “Recent”.
- **Modal/drawer:** routine detail in drawers; guarded mutations in compact dialogs with before/after summary.
- **Motion:** 180–260 ms ease-out; drawer slide, filter compression, selection wash and restrained live pulse.
- **Responsive:** contextual rail collapses at laptop, module rail at tablet, off-canvas navigation and record cards on mobile.
- **Benefits:** strongest OS identity, clear context, scalable modules, supports dense operations.
- **Risks:** two-rail desktop shell needs careful naming and can consume width on small laptops.
- **Suitability:** excellent; directly addresses navigation, identity and long-page problems.

## Concept B — Pongo Signal Grid

- **Core idea:** every module is a modular grid of movable information zones with status bands and compact density.
- **Shell:** single collapsible sidebar, persistent top status strip, 12-column tile canvas.
- **Navigation:** module list with saved workspaces and density controls.
- **Workspace:** grid zones for queues, metrics, charts and actions; details open as overlays.
- **Color:** light neutral field, Pongo-blue blocks, orange status headers, muted cyan/violet charts.
- **Typography:** single utilitarian sans with mono numerics.
- **Components:** squared 8 px panels, compact cards, visible grid rules and status bands.
- **Tables:** embedded grid regions with sticky toolbars and optional full-screen expansion.
- **Dashboard:** strongest area—live modular operations board.
- **Modal/drawer:** full-screen inspector for complex details; compact modal for confirmation.
- **Motion:** grid reflow and status updates; little decorative motion.
- **Responsive:** modules become a prioritized vertical feed.
- **Benefits:** very data-forward, efficient, strong monitoring language.
- **Risks:** can become a “collection of cards”, and free-form grids weaken workflow sequence.
- **Suitability:** good for dashboards, weaker for receiving/picking/count sessions.

## Concept C — Pongo Orbit Workspace

- **Core idea:** a spacious light canvas with a compact floating module dock, contextual command palette and layered entity sheets.
- **Shell:** narrow floating dock, top breadcrumb/command field, large canvas and floating utilities.
- **Navigation:** search-first; recent and pinned destinations carry more weight than hierarchy.
- **Workspace:** progressive disclosure with generous margins and layered detail sheets.
- **Color:** warm off-white, Pongo blue, soft violet, peach, subtle iridescent edge.
- **Typography:** larger display sans paired with neutral UI text.
- **Components:** 16–20 px surfaces, soft shadows, rounded floating controls.
- **Tables:** simplified default columns with expand-for-more behavior.
- **Dashboard:** spatial narrative, fewer simultaneous metrics.
- **Modal/drawer:** layered sheets are the primary interaction model.
- **Motion:** smooth spatial transitions and shared-element cues.
- **Responsive:** naturally collapses into single-column mobile sheets.
- **Benefits:** premium, distinctive and calm; excellent responsive potential.
- **Risks:** lower density and search-first navigation may slow repeat warehouse work.
- **Suitability:** strong for management and insights, less ideal for daily high-volume operations.

## Evaluation matrix

Scores are 1–10; higher is better.

| Criterion | Command Nexus | Signal Grid | Orbit Workspace |
| --- | ---: | ---: | ---: |
| Originality | 9 | 8 | 9 |
| Usability | 9 | 8 | 8 |
| Operational clarity | 10 | 9 | 7 |
| Scalability | 10 | 8 | 9 |
| Accessibility | 9 | 9 | 8 |
| Responsive suitability | 9 | 8 | 10 |
| Development feasibility | 8 | 8 | 7 |
| Future-module support | 10 | 8 | 9 |
| Pongo brand alignment | 10 | 8 | 9 |
| Distance from current design | 9 | 8 | 10 |
| **Total / 100** | **93** | **82** | **86** |

## Selected concept

**Pongo Command Nexus** is selected. It is the only direction that simultaneously supports warehouse density, management intelligence, future modules and a meaningfully new OS identity without becoming a card grid or sacrificing repeat-task speed. The signature two-level navigation makes the current route set understandable, while queue/detail and session patterns remove the long-page problem.

The prototype keeps the two-rail idea deliberately simple: one global module spine, one contextual rail, one top command area and one optional detail drawer. No configurable dashboard builder, personalization engine or new product capability is introduced.
