"""stock by location v2 transfers

Revision ID: 20260707_0013
Revises: 20260707_0012
Create Date: 2026-07-07
"""

from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0013"
down_revision: str | None = "20260707_0012"
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


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def create_index_if_missing(table_name: str, index_name: str, columns: list[str], unique: bool = False) -> None:
    if table_exists(table_name) and not index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    extend_inventory_item_locations()
    extend_stock_movements()
    extend_workflow_lines()
    create_transfer_tables()
    create_adjustment_tables()
    backfill_item_locations()


def extend_inventory_item_locations() -> None:
    if not table_exists("inventory_item_locations"):
        op.create_table(
            "inventory_item_locations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("location_id", sa.Integer(), nullable=True),
            sa.Column("client", sa.String(length=120), nullable=True),
            sa.Column("warehouse", sa.String(length=120), nullable=True),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("location_code", sa.String(length=120), nullable=True),
            sa.Column("location_name", sa.String(length=200), nullable=True),
            sa.Column("is_default_location", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("in_stock", sa.Numeric(14, 3), server_default="0", nullable=False),
            sa.Column("allocated", sa.Numeric(14, 3), server_default="0", nullable=False),
            sa.Column("sellable", sa.Numeric(14, 3), server_default="0", nullable=False),
            sa.Column("on_order", sa.Numeric(14, 3), server_default="0", nullable=False),
            sa.Column("par_level", sa.Numeric(14, 3), nullable=True),
            sa.Column("under_par", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
            sa.ForeignKeyConstraint(["location_id"], ["inventory_locations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        add_column_if_missing("inventory_item_locations", sa.Column("client", sa.String(length=120), nullable=True))
        add_column_if_missing("inventory_item_locations", sa.Column("location_code", sa.String(length=120), nullable=True))
        add_column_if_missing("inventory_item_locations", sa.Column("location_name", sa.String(length=200), nullable=True))
        add_column_if_missing("inventory_item_locations", sa.Column("par_level", sa.Numeric(14, 3), nullable=True))
        add_column_if_missing("inventory_item_locations", sa.Column("under_par", sa.Boolean(), server_default=sa.text("0"), nullable=False))
        add_column_if_missing("inventory_item_locations", sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False))
    for index_name, columns in [
        ("ix_inventory_item_locations_inventory_item_id", ["inventory_item_id"]),
        ("ix_inventory_item_locations_location_id", ["location_id"]),
        ("ix_inventory_item_locations_client", ["client"]),
        ("ix_inventory_item_locations_warehouse", ["warehouse"]),
        ("ix_inventory_item_locations_inventory_location", ["inventory_location"]),
        ("ix_inventory_item_locations_location_code", ["location_code"]),
        ("ix_inventory_item_locations_is_default_location", ["is_default_location"]),
        ("ix_inventory_item_locations_under_par", ["under_par"]),
        ("ix_inventory_item_locations_active", ["active"]),
        ("ix_inventory_item_locations_item_warehouse_location", ["inventory_item_id", "warehouse", "inventory_location"]),
    ]:
        create_index_if_missing("inventory_item_locations", index_name, columns)


def extend_stock_movements() -> None:
    for column in [
        sa.Column("inventory_item_location_id", sa.Integer(), nullable=True),
        sa.Column("from_inventory_location_id", sa.Integer(), nullable=True),
        sa.Column("to_inventory_location_id", sa.Integer(), nullable=True),
        sa.Column("from_warehouse", sa.String(length=120), nullable=True),
        sa.Column("from_inventory_location", sa.String(length=200), nullable=True),
        sa.Column("to_warehouse", sa.String(length=120), nullable=True),
        sa.Column("to_inventory_location", sa.String(length=200), nullable=True),
        sa.Column("old_location_stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("new_location_stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("old_item_stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("new_item_stock", sa.Numeric(14, 3), nullable=True),
        sa.Column("movement_group_id", sa.String(length=80), nullable=True),
        sa.Column("movement_source", sa.String(length=80), nullable=True),
    ]:
        add_column_if_missing("stock_movements", column)
    for index_name, columns in [
        ("ix_stock_movements_inventory_item_location_id", ["inventory_item_location_id"]),
        ("ix_stock_movements_from_inventory_location_id", ["from_inventory_location_id"]),
        ("ix_stock_movements_to_inventory_location_id", ["to_inventory_location_id"]),
        ("ix_stock_movements_from_warehouse", ["from_warehouse"]),
        ("ix_stock_movements_from_inventory_location", ["from_inventory_location"]),
        ("ix_stock_movements_to_warehouse", ["to_warehouse"]),
        ("ix_stock_movements_to_inventory_location", ["to_inventory_location"]),
        ("ix_stock_movements_movement_group_id", ["movement_group_id"]),
        ("ix_stock_movements_movement_source", ["movement_source"]),
    ]:
        create_index_if_missing("stock_movements", index_name, columns)


def extend_workflow_lines() -> None:
    workflow_columns = [
        ("receipt_items", "inventory_item_location_id"),
        ("cycle_count_lines", "inventory_item_location_id"),
        ("allocation_lines", "inventory_item_location_id"),
        ("pick_lines", "inventory_item_location_id"),
        ("fulfillment_lines", "inventory_item_location_id"),
    ]
    for table_name, column_name in workflow_columns:
        if table_exists(table_name):
            add_column_if_missing(table_name, sa.Column(column_name, sa.Integer(), nullable=True))
            create_index_if_missing(table_name, f"ix_{table_name}_{column_name}", [column_name])
    if table_exists("receipt_items"):
        add_column_if_missing("receipt_items", sa.Column("inventory_location", sa.String(length=200), nullable=True))
        create_index_if_missing("receipt_items", "ix_receipt_items_inventory_location", ["inventory_location"])


def create_transfer_tables() -> None:
    if not table_exists("inventory_transfers"):
        op.create_table(
            "inventory_transfers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("transfer_number", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("from_warehouse", sa.String(length=120), nullable=True),
            sa.Column("from_inventory_location", sa.String(length=200), nullable=True),
            sa.Column("to_warehouse", sa.String(length=120), nullable=True),
            sa.Column("to_inventory_location", sa.String(length=200), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("transfer_number"),
        )
    if not table_exists("inventory_transfer_lines"):
        op.create_table(
            "inventory_transfer_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("transfer_id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("from_inventory_item_location_id", sa.Integer(), nullable=False),
            sa.Column("to_inventory_item_location_id", sa.Integer(), nullable=True),
            sa.Column("from_warehouse", sa.String(length=120), nullable=True),
            sa.Column("from_inventory_location", sa.String(length=200), nullable=True),
            sa.Column("to_warehouse", sa.String(length=120), nullable=True),
            sa.Column("to_inventory_location", sa.String(length=200), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["transfer_id"], ["inventory_transfers.id"]),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
            sa.ForeignKeyConstraint(["from_inventory_item_location_id"], ["inventory_item_locations.id"]),
            sa.ForeignKeyConstraint(["to_inventory_item_location_id"], ["inventory_item_locations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for table_name in ["inventory_transfers", "inventory_transfer_lines"]:
        for column in ["status", "from_warehouse", "from_inventory_location", "to_warehouse", "to_inventory_location", "created_by"]:
            if column_exists(table_name, column):
                create_index_if_missing(table_name, f"ix_{table_name}_{column}", [column])


def create_adjustment_tables() -> None:
    if not table_exists("stock_adjustments"):
        op.create_table(
            "stock_adjustments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("adjustment_number", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("adjustment_type", sa.String(length=40), nullable=False),
            sa.Column("reason", sa.String(length=500), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=120), nullable=True),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("adjustment_number"),
        )
    if not table_exists("stock_adjustment_lines"):
        op.create_table(
            "stock_adjustment_lines",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("adjustment_id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_id", sa.Integer(), nullable=False),
            sa.Column("inventory_item_location_id", sa.Integer(), nullable=False),
            sa.Column("sku", sa.String(length=120), nullable=True),
            sa.Column("barcode", sa.String(length=120), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("warehouse", sa.String(length=120), nullable=True),
            sa.Column("inventory_location", sa.String(length=200), nullable=True),
            sa.Column("old_quantity", sa.Numeric(14, 3), nullable=False),
            sa.Column("new_quantity", sa.Numeric(14, 3), nullable=True),
            sa.Column("quantity_change", sa.Numeric(14, 3), nullable=False),
            sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
            sa.ForeignKeyConstraint(["adjustment_id"], ["stock_adjustments.id"]),
            sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"]),
            sa.ForeignKeyConstraint(["inventory_item_location_id"], ["inventory_item_locations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for table_name in ["stock_adjustments", "stock_adjustment_lines"]:
        for column in ["status", "adjustment_type", "created_by", "warehouse", "inventory_location"]:
            if column_exists(table_name, column):
                create_index_if_missing(table_name, f"ix_{table_name}_{column}", [column])


def backfill_item_locations() -> None:
    bind = op.get_bind()
    meta = sa.MetaData()
    items = sa.Table("inventory_items", meta, autoload_with=bind)
    locations = sa.Table("inventory_locations", meta, autoload_with=bind)
    item_locations = sa.Table("inventory_item_locations", meta, autoload_with=bind)

    item_rows = bind.execute(sa.select(items)).mappings().all()
    for item in item_rows:
        existing_count = bind.execute(
            sa.select(sa.func.count()).select_from(item_locations).where(item_locations.c.inventory_item_id == item["id"])
        ).scalar() or 0
        if existing_count:
            continue
        warehouse = item.get("warehouse") or "UNASSIGNED"
        location_code = item.get("inventory_location") or item.get("default_location") or "UNASSIGNED"
        location_id = find_or_create_location(bind, locations, item.get("client"), warehouse, location_code)
        in_stock = item.get("in_stock") or Decimal("0")
        allocated = item.get("allocated") or Decimal("0")
        sellable = in_stock - allocated
        par_level = item.get("par_level")
        bind.execute(
            item_locations.insert().values(
                inventory_item_id=item["id"],
                location_id=location_id,
                client=item.get("client"),
                warehouse=warehouse,
                inventory_location=location_code,
                location_code=location_code,
                location_name=location_code,
                is_default_location=True,
                in_stock=in_stock,
                allocated=allocated,
                sellable=sellable,
                on_order=item.get("on_order") or Decimal("0"),
                par_level=par_level,
                under_par=bool(par_level is not None and in_stock <= par_level),
                active=True,
            )
        )

    for item in item_rows:
        rows = bind.execute(sa.select(item_locations).where(item_locations.c.inventory_item_id == item["id"], item_locations.c.active == sa.true())).mappings().all()
        if not rows:
            continue
        in_stock = sum((row["in_stock"] or Decimal("0")) for row in rows)
        allocated = sum((row["allocated"] or Decimal("0")) for row in rows)
        sellable = in_stock - allocated
        par_level = item.get("par_level")
        bind.execute(
            items.update()
            .where(items.c.id == item["id"])
            .values(
                in_stock=in_stock,
                allocated=allocated,
                sellable=sellable,
                under_par=bool(par_level is not None and in_stock <= par_level),
            )
        )


def find_or_create_location(bind, locations: sa.Table, client: str | None, warehouse: str, location_code: str) -> int:
    existing = bind.execute(
        sa.select(locations.c.id).where(
            locations.c.warehouse == warehouse,
            locations.c.location_code == location_code,
        )
    ).scalar()
    if existing:
        return existing
    result = bind.execute(
        locations.insert().values(
            client=client,
            warehouse=warehouse,
            location_code=location_code,
            location_name=location_code,
            is_default=False,
            active=True,
        )
    )
    return int(result.inserted_primary_key[0])


def downgrade() -> None:
    pass
