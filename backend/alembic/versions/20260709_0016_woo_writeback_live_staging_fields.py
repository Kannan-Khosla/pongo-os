"""woo writeback live staging fields

Revision ID: 20260709_0016
Revises: 20260709_0015
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260709_0016"
down_revision: str | None = "20260709_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def index_exists(table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    add_column_if_missing("woo_writeback_queue", sa.Column("woo_product_id", sa.Integer(), nullable=True))
    add_column_if_missing("woo_writeback_queue", sa.Column("woo_variation_id", sa.Integer(), nullable=True))
    add_column_if_missing("woo_writeback_queue", sa.Column("woo_order_id", sa.Integer(), nullable=True))
    add_column_if_missing("woo_writeback_queue", sa.Column("allowed_host", sa.String(length=255), nullable=True))
    add_column_if_missing("woo_writeback_queue", sa.Column("requested_by", sa.String(length=120), nullable=True))
    add_column_if_missing("woo_writeback_queue", sa.Column("approved_by", sa.String(length=120), nullable=True))
    add_column_if_missing("woo_writeback_queue", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for index_name, columns in [
        ("ix_woo_writeback_queue_woo_product_id", ["woo_product_id"]),
        ("ix_woo_writeback_queue_woo_variation_id", ["woo_variation_id"]),
        ("ix_woo_writeback_queue_woo_order_id", ["woo_order_id"]),
        ("ix_woo_writeback_queue_allowed_host", ["allowed_host"]),
        ("ix_woo_writeback_queue_requested_by", ["requested_by"]),
        ("ix_woo_writeback_queue_approved_by", ["approved_by"]),
        ("ix_woo_writeback_queue_updated_at", ["updated_at"]),
    ]:
        create_index_if_missing("woo_writeback_queue", index_name, columns)


def downgrade() -> None:
    for index_name in [
        "ix_woo_writeback_queue_updated_at",
        "ix_woo_writeback_queue_approved_by",
        "ix_woo_writeback_queue_requested_by",
        "ix_woo_writeback_queue_allowed_host",
        "ix_woo_writeback_queue_woo_order_id",
        "ix_woo_writeback_queue_woo_variation_id",
        "ix_woo_writeback_queue_woo_product_id",
    ]:
        if index_exists("woo_writeback_queue", index_name):
            op.drop_index(index_name, table_name="woo_writeback_queue")
    for column_name in ["updated_at", "approved_by", "requested_by", "allowed_host", "woo_order_id", "woo_variation_id", "woo_product_id"]:
        if column_exists("woo_writeback_queue", column_name):
            op.drop_column("woo_writeback_queue", column_name)
