"""woocommerce order webhook deliveries

Revision ID: 20260710_0018
Revises: 20260709_0017
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0018"
down_revision: str | None = "20260709_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    if not table_exists("woocommerce_webhook_deliveries"):
        op.create_table(
            "woocommerce_webhook_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("delivery_id", sa.String(length=191), nullable=False),
            sa.Column("webhook_id", sa.String(length=80), nullable=False),
            sa.Column("payload_sha256", sa.String(length=64), nullable=False),
            sa.Column("topic", sa.String(length=120), nullable=False),
            sa.Column("resource", sa.String(length=80), nullable=True),
            sa.Column("event", sa.String(length=80), nullable=True),
            sa.Column("source_host", sa.String(length=255), nullable=True),
            sa.Column("woo_order_id", sa.Integer(), nullable=True),
            sa.Column("local_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("sync_run_id", sa.Integer(), sa.ForeignKey("woocommerce_sync_runs.id"), nullable=True),
            sa.Column("processing_status", sa.String(length=40), nullable=False, server_default="received"),
            sa.Column("created_order", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("webhook_id", "delivery_id", "payload_sha256", name="uq_woo_webhook_delivery_identity"),
        )
    for index_name, columns in [
        ("ix_woocommerce_webhook_deliveries_delivery_id", ["delivery_id"]),
        ("ix_woocommerce_webhook_deliveries_webhook_id", ["webhook_id"]),
        ("ix_woocommerce_webhook_deliveries_payload_sha256", ["payload_sha256"]),
        ("ix_woocommerce_webhook_deliveries_topic", ["topic"]),
        ("ix_woocommerce_webhook_deliveries_resource", ["resource"]),
        ("ix_woocommerce_webhook_deliveries_event", ["event"]),
        ("ix_woocommerce_webhook_deliveries_source_host", ["source_host"]),
        ("ix_woocommerce_webhook_deliveries_woo_order_id", ["woo_order_id"]),
        ("ix_woocommerce_webhook_deliveries_local_order_id", ["local_order_id"]),
        ("ix_woocommerce_webhook_deliveries_sync_run_id", ["sync_run_id"]),
        ("ix_woocommerce_webhook_deliveries_processing_status", ["processing_status"]),
        ("ix_woocommerce_webhook_deliveries_created_order", ["created_order"]),
        ("ix_woocommerce_webhook_deliveries_received_at", ["received_at"]),
        ("ix_woocommerce_webhook_deliveries_processed_at", ["processed_at"]),
        ("ix_woocommerce_webhook_deliveries_updated_at", ["updated_at"]),
    ]:
        if not index_exists("woocommerce_webhook_deliveries", index_name):
            op.create_index(index_name, "woocommerce_webhook_deliveries", columns)


def downgrade() -> None:
    if table_exists("woocommerce_webhook_deliveries"):
        op.drop_table("woocommerce_webhook_deliveries")
