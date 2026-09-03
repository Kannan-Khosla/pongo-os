"""Store the pre-receiving unit cost for complete invoice reversal.

Revision ID: 20260901_0046
Revises: 20260826_0045
"""

from alembic import op
import sqlalchemy as sa


revision = "20260901_0046"
down_revision = "20260826_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("receipt_items")}
    if "previous_unit_cost" not in columns:
        op.add_column("receipt_items", sa.Column("previous_unit_cost", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("receipt_items")}
    if "previous_unit_cost" in columns:
        op.drop_column("receipt_items", "previous_unit_cost")
