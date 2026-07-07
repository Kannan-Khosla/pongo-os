"""route creation foundation

Revision ID: 20260707_0011
Revises: 20260707_0010
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0011"
down_revision: str | None = "20260707_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    if not table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    route_columns = [
        ("route_number", sa.Column("route_number", sa.String(length=40), nullable=True)),
        ("driver_name", sa.Column("driver_name", sa.String(length=200), nullable=True)),
        ("vehicle_name", sa.Column("vehicle_name", sa.String(length=200), nullable=True)),
        ("notes", sa.Column("notes", sa.Text(), nullable=True)),
        ("finalized_at", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True)),
        ("cancelled_at", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)),
    ]
    for column_name, column in route_columns:
        if not column_exists("routes", column_name):
            op.add_column("routes", column)
    for index_name, columns, unique in [
        ("ix_routes_route_number", ["route_number"], True),
        ("ix_routes_driver_name", ["driver_name"], False),
        ("ix_routes_vehicle_name", ["vehicle_name"], False),
        ("ix_routes_finalized_at", ["finalized_at"], False),
        ("ix_routes_cancelled_at", ["cancelled_at"], False),
    ]:
        create_index_if_missing("routes", index_name, columns, unique)

    stop_columns = [
        ("stop_sequence", sa.Column("stop_sequence", sa.Integer(), nullable=True)),
        ("woo_order_id", sa.Column("woo_order_id", sa.Integer(), nullable=True)),
        ("woo_order_number", sa.Column("woo_order_number", sa.String(length=120), nullable=True)),
        ("customer_email", sa.Column("customer_email", sa.String(length=240), nullable=True)),
        ("customer_phone", sa.Column("customer_phone", sa.String(length=80), nullable=True)),
        ("shipping_summary", sa.Column("shipping_summary", sa.JSON(), nullable=True)),
        ("delivery_notes", sa.Column("delivery_notes", sa.Text(), nullable=True)),
        ("local_status", sa.Column("local_status", sa.String(length=80), nullable=True)),
        ("stop_status", sa.Column("stop_status", sa.String(length=40), nullable=True)),
    ]
    for column_name, column in stop_columns:
        if not column_exists("route_stops", column_name):
            op.add_column("route_stops", column)
    for index_name, columns in [
        ("ix_route_stops_stop_sequence", ["stop_sequence"]),
        ("ix_route_stops_woo_order_id", ["woo_order_id"]),
        ("ix_route_stops_woo_order_number", ["woo_order_number"]),
        ("ix_route_stops_customer_email", ["customer_email"]),
        ("ix_route_stops_local_status", ["local_status"]),
        ("ix_route_stops_stop_status", ["stop_status"]),
    ]:
        create_index_if_missing("route_stops", index_name, columns)


def downgrade() -> None:
    # Keep additive columns on downgrade to avoid data loss in local route audit
    # rows. Earlier migrations created the placeholder route tables.
    pass
