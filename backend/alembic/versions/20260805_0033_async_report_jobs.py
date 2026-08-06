"""Add asynchronous report jobs.

Revision ID: 20260805_0033
Revises: 20260805_0032
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0033"
down_revision = "20260805_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    report_run_columns = {column["name"] for column in inspector.get_columns("report_runs")}
    for name, column_type in (
        ("csv_artifact", sa.LargeBinary()),
        ("csv_artifact_hash", sa.String(length=64)),
        ("pdf_artifact", sa.LargeBinary()),
        ("pdf_artifact_hash", sa.String(length=64)),
    ):
        if name not in report_run_columns:
            op.add_column("report_runs", sa.Column(name, column_type, nullable=True))
    if "report_jobs" in inspector.get_table_names():
        return
    op.create_table(
        "report_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_key", sa.String(length=80), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("generated_by", sa.String(length=120), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("previous_run_id", sa.String(length=36), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["previous_run_id"], ["report_runs.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["report_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("report_key", "request_key", "status", "run_id", "previous_run_id", "created_at", "updated_at"):
        op.create_index(f"ix_report_jobs_{column}", "report_jobs", [column], unique=False)
    op.create_index(
        "uq_report_jobs_active_request",
        "report_jobs",
        ["request_key"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
        sqlite_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    if "report_jobs" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("report_jobs")
    report_run_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("report_runs")}
    for name in ("pdf_artifact_hash", "pdf_artifact", "csv_artifact_hash", "csv_artifact"):
        if name in report_run_columns:
            op.drop_column("report_runs", name)
