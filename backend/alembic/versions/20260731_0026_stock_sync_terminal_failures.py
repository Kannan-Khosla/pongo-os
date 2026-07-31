"""Persist terminal Woo stock-sync failures for manual retry.

Revision ID: 20260731_0026
Revises: 20260731_0025
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0026"
down_revision = "20260731_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("woo_stock_sync_jobs"):
        raise RuntimeError("Required woo_stock_sync_jobs table is missing before revision 0026.")
    columns = {column["name"] for column in inspector.get_columns("woo_stock_sync_jobs")}
    if "terminal_failed_item_ids" not in columns:
        with op.batch_alter_table("woo_stock_sync_jobs") as batch:
            batch.add_column(sa.Column("terminal_failed_item_ids", sa.JSON(), nullable=True))
    if "terminal_failed_item_ids" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("woo_stock_sync_jobs")}:
        raise RuntimeError("woo_stock_sync_jobs.terminal_failed_item_ids was not created.")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("woo_stock_sync_jobs")}
    if "terminal_failed_item_ids" in columns:
        with op.batch_alter_table("woo_stock_sync_jobs") as batch:
            batch.drop_column("terminal_failed_item_ids")
