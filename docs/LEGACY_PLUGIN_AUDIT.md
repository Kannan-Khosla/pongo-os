# Legacy Plugin Audit

This is a placeholder for a future audit of a legacy WordPress plugin that may later live under:

`legacy-wordpress-plugin/pongo-inventory-os`

## Audit Position

The new Pongo Inventory OS should not be a direct line-by-line conversion of a WordPress plugin. The new system is a standalone FastAPI, PostgreSQL, and React application.

## Useful Legacy Concepts

The old plugin may be useful as a reference for:
- Inventory table concepts
- Order picking concepts
- WooCommerce field mapping
- Stock audit behavior
- Admin UI ideas
- Existing Pongo terminology

## Do Not Port Directly

WordPress-specific code should not be ported directly, including:
- WordPress hooks
- Shortcodes
- `wpdb`
- `wp_ajax`
- WordPress permissions/capabilities
- WooCommerce PHP functions
- Plugin activation/deactivation lifecycle code
- WordPress admin page rendering

## Future Audit Notes

When the legacy plugin is available, audit it for concepts and data shapes, then map useful pieces into the standalone architecture documented in `MIGRATION_MAP.md`.
