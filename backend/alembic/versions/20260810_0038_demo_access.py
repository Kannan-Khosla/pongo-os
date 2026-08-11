"""Add isolated demo access level.

Revision ID: 20260810_0038
Revises: 20260807_0037
"""

from alembic import op
import sqlalchemy as sa


revision = "20260810_0038"
down_revision = "20260807_0037"
branch_labels = None
depends_on = None

USER_COLUMN_ORDER = (
    "id",
    "email",
    "display_name",
    "password_hash",
    "active",
    "failed_login_count",
    "locked_until",
    "last_login_at",
    "created_at",
    "updated_at",
    "access_level",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    constraints = {constraint["name"] for constraint in inspector.get_check_constraints("users")}
    with op.batch_alter_table("users", partial_reordering=[USER_COLUMN_ORDER]) as batch:
        if "access_level" not in columns:
            batch.add_column(sa.Column("access_level", sa.String(20), nullable=False, server_default="staff"))
        if "ck_users_access_level" not in constraints:
            batch.create_check_constraint("ck_users_access_level", "access_level IN ('staff', 'demo')")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    constraints = {constraint["name"] for constraint in inspector.get_check_constraints("users")}
    with op.batch_alter_table("users", partial_reordering=[USER_COLUMN_ORDER[:-1]]) as batch:
        if "ck_users_access_level" in constraints:
            batch.drop_constraint("ck_users_access_level", type_="check")
        if "access_level" in columns:
            batch.drop_column("access_level")
