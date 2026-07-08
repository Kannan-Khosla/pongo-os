"""items bulk receiving scanners reports

Revision ID: 20260707_0014
Revises: 20260707_0013
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0014"
down_revision: str | None = "20260707_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_exists(table_name) and not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    if table_exists(table_name) and not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    create_saved_views()
    create_item_notes()
    extend_receipts()
    create_scanner_tables()


def create_saved_views() -> None:
    if not table_exists("ui_saved_views"):
        op.create_table(
            "ui_saved_views",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("view_key", sa.String(length=120), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("page", sa.String(length=80), nullable=False),
            sa.Column("filters_json", sa.Text(), nullable=True),
            sa.Column("columns_json", sa.Text(), nullable=True),
            sa.Column("sort_json", sa.Text(), nullable=True),
            sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, columns in [
        ("ix_ui_saved_views_view_key", ["view_key"]),
        ("ix_ui_saved_views_page", ["page"]),
        ("ix_ui_saved_views_is_default", ["is_default"]),
        ("ix_ui_saved_views_created_by", ["created_by"]),
    ]:
        create_index_if_missing("ui_saved_views", name, columns)


def create_item_notes() -> None:
    if not table_exists("item_notes"):
        op.create_table(
            "item_notes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("note_type", sa.String(length=80), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for name, columns in [
        ("ix_item_notes_inventory_item_id", ["inventory_item_id"]),
        ("ix_item_notes_note_type", ["note_type"]),
        ("ix_item_notes_created_by", ["created_by"]),
    ]:
        create_index_if_missing("item_notes", name, columns)


def extend_receipts() -> None:
    for column in [
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    ]:
        add_column_if_missing("receipts", column)
    for column in [
        sa.Column("line_status", sa.String(length=40), nullable=True),
        sa.Column("scan_input", sa.String(length=500), nullable=True),
    ]:
        add_column_if_missing("receipt_items", column)
    for name, columns in [
        ("ix_receipts_source", ["source"]),
        ("ix_receipts_committed_at", ["committed_at"]),
        ("ix_receipts_cancelled_at", ["cancelled_at"]),
        ("ix_receipt_items_line_status", ["line_status"]),
    ]:
        table_name = "receipts" if name.startswith("ix_receipts") else "receipt_items"
        create_index_if_missing(table_name, name, columns)


def create_scanner_tables() -> None:
    if not table_exists("scanner_sessions"):
        op.create_table(
            "scanner_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_type", sa.String(length=60), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("reference_type", sa.String(length=80), nullable=True),
            sa.Column("reference_id", sa.Integer(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not table_exists("scanner_events"):
        op.create_table(
            "scanner_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("scanner_session_id", sa.Integer(), nullable=True),
            sa.Column("session_type", sa.String(length=60), nullable=False),
            sa.Column("scan_input", sa.String(length=500), nullable=False),
            sa.Column("matched_entity_type", sa.String(length=80), nullable=True),
            sa.Column("matched_entity_id", sa.Integer(), nullable=True),
            sa.Column("result_status", sa.String(length=40), nullable=False),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Numeric(14, 3), nullable=True),
            sa.Column("warehouse", sa.String(length=120), nullable=True),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["scanner_session_id"], ["scanner_sessions.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for table_name, indexed_columns in {
        "scanner_sessions": ["session_type", "status", "reference_type", "reference_id", "created_by", "completed_at"],
        "scanner_events": ["scanner_session_id", "session_type", "scan_input", "matched_entity_type", "matched_entity_id", "result_status", "warehouse", "inventory_location"],
    }.items():
        for column in indexed_columns:
            create_index_if_missing(table_name, f"ix_{table_name}_{column}", [column])
