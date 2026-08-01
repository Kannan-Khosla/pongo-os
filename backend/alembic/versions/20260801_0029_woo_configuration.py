"""Persist encrypted WooCommerce connection configuration.

Revision ID: 20260801_0029
Revises: 20260801_0028
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0029"
down_revision = "20260801_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("woocommerce_configuration"):
        op.create_table(
            "woocommerce_configuration",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("base_url", sa.String(length=500), nullable=False),
            sa.Column("allowed_host", sa.String(length=255), nullable=False),
            sa.Column("consumer_key_ciphertext", sa.Text(), nullable=False),
            sa.Column("consumer_secret_ciphertext", sa.Text(), nullable=False),
            sa.Column("updated_by", sa.String(length=120), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_woo_configuration_singleton"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_woocommerce_configuration_updated_by", "woocommerce_configuration", ["updated_by"])
        op.create_index("ix_woocommerce_configuration_updated_at", "woocommerce_configuration", ["updated_at"])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("woocommerce_configuration"):
        op.drop_table("woocommerce_configuration")
