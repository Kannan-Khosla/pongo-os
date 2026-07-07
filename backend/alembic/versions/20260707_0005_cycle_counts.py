"""cycle counts

Revision ID: 20260707_0005
Revises: 20260707_0004
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0005"
down_revision: str | None = "20260707_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name not in existing_indexes:
        op.create_index(index_name, table_name, columns, unique=False)


def drop_index_if_present(table_name: str, index_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in existing_indexes:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not table_exists("cycle_counts"):
        op.create_table(
            "cycle_counts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("count_number", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("warehouse", sa.String(length=120), nullable=False),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("count_type", sa.String(length=40), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("count_number"),
        )
    create_index_if_missing("cycle_counts", "ix_cycle_counts_count_number", ["count_number"])
    create_index_if_missing("cycle_counts", "ix_cycle_counts_status", ["status"])
    create_index_if_missing("cycle_counts", "ix_cycle_counts_warehouse", ["warehouse"])
    create_index_if_missing("cycle_counts", "ix_cycle_counts_inventory_location", ["inventory_location"])
    create_index_if_missing("cycle_counts", "ix_cycle_counts_count_type", ["count_type"])
    create_index_if_missing("cycle_counts", "ix_cycle_counts_created_by", ["created_by"])
    create_index_if_missing("cycle_counts", "ix_cycle_counts_posted_at", ["posted_at"])

    if not table_exists("cycle_count_lines"):
        op.create_table(
            "cycle_count_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cycle_count_id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("warehouse", sa.String(length=120), nullable=False),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("system_quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("counted_quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("variance_quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
            sa.Column("variance_value", sa.Numeric(14, 2), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["cycle_count_id"], ["cycle_counts.id"]),
            sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    create_index_if_missing("cycle_count_lines", "ix_cycle_count_lines_cycle_count_id", ["cycle_count_id"])
    create_index_if_missing("cycle_count_lines", "ix_cycle_count_lines_item_id", ["item_id"])
    create_index_if_missing("cycle_count_lines", "ix_cycle_count_lines_sku", ["sku"])
    create_index_if_missing("cycle_count_lines", "ix_cycle_count_lines_barcode", ["barcode"])
    create_index_if_missing("cycle_count_lines", "ix_cycle_count_lines_warehouse", ["warehouse"])
    create_index_if_missing("cycle_count_lines", "ix_cycle_count_lines_inventory_location", ["inventory_location"])


def downgrade() -> None:
    if table_exists("cycle_count_lines"):
        drop_index_if_present("cycle_count_lines", "ix_cycle_count_lines_inventory_location")
        drop_index_if_present("cycle_count_lines", "ix_cycle_count_lines_warehouse")
        drop_index_if_present("cycle_count_lines", "ix_cycle_count_lines_barcode")
        drop_index_if_present("cycle_count_lines", "ix_cycle_count_lines_sku")
        drop_index_if_present("cycle_count_lines", "ix_cycle_count_lines_item_id")
        drop_index_if_present("cycle_count_lines", "ix_cycle_count_lines_cycle_count_id")
        op.drop_table("cycle_count_lines")

    if table_exists("cycle_counts"):
        drop_index_if_present("cycle_counts", "ix_cycle_counts_posted_at")
        drop_index_if_present("cycle_counts", "ix_cycle_counts_created_by")
        drop_index_if_present("cycle_counts", "ix_cycle_counts_count_type")
        drop_index_if_present("cycle_counts", "ix_cycle_counts_inventory_location")
        drop_index_if_present("cycle_counts", "ix_cycle_counts_warehouse")
        drop_index_if_present("cycle_counts", "ix_cycle_counts_status")
        drop_index_if_present("cycle_counts", "ix_cycle_counts_count_number")
        op.drop_table("cycle_counts")
