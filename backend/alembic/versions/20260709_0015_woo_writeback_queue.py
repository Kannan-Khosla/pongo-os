"""woo writeback queue

Revision ID: 20260709_0015
Revises: 20260707_0014
Create Date: 2026-07-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260709_0015"
down_revision: str | None = "20260707_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    if not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not table_exists("woo_writeback_queue"):
        op.create_table(
            "woo_writeback_queue",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("operation_type", sa.String(length=80), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("woo_entity_id", sa.Integer(), nullable=True),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("environment", sa.String(length=40), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("preview_json", sa.JSON(), nullable=False),
            sa.Column("response_json", sa.JSON(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        )
    for index_name, columns in [
        ("ix_woo_writeback_queue_operation_type", ["operation_type"]),
        ("ix_woo_writeback_queue_entity_type", ["entity_type"]),
        ("ix_woo_writeback_queue_entity_id", ["entity_id"]),
        ("ix_woo_writeback_queue_woo_entity_id", ["woo_entity_id"]),
        ("ix_woo_writeback_queue_status", ["status"]),
        ("ix_woo_writeback_queue_environment", ["environment"]),
        ("ix_woo_writeback_queue_dry_run", ["dry_run"]),
        ("ix_woo_writeback_queue_created_at", ["created_at"]),
        ("ix_woo_writeback_queue_approved_at", ["approved_at"]),
        ("ix_woo_writeback_queue_sent_at", ["sent_at"]),
    ]:
        create_index_if_missing("woo_writeback_queue", index_name, columns)


def downgrade() -> None:
    if table_exists("woo_writeback_queue"):
        op.drop_table("woo_writeback_queue")
