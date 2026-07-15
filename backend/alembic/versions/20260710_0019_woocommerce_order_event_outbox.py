"""woocommerce order event outbox

Revision ID: 20260710_0019
Revises: 20260710_0018
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0019"
down_revision: str | None = "20260710_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    if not table_exists("woocommerce_order_events"):
        op.create_table(
            "woocommerce_order_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("webhook_delivery_id", sa.Integer(), sa.ForeignKey("woocommerce_webhook_deliveries.id"), nullable=False),
            sa.Column("local_order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("woo_order_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=80), nullable=False, server_default="order_created"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("webhook_delivery_id", name="uq_woocommerce_order_events_webhook_delivery_id"),
        )
    for index_name, columns in [
        ("ix_woocommerce_order_events_local_order_id", ["local_order_id"]),
        ("ix_woocommerce_order_events_woo_order_id", ["woo_order_id"]),
        ("ix_woocommerce_order_events_event_type", ["event_type"]),
        ("ix_woocommerce_order_events_created_at", ["created_at"]),
    ]:
        if not index_exists("woocommerce_order_events", index_name):
            op.create_index(index_name, "woocommerce_order_events", columns)


def downgrade() -> None:
    if table_exists("woocommerce_order_events"):
        op.drop_table("woocommerce_order_events")
