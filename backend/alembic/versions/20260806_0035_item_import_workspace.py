"""Add the guided item import workspace.

Revision ID: 20260806_0035
Revises: 20260806_0034
"""

from alembic import op
import sqlalchemy as sa


revision = "20260806_0035"
down_revision = "20260806_0034"
branch_labels = None
depends_on = None


def add_column_if_missing(table: str, column: sa.Column) -> None:
    columns = {candidate["name"] for candidate in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def create_index_if_missing(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    add_column_if_missing("import_jobs", sa.Column("preview_id", sa.String(36), nullable=True))
    add_column_if_missing("import_jobs", sa.Column("outcome", sa.String(80), nullable=True))
    add_column_if_missing("import_jobs", sa.Column("idempotency_key", sa.String(120), nullable=True))
    add_column_if_missing("import_jobs", sa.Column("result_json", sa.JSON(), nullable=True))
    add_column_if_missing("import_jobs", sa.Column("created_rows", sa.Integer(), nullable=False, server_default="0"))
    add_column_if_missing("import_jobs", sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"))
    add_column_if_missing("import_jobs", sa.Column("unchanged_rows", sa.Integer(), nullable=False, server_default="0"))
    add_column_if_missing("import_jobs", sa.Column("excluded_rows", sa.Integer(), nullable=False, server_default="0"))
    add_column_if_missing("import_jobs", sa.Column("starting_units", sa.Numeric(14, 3), nullable=False, server_default="0"))
    add_column_if_missing("import_jobs", sa.Column("duration_ms", sa.Integer(), nullable=True))
    create_index_if_missing("ix_import_jobs_preview_id", "import_jobs", ["preview_id"])
    create_index_if_missing("ix_import_jobs_outcome", "import_jobs", ["outcome"])
    create_index_if_missing("ix_import_jobs_idempotency_key", "import_jobs", ["idempotency_key"], unique=True)

    add_column_if_missing("import_errors", sa.Column("error_code", sa.String(100), nullable=True))
    add_column_if_missing("import_errors", sa.Column("field_name", sa.String(120), nullable=True))
    add_column_if_missing("import_errors", sa.Column("invalid_value", sa.Text(), nullable=True))
    add_column_if_missing("import_errors", sa.Column("blocking", sa.Boolean(), nullable=False, server_default=sa.true()))
    add_column_if_missing("import_errors", sa.Column("suggested_action", sa.Text(), nullable=True))
    create_index_if_missing("ix_import_errors_error_code", "import_errors", ["error_code"])
    create_index_if_missing("ix_import_errors_field_name", "import_errors", ["field_name"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "import_mapping_profiles" not in tables:
        op.create_table(
            "import_mapping_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("outcome", sa.String(80), nullable=False),
            sa.Column("source_signature", sa.String(64), nullable=False),
            sa.Column("source_headers", sa.JSON(), nullable=False),
            sa.Column("mapping_json", sa.JSON(), nullable=False),
            sa.Column("created_by", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("created_by", "outcome", "name", name="uq_import_mapping_profiles_actor_outcome_name"),
        )
        op.create_index("ix_import_mapping_profiles_outcome", "import_mapping_profiles", ["outcome"])
        op.create_index("ix_import_mapping_profiles_source_signature", "import_mapping_profiles", ["source_signature"])
        op.create_index("ix_import_mapping_profiles_created_by", "import_mapping_profiles", ["created_by"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "import_previews" not in tables:
        op.create_table(
            "import_previews",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("outcome", sa.String(80), nullable=False),
            sa.Column("file_name", sa.String(300), nullable=False),
            sa.Column("file_sha256", sa.String(64), nullable=False),
            sa.Column("source_file_text", sa.Text(), nullable=False),
            sa.Column("schema_version", sa.String(40), nullable=False),
            sa.Column("source_headers", sa.JSON(), nullable=False),
            sa.Column("source_columns_json", sa.JSON(), nullable=False),
            sa.Column("mapping_json", sa.JSON(), nullable=False),
            sa.Column("options_json", sa.JSON(), nullable=False),
            sa.Column("summary_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(80), nullable=False),
            sa.Column("commit_idempotency_key", sa.String(120), nullable=True),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=True),
            sa.Column("created_by", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_import_previews_outcome", "import_previews", ["outcome"])
        op.create_index("ix_import_previews_file_sha256", "import_previews", ["file_sha256"])
        op.create_index("ix_import_previews_status", "import_previews", ["status"])
        op.create_index("ix_import_previews_commit_idempotency_key", "import_previews", ["commit_idempotency_key"], unique=True)
        op.create_index("ix_import_previews_import_job_id", "import_previews", ["import_job_id"])
        op.create_index("ix_import_previews_created_by", "import_previews", ["created_by"])
        op.create_index("ix_import_previews_created_at", "import_previews", ["created_at"])
        op.create_index("ix_import_previews_expires_at", "import_previews", ["expires_at"])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "import_preview_rows" not in tables:
        op.create_table(
            "import_preview_rows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("preview_id", sa.String(36), sa.ForeignKey("import_previews.id", ondelete="CASCADE"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(120), nullable=True),
            sa.Column("barcode", sa.String(120), nullable=True),
            sa.Column("product_name", sa.String(500), nullable=True),
            sa.Column("source_data", sa.JSON(), nullable=False),
            sa.Column("normalized_data", sa.JSON(), nullable=False),
            sa.Column("corrected_data", sa.JSON(), nullable=False),
            sa.Column("existing_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=True),
            sa.Column("source_item_hash", sa.String(64), nullable=True),
            sa.Column("proposed_changes", sa.JSON(), nullable=False),
            sa.Column("issues_json", sa.JSON(), nullable=False),
            sa.Column("state", sa.String(80), nullable=False),
            sa.Column("match_method", sa.String(80), nullable=True),
            sa.Column("excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("preview_id", "row_number", name="uq_import_preview_rows_preview_row"),
        )
        for column in ["preview_id", "sku", "barcode", "product_name", "existing_item_id", "state", "excluded"]:
            op.create_index(f"ix_import_preview_rows_{column}", "import_preview_rows", [column])

    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "item_import_changes" not in tables:
        op.create_table(
            "item_import_changes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("import_job_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=False),
            sa.Column("preview_id", sa.String(36), nullable=False),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("sku", sa.String(120), nullable=True),
            sa.Column("field_name", sa.String(120), nullable=False),
            sa.Column("previous_value", sa.JSON(), nullable=True),
            sa.Column("new_value", sa.JSON(), nullable=True),
            sa.Column("source_filename", sa.String(300), nullable=True),
            sa.Column("outcome", sa.String(80), nullable=False),
            sa.Column("mapping_profile_id", sa.Integer(), sa.ForeignKey("import_mapping_profiles.id"), nullable=True),
            sa.Column("created_by", sa.String(120), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        for column in ["import_job_id", "preview_id", "item_id", "sku", "field_name", "outcome", "mapping_profile_id", "created_by", "created_at"]:
            op.create_index(f"ix_item_import_changes_{column}", "item_import_changes", [column])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ["item_import_changes", "import_preview_rows", "import_previews", "import_mapping_profiles"]:
        if table in tables:
            op.drop_table(table)

    for table, columns in {
        "import_errors": ["suggested_action", "blocking", "invalid_value", "field_name", "error_code"],
        "import_jobs": ["duration_ms", "starting_units", "excluded_rows", "unchanged_rows", "updated_rows", "created_rows", "result_json", "idempotency_key", "outcome", "preview_id"],
    }.items():
        existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
