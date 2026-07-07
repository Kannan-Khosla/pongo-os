"""direct receiving fields

Revision ID: 20260707_0004
Revises: 20260707_0003
Create Date: 2026-07-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260707_0004"
down_revision: str | None = "20260707_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {existing_column["name"] for existing_column in inspector.get_columns(table_name)}
    if column.name not in existing_columns:
        op.add_column(table_name, column)


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


def drop_column_if_present(table_name: str, column_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {existing_column["name"] for existing_column in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    add_column_if_missing("receipts", sa.Column("receipt_type", sa.String(length=40), nullable=True))
    add_column_if_missing("receipts", sa.Column("status", sa.String(length=40), nullable=True))
    add_column_if_missing("receipts", sa.Column("reference_number", sa.String(length=120), nullable=True))
    add_column_if_missing("receipts", sa.Column("created_by", sa.String(length=120), nullable=True))
    add_column_if_missing("receipts", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    add_column_if_missing("receipts", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    create_index_if_missing("receipts", "ix_receipts_receipt_type", ["receipt_type"])
    create_index_if_missing("receipts", "ix_receipts_status", ["status"])
    create_index_if_missing("receipts", "ix_receipts_reference_number", ["reference_number"])
    create_index_if_missing("receipts", "ix_receipts_created_by", ["created_by"])
    create_index_if_missing("receipts", "ix_receipts_received_at", ["received_at"])

    add_column_if_missing("receipt_items", sa.Column("default_location", sa.String(length=200), nullable=True))
    add_column_if_missing("receipt_items", sa.Column("quantity_received", sa.Numeric(14, 3), nullable=True))
    add_column_if_missing("receipt_items", sa.Column("notes", sa.Text(), nullable=True))

    add_column_if_missing("stock_movements", sa.Column("warehouse", sa.String(length=120), nullable=True))
    add_column_if_missing("stock_movements", sa.Column("inventory_location", sa.String(length=200), nullable=True))
    add_column_if_missing("stock_movements", sa.Column("reference_number", sa.String(length=120), nullable=True))
    add_column_if_missing("stock_movements", sa.Column("notes", sa.String(length=500), nullable=True))
    create_index_if_missing("stock_movements", "ix_stock_movements_warehouse", ["warehouse"])
    create_index_if_missing("stock_movements", "ix_stock_movements_inventory_location", ["inventory_location"])
    create_index_if_missing("stock_movements", "ix_stock_movements_reference_number", ["reference_number"])


def downgrade() -> None:
    drop_index_if_present("stock_movements", "ix_stock_movements_reference_number")
    drop_index_if_present("stock_movements", "ix_stock_movements_inventory_location")
    drop_index_if_present("stock_movements", "ix_stock_movements_warehouse")
    drop_column_if_present("stock_movements", "notes")
    drop_column_if_present("stock_movements", "reference_number")
    drop_column_if_present("stock_movements", "inventory_location")
    drop_column_if_present("stock_movements", "warehouse")

    drop_column_if_present("receipt_items", "notes")
    drop_column_if_present("receipt_items", "quantity_received")
    drop_column_if_present("receipt_items", "default_location")

    drop_index_if_present("receipts", "ix_receipts_received_at")
    drop_index_if_present("receipts", "ix_receipts_created_by")
    drop_index_if_present("receipts", "ix_receipts_reference_number")
    drop_index_if_present("receipts", "ix_receipts_status")
    drop_index_if_present("receipts", "ix_receipts_receipt_type")
    drop_column_if_present("receipts", "updated_at")
    drop_column_if_present("receipts", "received_at")
    drop_column_if_present("receipts", "created_by")
    drop_column_if_present("receipts", "reference_number")
    drop_column_if_present("receipts", "status")
    drop_column_if_present("receipts", "receipt_type")
