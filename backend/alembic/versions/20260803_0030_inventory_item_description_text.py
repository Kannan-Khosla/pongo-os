"""Allow complete WooCommerce product descriptions.

Revision ID: 20260803_0030
Revises: 20260801_0029
"""

from alembic import op
import sqlalchemy as sa


revision = "20260803_0030"
down_revision = "20260801_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("inventory_items") as batch:
        batch.alter_column(
            "description",
            existing_type=sa.String(length=500),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("inventory_items") as batch:
        batch.alter_column(
            "description",
            existing_type=sa.Text(),
            type_=sa.String(length=500),
            existing_nullable=True,
        )
