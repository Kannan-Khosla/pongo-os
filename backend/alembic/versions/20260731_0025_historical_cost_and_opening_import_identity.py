"""Freeze fulfillment cost and deduplicate opening-stock imports.

Revision ID: 20260731_0025
Revises: 20260731_0024
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0025"
down_revision = "20260731_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("fulfillment_lines") or not inspector.has_table("import_jobs"):
        raise RuntimeError("Required fulfillment_lines and import_jobs tables are missing before revision 0025.")
    columns = {column["name"] for column in inspector.get_columns("fulfillment_lines")}
    if "unit_cost" not in columns:
        with op.batch_alter_table("fulfillment_lines") as batch:
            batch.add_column(sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True))

    inspector = sa.inspect(bind)
    if inspector.has_table("import_jobs"):
        duplicate_groups = bind.execute(
            sa.text(
                "SELECT file_sha256 FROM import_jobs "
                "WHERE import_type = 'items_enrichment_opening_stock' AND file_sha256 IS NOT NULL "
                "GROUP BY file_sha256 HAVING COUNT(*) > 1"
            )
        ).scalars().all()
        for file_sha256 in duplicate_groups:
            duplicate_ids = bind.execute(
                sa.text(
                    "SELECT id FROM import_jobs WHERE import_type = 'items_enrichment_opening_stock' "
                    "AND file_sha256 = :file_sha256 ORDER BY id"
                ),
                {"file_sha256": file_sha256},
            ).scalars().all()[1:]
            if duplicate_ids:
                bind.execute(
                    sa.text(
                        "UPDATE import_jobs SET import_type = 'items_enrichment_opening_stock_duplicate' "
                        "WHERE id IN :duplicate_ids"
                    ).bindparams(sa.bindparam("duplicate_ids", expanding=True)),
                    {"duplicate_ids": duplicate_ids},
                )
        indexes = {index["name"] for index in inspector.get_indexes("import_jobs")}
        if "uq_import_jobs_opening_file" not in indexes:
            op.create_index(
                "uq_import_jobs_opening_file",
                "import_jobs",
                ["import_type", "file_sha256"],
                unique=True,
                postgresql_where=sa.text("import_type = 'items_enrichment_opening_stock' AND file_sha256 IS NOT NULL"),
                sqlite_where=sa.text("import_type = 'items_enrichment_opening_stock' AND file_sha256 IS NOT NULL"),
            )
    inspector = sa.inspect(bind)
    if "unit_cost" not in {column["name"] for column in inspector.get_columns("fulfillment_lines")}:
        raise RuntimeError("fulfillment_lines.unit_cost was not created.")
    if "uq_import_jobs_opening_file" not in {index["name"] for index in inspector.get_indexes("import_jobs")}:
        raise RuntimeError("Opening-stock import identity index was not created.")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("import_jobs"):
        indexes = {index["name"] for index in inspector.get_indexes("import_jobs")}
        if "uq_import_jobs_opening_file" in indexes:
            op.drop_index("uq_import_jobs_opening_file", table_name="import_jobs")

    inspector = sa.inspect(bind)
    if inspector.has_table("fulfillment_lines"):
        columns = {column["name"] for column in inspector.get_columns("fulfillment_lines")}
        if "unit_cost" in columns:
            with op.batch_alter_table("fulfillment_lines") as batch:
                batch.drop_column("unit_cost")
