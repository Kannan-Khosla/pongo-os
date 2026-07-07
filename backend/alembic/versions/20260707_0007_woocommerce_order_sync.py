"""woocommerce order sync

Revision ID: 20260707_0007
Revises: 20260707_0006
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0007"
down_revision: str | None = "20260707_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    for column in [
        sa.Column("woo_order_number", sa.String(length=120), nullable=True),
        sa.Column("woo_status", sa.String(length=80), nullable=True),
        sa.Column("local_status", sa.String(length=80), nullable=True),
        sa.Column("currency", sa.String(length=12), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_first_name", sa.String(length=120), nullable=True),
        sa.Column("customer_last_name", sa.String(length=120), nullable=True),
        sa.Column("customer_phone", sa.String(length=80), nullable=True),
        sa.Column("billing_summary", sa.JSON(), nullable=True),
        sa.Column("shipping_summary", sa.JSON(), nullable=True),
        sa.Column("payment_method", sa.String(length=120), nullable=True),
        sa.Column("payment_method_title", sa.String(length=240), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("shipping_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("total", sa.Numeric(12, 2), nullable=True),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_paid", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_completed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(length=80), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    ]:
        add_column_if_missing("orders", column)
    for index_name, columns in [
        ("ix_orders_woo_order_number", ["woo_order_number"]),
        ("ix_orders_woo_status", ["woo_status"]),
        ("ix_orders_local_status", ["local_status"]),
        ("ix_orders_customer_id", ["customer_id"]),
        ("ix_orders_date_created", ["date_created"]),
        ("ix_orders_date_modified", ["date_modified"]),
        ("ix_orders_sync_status", ["sync_status"]),
        ("ix_orders_last_synced_at", ["last_synced_at"]),
    ]:
        create_index_if_missing("orders", index_name, columns)

    for column in [
        sa.Column("woo_product_id", sa.Integer(), nullable=True),
        sa.Column("woo_variation_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("quantity_ordered", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("quantity_allocated", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("quantity_picked", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("line_subtotal", sa.Numeric(12, 2), nullable=True),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("line_tax", sa.Numeric(12, 2), nullable=True),
        sa.Column("matched_status", sa.String(length=80), nullable=True),
        sa.Column("availability_status", sa.String(length=80), nullable=True),
        sa.Column("sellable_snapshot", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("shortage_quantity", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("sync_status", sa.String(length=80), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
    ]:
        add_column_if_missing("order_items", column)
    for index_name, columns in [
        ("ix_order_items_woo_product_id", ["woo_product_id"]),
        ("ix_order_items_woo_variation_id", ["woo_variation_id"]),
        ("ix_order_items_matched_status", ["matched_status"]),
        ("ix_order_items_availability_status", ["availability_status"]),
        ("ix_order_items_sync_status", ["sync_status"]),
    ]:
        create_index_if_missing("order_items", index_name, columns)

    add_column_if_missing("woocommerce_sync_errors", sa.Column("remote_order_id", sa.Integer(), nullable=True))
    add_column_if_missing("woocommerce_sync_errors", sa.Column("remote_line_item_id", sa.Integer(), nullable=True))
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_remote_order_id", ["remote_order_id"])
    create_index_if_missing("woocommerce_sync_errors", "ix_woocommerce_sync_errors_remote_line_item_id", ["remote_line_item_id"])


def downgrade() -> None:
    for table_name, index_name in [
        ("woocommerce_sync_errors", "ix_woocommerce_sync_errors_remote_line_item_id"),
        ("woocommerce_sync_errors", "ix_woocommerce_sync_errors_remote_order_id"),
        ("order_items", "ix_order_items_sync_status"),
        ("order_items", "ix_order_items_availability_status"),
        ("order_items", "ix_order_items_matched_status"),
        ("order_items", "ix_order_items_woo_variation_id"),
        ("order_items", "ix_order_items_woo_product_id"),
        ("orders", "ix_orders_last_synced_at"),
        ("orders", "ix_orders_sync_status"),
        ("orders", "ix_orders_date_modified"),
        ("orders", "ix_orders_date_created"),
        ("orders", "ix_orders_customer_id"),
        ("orders", "ix_orders_local_status"),
        ("orders", "ix_orders_woo_status"),
        ("orders", "ix_orders_woo_order_number"),
    ]:
        drop_index_if_present(table_name, index_name)
    for column_name in ["remote_line_item_id", "remote_order_id"]:
        drop_column_if_present("woocommerce_sync_errors", column_name)
    for column_name in [
        "sync_error",
        "sync_status",
        "shortage_quantity",
        "sellable_snapshot",
        "availability_status",
        "matched_status",
        "line_tax",
        "line_total",
        "line_subtotal",
        "quantity_picked",
        "quantity_allocated",
        "quantity_ordered",
        "name",
        "woo_variation_id",
        "woo_product_id",
    ]:
        drop_column_if_present("order_items", column_name)
    for column_name in [
        "last_synced_at",
        "sync_error",
        "sync_status",
        "date_completed",
        "date_paid",
        "date_modified",
        "date_created",
        "total",
        "tax_total",
        "shipping_total",
        "discount_total",
        "subtotal",
        "payment_method_title",
        "payment_method",
        "shipping_summary",
        "billing_summary",
        "customer_phone",
        "customer_last_name",
        "customer_first_name",
        "customer_id",
        "currency",
        "local_status",
        "woo_status",
        "woo_order_number",
    ]:
        drop_column_if_present("orders", column_name)
