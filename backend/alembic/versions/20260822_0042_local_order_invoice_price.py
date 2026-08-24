"""Snapshot local invoice pricing for Pongo order edits.

Revision ID: 20260822_0042
Revises: 20260821_0041
"""

from alembic import op
import sqlalchemy as sa


revision = "20260822_0042"
down_revision = "20260821_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("order_items")}
    if "local_invoice_unit_price" not in columns:
        with op.batch_alter_table("order_items") as batch:
            batch.add_column(sa.Column("local_invoice_unit_price", sa.Numeric(12, 2)))

    op.execute(
        sa.text(
            """
            UPDATE order_items
            SET local_invoice_unit_price = COALESCE(
                (SELECT sales_price FROM inventory_items WHERE inventory_items.id = order_items.inventory_item_id),
                (SELECT recommended_retail_price FROM inventory_items WHERE inventory_items.id = order_items.inventory_item_id),
                unit_price
            )
            WHERE substituted_from_inventory_item_id IS NOT NULL
               OR sync_status = 'local_added'
            """
        )
    )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("order_items")}
    if "local_invoice_unit_price" in columns:
        with op.batch_alter_table("order_items") as batch:
            batch.drop_column("local_invoice_unit_price")
