# Audited feature matrix

The matrix was prepared from the existing repository's indexed frontend entry points, FastAPI routes, services, and tests. “Showcase treatment” describes this standalone demo—not a new production feature.

| Audited capability | Implemented in source product | Sales importance | Showcase treatment |
|---|---:|---|---|
| Operational dashboard and attention states | Yes | High | Hero preview and interactive Command Center pipeline |
| Item catalog, create/edit, facets, history, notes | Yes | High | Searchable inventory table and product detail drawer |
| Product/variation import, export, refresh, and remap | Yes | High | Inventory narrative and WooCommerce capability list |
| Stock by warehouse/location, availability, valuation | Yes | Critical | Location filter, warehouse selector, stock metrics, location detail |
| Low stock, expiring stock, par levels | Yes | High | Inventory status filters, alerts, reports, insight signals |
| Stock movements and audit history | Yes | Critical | Movement rows, audit copy, receiving/picking state confirmations |
| Direct and bulk receiving | Yes | High | Three-step receipt workflow with stock-impact preview |
| Cycle counting and adjustments | Yes | Medium | Platform overview and warehouse-execution narrative |
| Barcode/SKU scanning | Yes | High | Functional scan input, validation, progress, and completion |
| Open/completed order synchronization | Yes | Critical | Filterable order operations table and order detail |
| Allocation and allocation exceptions | Yes | Critical | Pipeline, status chips, line-level allocation visibility |
| Pick creation, progress, and commit | Yes | Critical | Four-line interactive scan-and-pick flow |
| Fulfillment history and export | Yes | High | Order story, report family, and local export feedback |
| Received inventory report | Yes | Medium | Receiving report in the six-report workspace |
| SKU/barcode order report | Yes | High | SKU/order report family with chart and sample rows |
| Movement and fulfillment reports | Yes | High | Dedicated report views with export-ready local state |
| Business metrics and inventory intelligence | Yes | High | Date-range insight dashboard and decision signals |
| Route candidates, preview, sequencing, finalize, history | Yes | High | Fictional-district route map, reorder controls, finalize lock |
| WooCommerce product/order synchronization | Yes | Critical | Only named connected integration; explicit capability summary |
| Sync preview/commit, writeback controls, health | Yes | Critical | Safe-preview action, controlled-writeback note, visible health |
| Internal authentication | Yes | Not in scope | Deliberately omitted; this is a public landing showcase |
| Supplier management and purchase orders | No / excluded by product scope | None | Not shown or implied |

## Scope guardrails

- No real customer, product, order, barcode, address, or map data.
- No credentials, authentication flow, API request, database, or external write.
- WooCommerce is the only integration identified as connected.
- Route geography uses fictional districts, not real addresses.
- System-health and performance values are visibly synthetic.

