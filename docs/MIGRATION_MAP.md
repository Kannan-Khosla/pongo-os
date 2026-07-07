# Migration and Rebuild Map

This document maps possible legacy WordPress plugin concepts to the new standalone architecture.

| Legacy concept | Pongo Inventory OS concept |
| --- | --- |
| WordPress plugin admin page | React admin page |
| WooCommerce PHP functions | Backend WooCommerce REST API client |
| `wpdb` custom tables | PostgreSQL tables through SQLAlchemy models |
| Shortcode UI | React routes and components |
| WP users/capabilities | Standalone staff auth and roles |
| WooCommerce stock APIs in PHP | Backend WooCommerce REST calls |
| Plugin audit rows | `stock_movements` table |
| WordPress AJAX handlers | FastAPI endpoints |
| Plugin settings page | Backend-managed settings and environment variables |
| WordPress cron | Backend scheduled jobs or Heroku scheduler |

## Rebuild Principles

- Rebuild concepts, not WordPress implementation details.
- Keep WooCommerce credentials in backend environment variables.
- Preserve useful Pongo workflows and terminology.
- Use PostgreSQL relationships rather than WordPress-specific data access.
- Keep stock changes audited through `stock_movements`.
