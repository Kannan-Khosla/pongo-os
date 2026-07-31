"""Add resumable WooCommerce stock sync jobs.

Revision ID: 20260731_0024
Revises: 20260731_0023
"""

from alembic import op
import sqlalchemy as sa

revision = "20260731_0024"
down_revision = "20260731_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("woo_stock_sync_jobs"):
        op.create_table(
            "woo_stock_sync_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("force", sa.Boolean(), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=True),
        sa.Column("chunk_size", sa.Integer(), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False),
        sa.Column("processed_items", sa.Integer(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("dry_run_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_unmapped_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("last_item_id", sa.Integer(), nullable=False),
        sa.Column("retry_item_ids", sa.JSON(), nullable=True),
        sa.Column("retry_attempt", sa.Integer(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_woo_stock_sync_jobs_idempotency_key"),
        )
    existing_indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("woo_stock_sync_jobs")}
    for column in ["idempotency_key", "status", "requested_by", "started_at", "completed_at", "created_at", "updated_at"]:
        index_name = f"ix_woo_stock_sync_jobs_{column}"
        if index_name not in existing_indexes:
            op.create_index(index_name, "woo_stock_sync_jobs", [column])
    inspector = sa.inspect(op.get_bind())
    required_columns = {
        "id", "idempotency_key", "status", "force", "requested_by", "chunk_size", "total_items",
        "processed_items", "sent_count", "dry_run_count", "failed_count", "skipped_unmapped_count",
        "unchanged_count", "last_item_id", "retry_item_ids", "retry_attempt", "errors", "last_error",
        "started_at", "completed_at", "created_at", "updated_at",
    }
    columns = {column["name"] for column in inspector.get_columns("woo_stock_sync_jobs")}
    unique_sets = {frozenset(constraint.get("column_names") or []) for constraint in inspector.get_unique_constraints("woo_stock_sync_jobs")}
    unique_sets.update(frozenset(index.get("column_names") or []) for index in inspector.get_indexes("woo_stock_sync_jobs") if index.get("unique"))
    missing = required_columns - columns
    missing_unique = frozenset({"idempotency_key"}) not in unique_sets
    if missing or missing_unique:
        raise RuntimeError(
            "Existing woo_stock_sync_jobs table has an unexpected shape: "
            f"missing_columns={sorted(missing)}, missing_idempotency_unique={missing_unique}"
        )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("woo_stock_sync_jobs"):
        op.drop_table("woo_stock_sync_jobs")
