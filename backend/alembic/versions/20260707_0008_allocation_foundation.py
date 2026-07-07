"""allocation foundation

Revision ID: 20260707_0008
Revises: 20260707_0007
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0008"
down_revision: str | None = "20260707_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns, unique=unique)


def drop_index_if_present(table_name: str, index_name: str) -> None:
    if not table_exists(table_name):
        return
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}
    if index_name in existing:
        op.drop_index(index_name, table_name=table_name)


def upgrade() -> None:
    if not table_exists("allocations"):
        op.create_table(
            "allocations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("allocation_number", sa.String(length=40), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("allocation_type", sa.String(length=40), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
            sa.Column("woo_order_id", sa.Integer(), nullable=True),
            sa.Column("woo_order_number", sa.String(length=120), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for index_name, columns, unique in [
        ("ix_allocations_allocation_number", ["allocation_number"], True),
        ("ix_allocations_status", ["status"], False),
        ("ix_allocations_allocation_type", ["allocation_type"], False),
        ("ix_allocations_order_id", ["order_id"], False),
        ("ix_allocations_woo_order_id", ["woo_order_id"], False),
        ("ix_allocations_woo_order_number", ["woo_order_number"], False),
        ("ix_allocations_created_by", ["created_by"], False),
        ("ix_allocations_posted_at", ["posted_at"], False),
        ("ix_allocations_cancelled_at", ["cancelled_at"], False),
    ]:
        create_index_if_missing("allocations", index_name, columns, unique)

    if not table_exists("allocation_lines"):
        op.create_table(
            "allocation_lines",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("allocation_id", sa.Integer(), sa.ForeignKey("allocations.id"), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("order_line_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=False),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("warehouse", sa.String(length=120), nullable=True),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("quantity_ordered", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_previously_allocated", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_to_allocate", sa.Numeric(14, 3), nullable=False),
            sa.Column("quantity_allocated_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("in_stock_before", sa.Numeric(14, 3), nullable=False),
            sa.Column("allocated_before", sa.Numeric(14, 3), nullable=False),
            sa.Column("sellable_before", sa.Numeric(14, 3), nullable=False),
            sa.Column("allocated_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("sellable_after", sa.Numeric(14, 3), nullable=False),
            sa.Column("shortage_quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for index_name, columns in [
        ("ix_allocation_lines_allocation_id", ["allocation_id"]),
        ("ix_allocation_lines_order_id", ["order_id"]),
        ("ix_allocation_lines_order_line_id", ["order_line_id"]),
        ("ix_allocation_lines_item_id", ["item_id"]),
        ("ix_allocation_lines_sku", ["sku"]),
        ("ix_allocation_lines_barcode", ["barcode"]),
        ("ix_allocation_lines_warehouse", ["warehouse"]),
        ("ix_allocation_lines_inventory_location", ["inventory_location"]),
        ("ix_allocation_lines_status", ["status"]),
    ]:
        create_index_if_missing("allocation_lines", index_name, columns)

    if not table_exists("inventory_audit_events"):
        op.create_table(
            "inventory_audit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("quantity_delta", sa.Numeric(14, 3), nullable=False),
            sa.Column("previous_in_stock", sa.Numeric(14, 3), nullable=False),
            sa.Column("new_in_stock", sa.Numeric(14, 3), nullable=False),
            sa.Column("previous_allocated", sa.Numeric(14, 3), nullable=False),
            sa.Column("new_allocated", sa.Numeric(14, 3), nullable=False),
            sa.Column("previous_sellable", sa.Numeric(14, 3), nullable=False),
            sa.Column("new_sellable", sa.Numeric(14, 3), nullable=False),
            sa.Column("warehouse", sa.String(length=120), nullable=True),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("reference_type", sa.String(length=80), nullable=True),
            sa.Column("reference_id", sa.Integer(), nullable=True),
            sa.Column("reference_number", sa.String(length=120), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    for index_name, columns in [
        ("ix_inventory_audit_events_item_id", ["item_id"]),
        ("ix_inventory_audit_events_sku", ["sku"]),
        ("ix_inventory_audit_events_barcode", ["barcode"]),
        ("ix_inventory_audit_events_event_type", ["event_type"]),
        ("ix_inventory_audit_events_warehouse", ["warehouse"]),
        ("ix_inventory_audit_events_inventory_location", ["inventory_location"]),
        ("ix_inventory_audit_events_reference_type", ["reference_type"]),
        ("ix_inventory_audit_events_reference_id", ["reference_id"]),
        ("ix_inventory_audit_events_reference_number", ["reference_number"]),
        ("ix_inventory_audit_events_created_by", ["created_by"]),
        ("ix_inventory_audit_events_created_at", ["created_at"]),
    ]:
        create_index_if_missing("inventory_audit_events", index_name, columns)


def downgrade() -> None:
    for table_name, index_names in [
        (
            "inventory_audit_events",
            [
                "ix_inventory_audit_events_created_at",
                "ix_inventory_audit_events_created_by",
                "ix_inventory_audit_events_reference_number",
                "ix_inventory_audit_events_reference_id",
                "ix_inventory_audit_events_reference_type",
                "ix_inventory_audit_events_inventory_location",
                "ix_inventory_audit_events_warehouse",
                "ix_inventory_audit_events_event_type",
                "ix_inventory_audit_events_barcode",
                "ix_inventory_audit_events_sku",
                "ix_inventory_audit_events_item_id",
            ],
        ),
        (
            "allocation_lines",
            [
                "ix_allocation_lines_status",
                "ix_allocation_lines_inventory_location",
                "ix_allocation_lines_warehouse",
                "ix_allocation_lines_barcode",
                "ix_allocation_lines_sku",
                "ix_allocation_lines_item_id",
                "ix_allocation_lines_order_line_id",
                "ix_allocation_lines_order_id",
                "ix_allocation_lines_allocation_id",
            ],
        ),
        (
            "allocations",
            [
                "ix_allocations_cancelled_at",
                "ix_allocations_posted_at",
                "ix_allocations_created_by",
                "ix_allocations_woo_order_number",
                "ix_allocations_woo_order_id",
                "ix_allocations_order_id",
                "ix_allocations_allocation_type",
                "ix_allocations_status",
                "ix_allocations_allocation_number",
            ],
        ),
    ]:
        for index_name in index_names:
            drop_index_if_present(table_name, index_name)
    for table_name in ["inventory_audit_events", "allocation_lines", "allocations"]:
        if table_exists(table_name):
            op.drop_table(table_name)
