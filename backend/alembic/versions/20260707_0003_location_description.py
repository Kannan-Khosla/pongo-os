"""location description

Revision ID: 20260707_0003
Revises: 20260707_0002
Create Date: 2026-07-07
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260707_0003"
down_revision: str | None = "20260707_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("inventory_locations")}

    if "description" not in existing_columns:
        op.add_column("inventory_locations", sa.Column("description", sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("inventory_locations")}

    if "description" in existing_columns:
        op.drop_column("inventory_locations", "description")
