"""Add versioned metric cache and reporting indexes.

Revision ID: 20260805_0032
Revises: 20260805_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0032"
down_revision = "20260805_0031"
branch_labels = None
depends_on = None


VISIBLE_ORDERS_SQL = "(is_historical_snapshot = false OR historical_source_present = true)"
REPORTING_DATE_SQL = "COALESCE(placed_on, date_created, completed_on, created_at)"
NORMALIZED_EMAIL_SQL = "LOWER(TRIM(customer_email))"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "metric_versions" not in tables:
        op.create_table(
            "metric_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.bulk_insert(sa.table("metric_versions", sa.column("id", sa.Integer()), sa.column("version", sa.BigInteger())), [{"id": 1, "version": 0}])
    if "metric_cache" not in tables:
        op.create_table(
            "metric_cache",
            sa.Column("cache_key", sa.String(length=64), primary_key=True),
            sa.Column("namespace", sa.String(length=80), nullable=False),
            sa.Column("params", sa.JSON(), nullable=False),
            sa.Column("source_version", sa.BigInteger(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("refresh_requested_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_metric_cache_namespace_version", "metric_cache", ["namespace", "source_version"])

    op.execute(sa.text(
        f"CREATE INDEX IF NOT EXISTS ix_orders_reporting_date "
        f"ON orders ({REPORTING_DATE_SQL}) WHERE {VISIBLE_ORDERS_SQL}"
    ))
    op.execute(sa.text(
        f"CREATE INDEX IF NOT EXISTS ix_orders_reporting_customer_date "
        f"ON orders ({NORMALIZED_EMAIL_SQL}, {REPORTING_DATE_SQL}) WHERE {VISIBLE_ORDERS_SQL}"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_orders_reporting_customer_date"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_orders_reporting_date"))
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "metric_cache" in tables:
        op.drop_table("metric_cache")
    if "metric_versions" in tables:
        op.drop_table("metric_versions")
