"""item csv fields

Revision ID: 20260707_0002
Revises: 20260707_0001
Create Date: 2026-07-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260707_0002"
down_revision: str | None = "20260707_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("inventory_items")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("inventory_items")}

    if "inventory_location" not in existing_columns:
        op.add_column("inventory_items", sa.Column("inventory_location", sa.String(length=200), nullable=True))
    if "default_location" not in existing_columns:
        op.add_column("inventory_items", sa.Column("default_location", sa.String(length=200), nullable=True))
    if "non_inventory" not in existing_columns:
        op.add_column("inventory_items", sa.Column("non_inventory", sa.Boolean(), nullable=False, server_default=sa.false()))

    if "ix_inventory_items_inventory_location" not in existing_indexes:
        op.create_index(op.f("ix_inventory_items_inventory_location"), "inventory_items", ["inventory_location"], unique=False)
    if "ix_inventory_items_non_inventory" not in existing_indexes:
        op.create_index(op.f("ix_inventory_items_non_inventory"), "inventory_items", ["non_inventory"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("inventory_items")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("inventory_items")}

    if "ix_inventory_items_non_inventory" in existing_indexes:
        op.drop_index(op.f("ix_inventory_items_non_inventory"), table_name="inventory_items")
    if "ix_inventory_items_inventory_location" in existing_indexes:
        op.drop_index(op.f("ix_inventory_items_inventory_location"), table_name="inventory_items")
    if "non_inventory" in existing_columns:
        op.drop_column("inventory_items", "non_inventory")
    if "default_location" in existing_columns:
        op.drop_column("inventory_items", "default_location")
    if "inventory_location" in existing_columns:
        op.drop_column("inventory_items", "inventory_location")
