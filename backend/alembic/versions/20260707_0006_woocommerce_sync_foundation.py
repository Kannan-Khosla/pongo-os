"""woocommerce sync foundation

Revision ID: 20260707_0006
Revises: 20260707_0005
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0006"
down_revision: str | None = "20260707_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    existing = {existing_column["name"] for existing_column in sa.inspect(op.get_bind()).get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=False)


def drop_index_if_present(table_name: str, index_name: str) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def drop_column_if_present(table_name: str, column_name: str) -> None:
    existing = {existing_column["name"] for existing_column in sa.inspect(op.get_bind()).get_columns(table_name)}
    if column_name in existing:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    add_column_if_missing("inventory_items", sa.Column("woo_product_type", sa.String(length=40), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_permalink", sa.String(length=1000), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_status", sa.String(length=80), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_manage_stock", sa.Boolean(), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_stock_status", sa.String(length=80), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_stock_quantity_snapshot", sa.Numeric(14, 3), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_last_synced_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_sync_status", sa.String(length=80), nullable=True))
    add_column_if_missing("inventory_items", sa.Column("woo_sync_error", sa.Text(), nullable=True))
    create_index_if_missing("inventory_items", "ix_inventory_items_woo_product_type", ["woo_product_type"])
    create_index_if_missing("inventory_items", "ix_inventory_items_woo_status", ["woo_status"])
    create_index_if_missing("inventory_items", "ix_inventory_items_woo_stock_status", ["woo_stock_status"])
    create_index_if_missing("inventory_items", "ix_inventory_items_woo_last_synced_at", ["woo_last_synced_at"])
    create_index_if_missing("inventory_items", "ix_inventory_items_woo_sync_status", ["woo_sync_status"])

    if not table_exists("woocommerce_sync_runs"):
        op.create_table(
            "woocommerce_sync_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sync_type", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=80), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("total_remote_records", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    create_index_if_missing("woocommerce_sync_runs", "ix_woocommerce_sync_runs_sync_type", ["sync_type"])
    create_index_if_missing("woocommerce_sync_runs", "ix_woocommerce_sync_runs_status", ["status"])
    create_index_if_missing("woocommerce_sync_runs", "ix_woocommerce_sync_runs_started_at", ["started_at"])
    create_index_if_missing("woocommerce_sync_runs", "ix_woocommerce_sync_runs_completed_at", ["completed_at"])
    create_index_if_missing("woocommerce_sync_runs", "ix_woocommerce_sync_runs_created_by", ["created_by"])

    if not table_exists("woocommerce_sync_errors"):
        op.create_table(
            "woocommerce_sync_errors",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("sync_run_id", sa.Integer(), nullable=False),
            sa.Column("remote_product_id", sa.Integer(), nullable=True),
            sa.Column("remote_variation_id", sa.Integer(), nullable=True),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("raw_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["sync_run_id"], ["woocommerce_sync_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_sync_run_id", ["sync_run_id"])
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_remote_product_id", ["remote_product_id"])
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_remote_variation_id", ["remote_variation_id"])
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_sku", ["sku"])
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_barcode", ["barcode"])


def downgrade() -> None:
    if table_exists("woocommerce_sync_errors"):
        op.drop_table("woocommerce_sync_errors")
    if table_exists("woocommerce_sync_runs"):
        op.drop_table("woocommerce_sync_runs")
    for index_name in [
        "ix_inventory_items_woo_sync_status",
        "ix_inventory_items_woo_last_synced_at",
        "ix_inventory_items_woo_stock_status",
        "ix_inventory_items_woo_status",
        "ix_inventory_items_woo_product_type",
    ]:
        drop_index_if_present("inventory_items", index_name)
    for column_name in [
        "woo_sync_error",
        "woo_sync_status",
        "woo_last_synced_at",
        "woo_stock_quantity_snapshot",
        "woo_stock_status",
        "woo_manage_stock",
        "woo_status",
        "woo_permalink",
        "woo_product_type",
    ]:
        drop_column_if_present("inventory_items", column_name)
