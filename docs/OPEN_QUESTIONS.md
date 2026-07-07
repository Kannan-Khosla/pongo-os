# Open Questions

- What is the exact CSV product import format?
- What are the exact location import columns Pongo will upload?
- Should manual item creation push to WooCommerce later, or remain local-only?
- Which WooCommerce order statuses count as open?
- Which map provider should be used: Google Maps, Google Routes API, Mapbox, OpenRouteService, or another provider?
- Should WooCommerce stock updates be automatic, queued for approval, or disabled until manually triggered?
- Does tracking number come from a WooCommerce plugin/meta field, and if so which one?
- What staff auth roles are required for MVP?
- Which Heroku PostgreSQL plan should be used?
- Should barcode be globally unique or only unique per client?
- Should SKU be required for all items, or can barcode-only items exist?
- How should duplicate SKUs from WooCommerce be handled during sync?
- Should received unit cost update item master unit cost automatically or remain receipt-specific?
- What is the default warehouse name/code?
- What location should be assigned when synced WooCommerce items have no mapped stock location?
