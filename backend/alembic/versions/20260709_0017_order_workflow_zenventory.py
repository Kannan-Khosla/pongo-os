"""zenventory order workflow fields

Revision ID: 20260709_0017
Revises: 20260709_0016
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260709_0017"
down_revision: str | None = "20260709_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def column_exists(table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def index_exists(table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return constraint_name in {foreign_key.get("name") for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)}


def supports_alter_foreign_key() -> bool:
    return op.get_bind().dialect.name != "sqlite"


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def drop_index_if_exists(table_name: str, index_name: str) -> None:
    if index_exists(table_name, index_name):
        op.drop_index(index_name, table_name=table_name)


def drop_column_if_exists(table_name: str, column_name: str) -> None:
    if column_exists(table_name, column_name):
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_column(column_name)
        else:
            op.drop_column(table_name, column_name)


def upgrade() -> None:
    add_column_if_missing("orders", sa.Column("pick_status", sa.String(length=80), nullable=True))
    add_column_if_missing("orders", sa.Column("completion_status", sa.String(length=80), nullable=True))
    add_column_if_missing("orders", sa.Column("auto_allocation_status", sa.String(length=80), nullable=True))
    add_column_if_missing("orders", sa.Column("completed_without_picking", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column_if_missing("orders", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("orders", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("orders", sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("orders", sa.Column("allocation_exception_reason", sa.Text(), nullable=True))
    add_column_if_missing("orders", sa.Column("workflow_notes", sa.Text(), nullable=True))

    add_column_if_missing("order_items", sa.Column("quantity_stock_reduced", sa.Numeric(14, 3), nullable=False, server_default="0"))
    add_column_if_missing("order_items", sa.Column("stock_reduced_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("order_items", sa.Column("allocation_status", sa.String(length=80), nullable=True))
    add_column_if_missing("order_items", sa.Column("pick_status", sa.String(length=80), nullable=True))
    add_column_if_missing("order_items", sa.Column("allocation_exception_reason", sa.Text(), nullable=True))

    add_column_if_missing("allocations", sa.Column("auto_allocated", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column_if_missing("allocations", sa.Column("allocation_source", sa.String(length=40), nullable=False, server_default="manual"))
    add_column_if_missing("allocation_lines", sa.Column("auto_allocated", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column_if_missing("allocation_lines", sa.Column("allocation_source", sa.String(length=40), nullable=False, server_default="manual"))

    add_column_if_missing("pick_lines", sa.Column("quantity_stock_reduced", sa.Numeric(14, 3), nullable=False, server_default="0"))
    add_column_if_missing("pick_lines", sa.Column("stock_movement_id", sa.Integer(), nullable=True))
    add_column_if_missing("pick_lines", sa.Column("stock_reduced_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("pick_lines", sa.Column("idempotency_key", sa.String(length=120), nullable=True))

    for table_name, index_name, columns in [
        ("orders", "ix_orders_pick_status", ["pick_status"]),
        ("orders", "ix_orders_completion_status", ["completion_status"]),
        ("orders", "ix_orders_auto_allocation_status", ["auto_allocation_status"]),
        ("orders", "ix_orders_completed_without_picking", ["completed_without_picking"]),
        ("orders", "ix_orders_completed_at", ["completed_at"]),
        ("orders", "ix_orders_closed_at", ["closed_at"]),
        ("orders", "ix_orders_picked_at", ["picked_at"]),
        ("order_items", "ix_order_items_stock_reduced_at", ["stock_reduced_at"]),
        ("order_items", "ix_order_items_allocation_status", ["allocation_status"]),
        ("order_items", "ix_order_items_pick_status", ["pick_status"]),
        ("allocations", "ix_allocations_auto_allocated", ["auto_allocated"]),
        ("allocations", "ix_allocations_allocation_source", ["allocation_source"]),
        ("allocation_lines", "ix_allocation_lines_auto_allocated", ["auto_allocated"]),
        ("allocation_lines", "ix_allocation_lines_allocation_source", ["allocation_source"]),
        ("pick_lines", "ix_pick_lines_stock_movement_id", ["stock_movement_id"]),
        ("pick_lines", "ix_pick_lines_stock_reduced_at", ["stock_reduced_at"]),
        ("pick_lines", "ix_pick_lines_idempotency_key", ["idempotency_key"]),
    ]:
        create_index_if_missing(table_name, index_name, columns)

    if supports_alter_foreign_key() and not foreign_key_exists("pick_lines", "fk_pick_lines_stock_movement_id"):
        op.create_foreign_key("fk_pick_lines_stock_movement_id", "pick_lines", "stock_movements", ["stock_movement_id"], ["id"])


def downgrade() -> None:
    if supports_alter_foreign_key() and foreign_key_exists("pick_lines", "fk_pick_lines_stock_movement_id"):
        op.drop_constraint("fk_pick_lines_stock_movement_id", "pick_lines", type_="foreignkey")

    for table_name, index_name in [
        ("pick_lines", "ix_pick_lines_idempotency_key"),
        ("pick_lines", "ix_pick_lines_stock_reduced_at"),
        ("pick_lines", "ix_pick_lines_stock_movement_id"),
        ("allocation_lines", "ix_allocation_lines_allocation_source"),
        ("allocation_lines", "ix_allocation_lines_auto_allocated"),
        ("allocations", "ix_allocations_allocation_source"),
        ("allocations", "ix_allocations_auto_allocated"),
        ("order_items", "ix_order_items_pick_status"),
        ("order_items", "ix_order_items_allocation_status"),
        ("order_items", "ix_order_items_stock_reduced_at"),
        ("orders", "ix_orders_picked_at"),
        ("orders", "ix_orders_closed_at"),
        ("orders", "ix_orders_completed_at"),
        ("orders", "ix_orders_completed_without_picking"),
        ("orders", "ix_orders_auto_allocation_status"),
        ("orders", "ix_orders_completion_status"),
        ("orders", "ix_orders_pick_status"),
    ]:
        drop_index_if_exists(table_name, index_name)

    for column_name in ["idempotency_key", "stock_reduced_at", "stock_movement_id", "quantity_stock_reduced"]:
        drop_column_if_exists("pick_lines", column_name)
    for column_name in ["allocation_source", "auto_allocated"]:
        drop_column_if_exists("allocation_lines", column_name)
        drop_column_if_exists("allocations", column_name)
    for column_name in ["allocation_exception_reason", "pick_status", "allocation_status", "stock_reduced_at", "quantity_stock_reduced"]:
        drop_column_if_exists("order_items", column_name)
    for column_name in [
        "workflow_notes",
        "allocation_exception_reason",
        "picked_at",
        "closed_at",
        "completed_at",
        "completed_without_picking",
        "auto_allocation_status",
        "completion_status",
        "pick_status",
    ]:
        drop_column_if_exists("orders", column_name)
