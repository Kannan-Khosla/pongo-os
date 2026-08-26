"""Use WooCommerce product titles instead of product descriptions.

Revision ID: 20260826_0044
Revises: 20260823_0043
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0044"
down_revision = "20260823_0043"
branch_labels = None
depends_on = None


TITLE_SNAPSHOT_TABLES = {
    "allocation_lines": "item_id",
    "cycle_count_lines": "item_id",
    "fulfillment_lines": "item_id",
    "inventory_transfer_lines": "inventory_item_id",
    "order_items": "inventory_item_id",
    "pick_lines": "item_id",
    "receipt_items": "inventory_item_id",
    "stock_adjustment_lines": "inventory_item_id",
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for table, item_column in TITLE_SNAPSHOT_TABLES.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "description" not in columns or item_column not in columns:
            continue
        op.execute(sa.text(f"""
            UPDATE {table}
            SET description = (
                SELECT inventory_items.woo_name
                FROM inventory_items
                WHERE inventory_items.id = {table}.{item_column}
            )
            WHERE EXISTS (
                SELECT 1
                FROM inventory_items
                WHERE inventory_items.id = {table}.{item_column}
                  AND inventory_items.woo_name IS NOT NULL
                  AND TRIM(inventory_items.woo_name) <> ''
            )
        """))

    op.execute(sa.text("""
        UPDATE inventory_items
        SET description = woo_name
        WHERE woo_name IS NOT NULL AND TRIM(woo_name) <> ''
    """))


def downgrade() -> None:
    # Long Woo descriptions were intentionally discarded and cannot be reconstructed.
    pass
