"""Add WooCommerce subscription line snapshots.

Revision ID: 20260818_0039
Revises: 20260810_0038
"""

from alembic import op
import sqlalchemy as sa


revision = "20260818_0039"
down_revision = "20260810_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("woo_subscription_line_snapshots"):
        return
    op.create_table(
        "woo_subscription_line_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("woo_subscription_id", sa.Integer(), nullable=False),
        sa.Column("woo_line_item_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("next_payment_at", sa.DateTime(timezone=True)),
        sa.Column("customer_name", sa.String(240)),
        sa.Column("customer_email", sa.String(240)),
        sa.Column("subscription_total", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(12)),
        sa.Column("woo_product_id", sa.Integer(), nullable=False),
        sa.Column("woo_variation_id", sa.Integer()),
        sa.Column("sku", sa.String(120)),
        sa.Column("product_name", sa.String(500)),
        sa.Column("quantity_per_renewal", sa.Numeric(14, 3)),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "woo_subscription_id",
            "woo_line_item_id",
            name="uq_woo_subscription_line_snapshot_remote_line",
        ),
    )
    for column in (
        "woo_subscription_id",
        "status",
        "next_payment_at",
        "customer_email",
        "woo_product_id",
        "woo_variation_id",
        "sku",
        "synced_at",
    ):
        op.create_index(
            f"ix_woo_subscription_line_snapshots_{column}",
            "woo_subscription_line_snapshots",
            [column],
        )
    op.create_index(
        "ix_woo_subscription_line_snapshot_product_variation",
        "woo_subscription_line_snapshots",
        ["woo_product_id", "woo_variation_id"],
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("woo_subscription_line_snapshots"):
        op.drop_table("woo_subscription_line_snapshots")
