"""picking foundation

Revision ID: 20260707_0009
Revises: 20260707_0008
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0009"
down_revision: str | None = "20260707_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


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
    if not table_exists("picks"):
        op.create_table(
            "picks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pick_number", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("pick_type", sa.String(length=40), nullable=False),
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
        ("ix_picks_pick_number", ["pick_number"], True),
        ("ix_picks_status", ["status"], False),
        ("ix_picks_pick_type", ["pick_type"], False),
        ("ix_picks_order_id", ["order_id"], False),
        ("ix_picks_woo_order_id", ["woo_order_id"], False),
        ("ix_picks_woo_order_number", ["woo_order_number"], False),
        ("ix_picks_created_by", ["created_by"], False),
        ("ix_picks_posted_at", ["posted_at"], False),
        ("ix_picks_cancelled_at", ["cancelled_at"], False),
    ]:
        create_index_if_missing("picks", index_name, columns, unique)

    if not table_exists("pick_lines"):
        op.create_table(
            "pick_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pick_id", sa.Integer(), sa.ForeignKey("picks.id"), nullable=False),
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
            sa.Column("quantity_previously_picked", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_to_pick", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_picked_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("remaining_to_pick", sa.Numeric(14, 3), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for index_name, columns in [
        ("ix_pick_lines_pick_id", ["pick_id"]),
        ("ix_pick_lines_order_id", ["order_id"]),
        ("ix_pick_lines_order_line_id", ["order_line_id"]),
        ("ix_pick_lines_item_id", ["item_id"]),
        ("ix_pick_lines_sku", ["sku"]),
        ("ix_pick_lines_barcode", ["barcode"]),
        ("ix_pick_lines_warehouse", ["warehouse"]),
        ("ix_pick_lines_inventory_location", ["inventory_location"]),
        ("ix_pick_lines_status", ["status"]),
    ]:
        create_index_if_missing("pick_lines", index_name, columns)


def downgrade() -> None:
    for table_name, index_names in [
        (
            "pick_lines",
            [
                "ix_pick_lines_status",
                "ix_pick_lines_inventory_location",
                "ix_pick_lines_warehouse",
                "ix_pick_lines_barcode",
                "ix_pick_lines_sku",
                "ix_pick_lines_item_id",
                "ix_pick_lines_order_line_id",
                "ix_pick_lines_order_id",
                "ix_pick_lines_pick_id",
            ],
        ),
        (
            "picks",
            [
                "ix_picks_cancelled_at",
                "ix_picks_posted_at",
                "ix_picks_created_by",
                "ix_picks_woo_order_number",
                "ix_picks_woo_order_id",
                "ix_picks_order_id",
                "ix_picks_pick_type",
                "ix_picks_status",
                "ix_picks_pick_number",
            ],
        ),
    ]:
        for index_name in index_names:
            drop_index_if_present(table_name, index_name)
    for table_name in ["pick_lines", "picks"]:
        if table_exists(table_name):
            op.drop_table(table_name)
