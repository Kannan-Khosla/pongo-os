"""Add durable WooCommerce catalog sync staging.

Revision ID: 20260821_0041
Revises: 20260819_0040
"""

from alembic import op
import sqlalchemy as sa


revision = "20260821_0041"
down_revision = "20260819_0040"
branch_labels = None
depends_on = None

CATALOG_ACTIVE = "sync_type = 'catalog' AND status IN ('queued', 'fetching_products', 'fetching_variations', 'matching', 'applying', 'waiting_retry', 'paused', 'cancelling')"


def inspector():
    return sa.inspect(op.get_bind())


def table_names() -> set[str]:
    return set(inspector().get_table_names())


def column_names(table: str) -> set[str]:
    return {column["name"] for column in inspector().get_columns(table)}


def index_names(table: str) -> set[str]:
    return {index["name"] for index in inspector().get_indexes(table)}


def active_mapping_conflicts() -> list[str]:
    connection = op.get_bind()
    checks = (
        (
            "local item",
            "SELECT item_id AS identity, COUNT(*) AS count FROM woo_item_mappings "
            "WHERE active = true GROUP BY item_id HAVING COUNT(*) > 1",
        ),
        (
            "simple product",
            "SELECT woo_product_id AS identity, COUNT(*) AS count FROM woo_item_mappings "
            "WHERE active = true AND woo_variation_id IS NULL "
            "GROUP BY woo_product_id HAVING COUNT(*) > 1",
        ),
        (
            "variation",
            "SELECT woo_variation_id AS identity, COUNT(*) AS count "
            "FROM woo_item_mappings WHERE active = true AND woo_variation_id IS NOT NULL "
            "GROUP BY woo_variation_id HAVING COUNT(*) > 1",
        ),
    )
    conflicts: list[str] = []
    for label, statement in checks:
        rows = connection.execute(sa.text(statement)).mappings().all()
        conflicts.extend(f"{label} {row['identity']} ({row['count']} active mappings)" for row in rows[:5])
    return conflicts


def create_index_if_missing(name: str, table: str, columns: list[str], **kwargs) -> None:
    if name not in index_names(table):
        op.create_index(name, table, columns, **kwargs)


def upgrade() -> None:
    mapping_indexes = index_names("woo_item_mappings")
    required_mapping_indexes = {
        "uq_woo_map_active_item",
        "uq_woo_map_active_product",
        "uq_woo_map_active_variation",
    }
    if not required_mapping_indexes.issubset(mapping_indexes):
        conflicts = active_mapping_conflicts()
        if conflicts:
            sample = "; ".join(conflicts)
            raise RuntimeError(
                "Catalog mapping uniqueness preflight failed. Resolve duplicate active Woo mappings before retrying migration 0041: "
                + sample
            )

    run_columns = column_names("woocommerce_sync_runs")
    with op.batch_alter_table("woocommerce_sync_runs") as batch:
        if "request_key" not in run_columns:
            batch.add_column(sa.Column("request_key", sa.String(120)))
        if "attempt_count" not in run_columns:
            batch.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        if "updated_at" not in run_columns:
            batch.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    create_index_if_missing("ix_woocommerce_sync_runs_request_key", "woocommerce_sync_runs", ["request_key"])
    create_index_if_missing("ix_woocommerce_sync_runs_updated_at", "woocommerce_sync_runs", ["updated_at"])
    create_index_if_missing(
        "uq_woo_catalog_one_active",
        "woocommerce_sync_runs",
        ["sync_type"],
        unique=True,
        postgresql_where=sa.text(CATALOG_ACTIVE),
        sqlite_where=sa.text(CATALOG_ACTIVE),
    )
    create_index_if_missing(
        "uq_woo_catalog_request_key",
        "woocommerce_sync_runs",
        ["sync_type", "request_key"],
        unique=True,
        postgresql_where=sa.text("sync_type = 'catalog' AND request_key IS NOT NULL"),
        sqlite_where=sa.text("sync_type = 'catalog' AND request_key IS NOT NULL"),
    )

    if "woo_catalog_sync_rows" not in table_names():
        op.create_table(
            "woo_catalog_sync_rows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("sync_run_id", sa.Integer(), nullable=False),
            sa.Column("remote_key", sa.String(191), nullable=False),
            sa.Column("remote_type", sa.String(40), nullable=False),
            sa.Column("woo_product_id", sa.Integer()),
            sa.Column("woo_variation_id", sa.Integer()),
            sa.Column("sku", sa.String(120)),
            sa.Column("normalized_sku", sa.String(120)),
            sa.Column("barcode", sa.String(120)),
            sa.Column("product_name", sa.String(500)),
            sa.Column("status", sa.String(40), nullable=False, server_default="staged"),
            sa.Column("action", sa.String(40), nullable=False, server_default="pending"),
            sa.Column("local_item_id", sa.Integer()),
            sa.Column("message", sa.Text()),
            sa.Column("resolution_action", sa.String(40)),
            sa.Column("resolution_item_id", sa.Integer()),
            sa.Column("resolved_by", sa.String(120)),
            sa.Column("resolved_at", sa.DateTime(timezone=True)),
            sa.Column("raw_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["sync_run_id"], ["woocommerce_sync_runs.id"], name="fk_woo_catalog_row_run", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["local_item_id"], ["inventory_items.id"], name="fk_woo_catalog_row_item"),
            sa.ForeignKeyConstraint(["resolution_item_id"], ["inventory_items.id"], name="fk_woo_catalog_row_resolution_item"),
            sa.UniqueConstraint("sync_run_id", "remote_key", name="uq_woo_catalog_row_run_remote"),
        )

    for name, columns in (
        ("ix_woo_catalog_sync_rows_sync_run_id", ["sync_run_id"]),
        ("ix_woo_catalog_sync_rows_remote_type", ["remote_type"]),
        ("ix_woo_catalog_sync_rows_woo_product_id", ["woo_product_id"]),
        ("ix_woo_catalog_sync_rows_woo_variation_id", ["woo_variation_id"]),
        ("ix_woo_catalog_sync_rows_sku", ["sku"]),
        ("ix_woo_catalog_sync_rows_normalized_sku", ["normalized_sku"]),
        ("ix_woo_catalog_sync_rows_barcode", ["barcode"]),
        ("ix_woo_catalog_sync_rows_status", ["status"]),
        ("ix_woo_catalog_sync_rows_action", ["action"]),
        ("ix_woo_catalog_sync_rows_local_item_id", ["local_item_id"]),
        ("ix_woo_catalog_sync_rows_resolution_action", ["resolution_action"]),
        ("ix_woo_catalog_sync_rows_resolution_item_id", ["resolution_item_id"]),
        ("ix_woo_catalog_sync_rows_resolved_by", ["resolved_by"]),
        ("ix_woo_catalog_sync_rows_resolved_at", ["resolved_at"]),
        ("ix_woo_catalog_sync_rows_created_at", ["created_at"]),
        ("ix_woo_catalog_sync_rows_updated_at", ["updated_at"]),
        ("ix_woo_catalog_row_run_status", ["sync_run_id", "status"]),
    ):
        create_index_if_missing(name, "woo_catalog_sync_rows", columns)

    create_index_if_missing(
        "uq_woo_map_active_item",
        "woo_item_mappings",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
        sqlite_where=sa.text("active = 1"),
    )
    create_index_if_missing(
        "uq_woo_map_active_product",
        "woo_item_mappings",
        ["woo_product_id"],
        unique=True,
        postgresql_where=sa.text("active = true AND woo_variation_id IS NULL"),
        sqlite_where=sa.text("active = 1 AND woo_variation_id IS NULL"),
    )
    create_index_if_missing(
        "uq_woo_map_active_variation",
        "woo_item_mappings",
        ["woo_variation_id"],
        unique=True,
        postgresql_where=sa.text("active = true AND woo_variation_id IS NOT NULL"),
        sqlite_where=sa.text("active = 1 AND woo_variation_id IS NOT NULL"),
    )


def downgrade() -> None:
    if "woo_catalog_sync_rows" in table_names():
        op.drop_table("woo_catalog_sync_rows")

    for name in (
        "uq_woo_map_active_variation",
        "uq_woo_map_active_product",
        "uq_woo_map_active_item",
    ):
        if name in index_names("woo_item_mappings"):
            op.drop_index(name, table_name="woo_item_mappings")

    for name in (
        "uq_woo_catalog_request_key",
        "uq_woo_catalog_one_active",
        "ix_woocommerce_sync_runs_updated_at",
        "ix_woocommerce_sync_runs_request_key",
    ):
        if name in index_names("woocommerce_sync_runs"):
            op.drop_index(name, table_name="woocommerce_sync_runs")

    run_columns = column_names("woocommerce_sync_runs")
    with op.batch_alter_table("woocommerce_sync_runs") as batch:
        for column in ("updated_at", "attempt_count", "request_key"):
            if column in run_columns:
                batch.drop_column(column)
