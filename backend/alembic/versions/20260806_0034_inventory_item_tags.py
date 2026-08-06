"""Add inventory item tags.

Revision ID: 20260806_0034
Revises: 20260805_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_0034"
down_revision = "20260805_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("inventory_items")}
    if "tags" not in columns:
        op.add_column("inventory_items", sa.Column("tags", sa.Text(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("inventory_items")}
    if "tags" in columns:
        op.drop_column("inventory_items", "tags")
