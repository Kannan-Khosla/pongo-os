"""Add immutable report runs and delivery audit.

Revision ID: 20260730_0022
Revises: 20260726_0021
"""

from alembic import op
import sqlalchemy as sa

revision = "20260730_0022"
down_revision = "20260726_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("report_runs"):
        op.create_table(
            "report_runs",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("report_key", sa.String(length=80), nullable=False),
            sa.Column("title", sa.String(length=240), nullable=False),
            sa.Column("definition_version", sa.Integer(), nullable=False),
            sa.Column("timezone", sa.String(length=80), nullable=False),
            sa.Column("filters", sa.JSON(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False),
            sa.Column("data_hash", sa.String(length=64), nullable=False),
            sa.Column("generated_by", sa.String(length=120), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_report_runs_report_key", "report_runs", ["report_key"])
        op.create_index("ix_report_runs_data_hash", "report_runs", ["data_hash"])
        op.create_index("ix_report_runs_generated_at", "report_runs", ["generated_at"])

    inspector = sa.inspect(bind)
    if not inspector.has_table("report_deliveries"):
        op.create_table(
            "report_deliveries",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("report_run_id", sa.String(length=36), nullable=False),
            sa.Column("channel", sa.String(length=40), nullable=False),
            sa.Column("recipient", sa.String(length=320), nullable=True),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("external_url", sa.String(length=1000), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["report_run_id"], ["report_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_report_deliveries_report_run_id", "report_deliveries", ["report_run_id"])
        op.create_index("ix_report_deliveries_channel", "report_deliveries", ["channel"])
        op.create_index("ix_report_deliveries_recipient", "report_deliveries", ["recipient"])
        op.create_index("ix_report_deliveries_status", "report_deliveries", ["status"])
        op.create_index("ix_report_deliveries_created_at", "report_deliveries", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_report_deliveries_created_at", table_name="report_deliveries")
    op.drop_index("ix_report_deliveries_status", table_name="report_deliveries")
    op.drop_index("ix_report_deliveries_recipient", table_name="report_deliveries")
    op.drop_index("ix_report_deliveries_channel", table_name="report_deliveries")
    op.drop_index("ix_report_deliveries_report_run_id", table_name="report_deliveries")
    op.drop_table("report_deliveries")
    op.drop_index("ix_report_runs_generated_at", table_name="report_runs")
    op.drop_index("ix_report_runs_data_hash", table_name="report_runs")
    op.drop_index("ix_report_runs_report_key", table_name="report_runs")
    op.drop_table("report_runs")
