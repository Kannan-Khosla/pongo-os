"""fulfillment foundation

Revision ID: 20260707_0010
Revises: 20260707_0009
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0010"
down_revision: str | None = "20260707_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def drop_index_if_present(table_name: str, index_name: str) -> None:
    if not table_exists(table_name):
        return
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not column_exists("order_items", "quantity_fulfilled"):
        op.add_column("order_items", sa.Column("quantity_fulfilled", sa.Numeric(14, 3), nullable=False, server_default="0"))
    if not column_exists("order_items", "fulfilled_qty"):
        op.add_column("order_items", sa.Column("fulfilled_qty", sa.Numeric(14, 3), nullable=False, server_default="0"))

    if not table_exists("fulfillments"):
        op.create_table(
            "fulfillments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fulfillment_number", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("fulfillment_type", sa.String(length=40), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("woo_order_id", sa.Integer(), nullable=True),
            sa.Column("woo_order_number", sa.String(length=120), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for index_name, columns, unique in [
        ("ix_fulfillments_fulfillment_number", ["fulfillment_number"], True),
        ("ix_fulfillments_status", ["status"], False),
        ("ix_fulfillments_fulfillment_type", ["fulfillment_type"], False),
        ("ix_fulfillments_order_id", ["order_id"], False),
        ("ix_fulfillments_woo_order_id", ["woo_order_id"], False),
        ("ix_fulfillments_woo_order_number", ["woo_order_number"], False),
        ("ix_fulfillments_created_by", ["created_by"], False),
        ("ix_fulfillments_posted_at", ["posted_at"], False),
        ("ix_fulfillments_cancelled_at", ["cancelled_at"], False),
    ]:
        create_index_if_missing("fulfillments", index_name, columns, unique)

    if not table_exists("fulfillment_lines"):
        op.create_table(
            "fulfillment_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("fulfillment_id", sa.Integer(), sa.ForeignKey("fulfillments.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("order_line_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=False),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("warehouse", sa.String(length=120), nullable=True),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("quantity_ordered", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_allocated", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_picked", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_previously_fulfilled", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_to_fulfill", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_fulfilled_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("remaining_to_fulfill", sa.Numeric(14, 3), nullable=False),
            sa.Column("in_stock_before", sa.Numeric(14, 3), nullable=False),
            sa.Column("allocated_before", sa.Numeric(14, 3), nullable=False),
            sa.Column("sellable_before", sa.Numeric(14, 3), nullable=False),
            sa.Column("in_stock_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("allocated_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("sellable_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for index_name, columns in [
        ("ix_fulfillment_lines_fulfillment_id", ["fulfillment_id"]),
        ("ix_fulfillment_lines_order_id", ["order_id"]),
        ("ix_fulfillment_lines_order_line_id", ["order_line_id"]),
        ("ix_fulfillment_lines_item_id", ["item_id"]),
        ("ix_fulfillment_lines_sku", ["sku"]),
        ("ix_fulfillment_lines_barcode", ["barcode"]),
        ("ix_fulfillment_lines_warehouse", ["warehouse"]),
        ("ix_fulfillment_lines_inventory_location", ["inventory_location"]),
        ("ix_fulfillment_lines_status", ["status"]),
    ]:
        create_index_if_missing("fulfillment_lines", index_name, columns)


def downgrade() -> None:
    for table_name, index_names in [
        (
            "fulfillment_lines",
            [
                "ix_fulfillment_lines_status",
                "ix_fulfillment_lines_inventory_location",
                "ix_fulfillment_lines_warehouse",
                "ix_fulfillment_lines_barcode",
                "ix_fulfillment_lines_sku",
                "ix_fulfillment_lines_item_id",
                "ix_fulfillment_lines_order_line_id",
                "ix_fulfillment_lines_order_id",
                "ix_fulfillment_lines_fulfillment_id",
            ],
        ),
        (
            "fulfillments",
            [
                "ix_fulfillments_cancelled_at",
                "ix_fulfillments_posted_at",
                "ix_fulfillments_created_by",
                "ix_fulfillments_woo_order_number",
                "ix_fulfillments_woo_order_id",
                "ix_fulfillments_order_id",
                "ix_fulfillments_fulfillment_type",
                "ix_fulfillments_status",
                "ix_fulfillments_fulfillment_number",
            ],
        ),
    ]:
        for index_name in index_names:
            drop_index_if_present(table_name, index_name)
    for table_name in ["fulfillment_lines", "fulfillments"]:
        if table_exists(table_name):
            op.drop_table(table_name)
    if column_exists("order_items", "fulfilled_qty"):
        op.drop_column("order_items", "fulfilled_qty")
    if column_exists("order_items", "quantity_fulfilled"):
        op.drop_column("order_items", "quantity_fulfilled")
