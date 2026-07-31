"""Add item enrichment import identity fields.

Revision ID: 20260715_0020
Revises: 20260710_0019
"""

from alembic import op
import sqlalchemy as sa

revision = "20260715_0020"
down_revision = "20260710_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    item_columns = {column["name"] for column in inspector.get_columns("inventory_items")}
    job_columns = {column["name"] for column in inspector.get_columns("import_jobs")}
    for column in (
        sa.Column("woo_name", sa.String(length=500), nullable=True),
        sa.Column("woo_parent_name", sa.String(length=500), nullable=True),
        sa.Column("woo_variation_attributes", sa.JSON(), nullable=True),
    ):
        if column.name not in item_columns:
            op.add_column("inventory_items", column)
    for column in (
        sa.Column("file_sha256", sa.String(length=64), nullable=True),
        sa.Column("options_json", sa.JSON(), nullable=True),
    ):
        if column.name not in job_columns:
            op.add_column("import_jobs", column)
    if "ix_import_jobs_file_sha256" not in {index["name"] for index in inspector.get_indexes("import_jobs")}:
        op.create_index("ix_import_jobs_file_sha256", "import_jobs", ["file_sha256"], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "ix_import_jobs_file_sha256" in {index["name"] for index in inspector.get_indexes("import_jobs")}:
        op.drop_index("ix_import_jobs_file_sha256", table_name="import_jobs")
    job_columns = {column["name"] for column in inspector.get_columns("import_jobs")}
    for column_name in ("options_json", "file_sha256"):
        if column_name in job_columns:
            op.drop_column("import_jobs", column_name)
    item_columns = {column["name"] for column in inspector.get_columns("inventory_items")}
    for column_name in ("woo_variation_attributes", "woo_parent_name", "woo_name"):
        if column_name in item_columns:
            op.drop_column("inventory_items", column_name)
