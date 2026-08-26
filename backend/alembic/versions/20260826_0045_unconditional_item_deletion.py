"""Allow local items to be deleted while retaining operational history.

Revision ID: 20260826_0045
Revises: 20260826_0044
"""

from alembic import op
import sqlalchemy as sa


revision = "20260826_0045"
down_revision = "20260826_0044"
branch_labels = None
depends_on = None


NULLABLE_HISTORY_COLUMNS = {
    "allocation_lines": ["item_id"],
    "cycle_count_lines": ["item_id"],
    "fulfillment_lines": ["item_id"],
    "inventory_audit_events": ["item_id"],
    "inventory_transfer_lines": ["inventory_item_id", "from_inventory_item_location_id"],
    "pick_lines": ["item_id"],
    "stock_adjustment_lines": ["inventory_item_id", "inventory_item_location_id"],
    "stock_movements": ["inventory_item_id"],
}


def upgrade() -> None:
    for table, columns in NULLABLE_HISTORY_COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(column, existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # Deleted item IDs cannot be reconstructed; nullable history references are permanent.
    pass
