"""mvp hardening dashboard remap routes

Revision ID: 20260707_0012
Revises: 20260707_0011
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0012"
down_revision: str | None = "20260707_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def index_exists(table_name: str, index_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    if not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not table_exists("woo_item_mappings"):
        op.create_table(
            "woo_item_mappings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=False),
            sa.Column("woo_product_id", sa.Integer(), nullable=False),
            sa.Column("woo_variation_id", sa.Integer(), nullable=True),
            sa.Column("woo_sku", sa.String(length=120), nullable=True),
            sa.Column("woo_name", sa.String(length=500), nullable=True),
            sa.Column("mapping_source", sa.String(length=40), nullable=False),
            sa.Column("confidence", sa.Numeric(5, 2), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["item_id"], ["inventory_items.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("item_id", "woo_product_id", "woo_variation_id", "active", name="uq_woo_item_mappings_item_remote_active"),
        )
    for index_name, columns in [
        ("ix_woo_item_mappings_item_id", ["item_id"]),
        ("ix_woo_item_mappings_woo_product_id", ["woo_product_id"]),
        ("ix_woo_item_mappings_woo_variation_id", ["woo_variation_id"]),
        ("ix_woo_item_mappings_woo_sku", ["woo_sku"]),
        ("ix_woo_item_mappings_mapping_source", ["mapping_source"]),
        ("ix_woo_item_mappings_active", ["active"]),
        ("ix_woo_item_mappings_created_at", ["created_at"]),
        ("ix_woo_item_mappings_updated_at", ["updated_at"]),
    ]:
        create_index_if_missing("woo_item_mappings", index_name, columns)

    route_columns = [
        ("map_provider", sa.Column("map_provider", sa.String(length=80), nullable=True)),
        ("optimization_status", sa.Column("optimization_status", sa.String(length=80), nullable=True)),
        ("estimated_duration_minutes", sa.Column("estimated_duration_minutes", sa.Integer(), nullable=True)),
    ]
    for column_name, column in route_columns:
        if not column_exists("routes", column_name):
            op.add_column("routes", column)
    create_index_if_missing("routes", "ix_routes_optimization_status", ["optimization_status"])

    stop_columns = [
        ("geocode_status", sa.Column("geocode_status", sa.String(length=40), nullable=True)),
        ("geocode_provider", sa.Column("geocode_provider", sa.String(length=80), nullable=True)),
        ("geocode_error", sa.Column("geocode_error", sa.Text(), nullable=True)),
        ("internal_notes", sa.Column("internal_notes", sa.Text(), nullable=True)),
    ]
    for column_name, column in stop_columns:
        if not column_exists("route_stops", column_name):
            op.add_column("route_stops", column)
    create_index_if_missing("route_stops", "ix_route_stops_geocode_status", ["geocode_status"])


def downgrade() -> None:
    pass
