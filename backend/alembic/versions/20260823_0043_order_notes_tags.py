"""Add internal order metadata and targeted stock-sync jobs.

Revision ID: 20260823_0043
Revises: 20260822_0042
"""

from alembic import op
import sqlalchemy as sa


revision = "20260823_0043"
down_revision = "20260822_0042"
branch_labels = None
depends_on = None


def table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    existing_tables = table_names()
    if "woo_stock_sync_jobs" in existing_tables and "target_item_ids" not in column_names("woo_stock_sync_jobs"):
        op.add_column("woo_stock_sync_jobs", sa.Column("target_item_ids", sa.JSON(), nullable=True))

    if "order_notes" not in existing_tables:
        op.create_table(
            "order_notes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("note_type", sa.String(40), nullable=False, server_default="manual"),
            sa.Column("created_by", sa.String(320), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_notes_order", ondelete="CASCADE"),
        )
        op.create_index("ix_order_notes_order_id", "order_notes", ["order_id"])
        op.create_index("ix_order_notes_note_type", "order_notes", ["note_type"])
        op.create_index("ix_order_notes_created_by", "order_notes", ["created_by"])
        op.create_index("ix_order_notes_created_at", "order_notes", ["created_at"])

    if "order_tags" not in existing_tables:
        op.create_table(
            "order_tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("normalized_name", sa.String(80), nullable=False),
            sa.Column("color", sa.String(7), nullable=False),
            sa.Column("created_by", sa.String(320), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_order_tags_normalized_name", "order_tags", ["normalized_name"], unique=True)
        op.create_index("ix_order_tags_created_by", "order_tags", ["created_by"])

    if "order_tag_assignments" not in existing_tables:
        op.create_table(
            "order_tag_assignments",
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("tag_id", sa.Integer(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("assigned_by", sa.String(320), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_tag_assignments_order", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tag_id"], ["order_tags.id"], name="fk_order_tag_assignments_tag", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("order_id", "tag_id", name="pk_order_tag_assignments"),
        )
        op.create_index("ix_order_tag_assignments_tag_id", "order_tag_assignments", ["tag_id"])
        op.create_index(
            "ix_order_tag_assignments_order_position",
            "order_tag_assignments",
            ["order_id", "position"],
        )


def downgrade() -> None:
    existing_tables = table_names()
    if "order_tag_assignments" in existing_tables:
        op.drop_table("order_tag_assignments")
    if "order_notes" in existing_tables:
        op.drop_table("order_notes")
    if "order_tags" in existing_tables:
        op.drop_table("order_tags")
    if "woo_stock_sync_jobs" in existing_tables and "target_item_ids" in column_names("woo_stock_sync_jobs"):
        op.drop_column("woo_stock_sync_jobs", "target_item_ids")
