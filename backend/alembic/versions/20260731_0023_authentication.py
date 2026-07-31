"""Add simple staff authentication without roles.

Revision ID: 20260731_0023
Revises: 20260730_0022
"""

from alembic import op
import sqlalchemy as sa

revision = "20260731_0023"
down_revision = "20260730_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("users"):
        op.create_table(
            "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        )
    create_index_if_missing("users", "ix_users_email", ["email"])
    create_index_if_missing("users", "ix_users_active", ["active"])
    if not sa.inspect(op.get_bind()).has_table("user_sessions"):
        op.create_table(
            "user_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        )
    create_index_if_missing("user_sessions", "ix_user_sessions_user_id", ["user_id"])
    create_index_if_missing("user_sessions", "ix_user_sessions_token_hash", ["token_hash"])
    create_index_if_missing("user_sessions", "ix_user_sessions_expires_at", ["expires_at"])
    create_index_if_missing("user_sessions", "ix_user_sessions_revoked_at", ["revoked_at"])
    assert_table_shape(
        "users",
        {"id", "email", "display_name", "password_hash", "active", "failed_login_count", "locked_until", "last_login_at", "created_at", "updated_at"},
        {"email"},
    )
    assert_table_shape(
        "user_sessions",
        {"id", "user_id", "token_hash", "expires_at", "revoked_at", "created_at", "updated_at"},
        {"token_hash"},
    )
    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys("user_sessions")
    if not any(key.get("constrained_columns") == ["user_id"] and key.get("referred_table") == "users" for key in foreign_keys):
        raise RuntimeError("Existing user_sessions table is missing its users foreign key.")


def create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)


def assert_table_shape(table_name: str, required_columns: set[str], unique_columns: set[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    missing = required_columns - columns
    unique_sets = {frozenset(constraint.get("column_names") or []) for constraint in inspector.get_unique_constraints(table_name)}
    unique_sets.update(frozenset(index.get("column_names") or []) for index in inspector.get_indexes(table_name) if index.get("unique"))
    missing_unique = frozenset(unique_columns) not in unique_sets
    if missing or missing_unique:
        raise RuntimeError(f"Existing {table_name} table has an unexpected shape: missing_columns={sorted(missing)}, missing_unique={missing_unique}")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("user_sessions"):
        op.drop_table("user_sessions")
    if inspector.has_table("users"):
        op.drop_table("users")
