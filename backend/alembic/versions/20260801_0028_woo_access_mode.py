"""Persist audited WooCommerce access mode changes.

Revision ID: 20260801_0028
Revises: 20260731_0027
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0028"
down_revision = "20260731_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("woocommerce_access_mode_changes"):
        op.create_table(
            "woocommerce_access_mode_changes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("access_mode", sa.String(length=20), nullable=False),
            sa.Column("changed_by", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("access_mode in ('read_only', 'read_write')", name="ck_woo_access_mode_value"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_woo_access_mode_changes_access_mode", "woocommerce_access_mode_changes", ["access_mode"])
        op.create_index("ix_woo_access_mode_changes_changed_by", "woocommerce_access_mode_changes", ["changed_by"])
        op.create_index("ix_woo_access_mode_changes_created_at", "woocommerce_access_mode_changes", ["created_at"])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("woocommerce_access_mode_changes"):
        op.drop_table("woocommerce_access_mode_changes")
