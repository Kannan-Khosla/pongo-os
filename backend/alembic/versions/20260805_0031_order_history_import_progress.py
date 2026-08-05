"""Add resumable WooCommerce order-history import progress.

Revision ID: 20260805_0031
Revises: 20260803_0030
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0031"
down_revision = "20260803_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    sync_columns = {column["name"] for column in inspector.get_columns("woocommerce_sync_runs")}
    if "progress" not in sync_columns:
        op.add_column("woocommerce_sync_runs", sa.Column("progress", sa.JSON(), nullable=True))
    order_columns = {column["name"] for column in inspector.get_columns("orders")}
    if "is_historical_snapshot" not in order_columns:
        op.add_column(
            "orders",
            sa.Column("is_historical_snapshot", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "historical_source_present" not in order_columns:
        op.add_column(
            "orders",
            sa.Column("historical_source_present", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    order_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("orders")}
    if "ix_orders_is_historical_snapshot" not in order_indexes:
        op.create_index(
            "ix_orders_is_historical_snapshot",
            "orders",
            ["is_historical_snapshot"],
            unique=False,
        )
    if "ix_orders_historical_source_present" not in order_indexes:
        op.create_index(
            "ix_orders_historical_source_present",
            "orders",
            ["historical_source_present"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    order_indexes = {index["name"] for index in inspector.get_indexes("orders")}
    if "ix_orders_is_historical_snapshot" in order_indexes:
        op.drop_index("ix_orders_is_historical_snapshot", table_name="orders")
    if "ix_orders_historical_source_present" in order_indexes:
        op.drop_index("ix_orders_historical_source_present", table_name="orders")
    order_columns = {column["name"] for column in inspector.get_columns("orders")}
    if "is_historical_snapshot" in order_columns:
        op.drop_column("orders", "is_historical_snapshot")
    if "historical_source_present" in order_columns:
        op.drop_column("orders", "historical_source_present")
    sync_columns = {column["name"] for column in inspector.get_columns("woocommerce_sync_runs")}
    if "progress" in sync_columns:
        op.drop_column("woocommerce_sync_runs", "progress")
