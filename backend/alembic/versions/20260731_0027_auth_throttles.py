"""Persist registration throttling.

Revision ID: 20260731_0027
Revises: 20260731_0026
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0027"
down_revision = "20260731_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("auth_throttles"):
        op.create_table(
            "auth_throttles",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("throttle_key", sa.String(length=80), nullable=False),
            sa.Column("failed_attempt_count", sa.Integer(), nullable=False),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("throttle_key", name="uq_auth_throttles_key"),
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("auth_throttles")}
    if "ix_auth_throttles_throttle_key" not in indexes:
        op.create_index("ix_auth_throttles_throttle_key", "auth_throttles", ["throttle_key"])
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("auth_throttles")}
    unique_sets = {frozenset(constraint.get("column_names") or []) for constraint in inspector.get_unique_constraints("auth_throttles")}
    unique_sets.update(frozenset(index.get("column_names") or []) for index in inspector.get_indexes("auth_throttles") if index.get("unique"))
    required = {"id", "throttle_key", "failed_attempt_count", "locked_until", "created_at", "updated_at"}
    if required - columns or frozenset({"throttle_key"}) not in unique_sets:
        raise RuntimeError("Existing auth_throttles table has an unexpected shape.")


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("auth_throttles"):
        op.drop_table("auth_throttles")
