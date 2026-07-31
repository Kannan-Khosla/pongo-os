"""Add stock mutation idempotency and database invariants.

Revision ID: 20260726_0021
Revises: 20260715_0020
"""

from alembic import op
import sqlalchemy as sa

revision = "20260726_0021"
down_revision = "20260715_0020"
branch_labels = None
depends_on = None


ITEM_CHECKS = (
    ("ck_inventory_items_in_stock_nonnegative", "in_stock >= 0"),
    ("ck_inventory_items_allocated_nonnegative", "allocated >= 0"),
    ("ck_inventory_items_allocated_lte_stock", "allocated <= in_stock"),
    ("ck_inventory_items_sellable_nonnegative", "sellable >= 0"),
)

LOCATION_CHECKS = (
    ("ck_inventory_item_locations_in_stock_nonnegative", "in_stock >= 0"),
    ("ck_inventory_item_locations_allocated_nonnegative", "allocated >= 0"),
    ("ck_inventory_item_locations_allocated_lte_stock", "allocated <= in_stock"),
    ("ck_inventory_item_locations_sellable_nonnegative", "sellable >= 0"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("stock_mutation_requests"):
        op.create_table(
            "stock_mutation_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("operation", sa.String(length=40), nullable=False),
            sa.Column("idempotency_key", sa.String(length=120), nullable=False),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("operation", "idempotency_key", name="uq_stock_mutation_request_operation_key"),
        )
        op.create_index("ix_stock_mutation_requests_operation", "stock_mutation_requests", ["operation"])
        op.create_index("ix_stock_mutation_requests_status", "stock_mutation_requests", ["status"])

    for table_name, checks in (
        ("inventory_items", ITEM_CHECKS),
        ("inventory_item_locations", LOCATION_CHECKS),
    ):
        existing = {constraint["name"] for constraint in sa.inspect(bind).get_check_constraints(table_name)}
        missing = [(name, condition) for name, condition in checks if name not in existing]
        if missing:
            with op.batch_alter_table(table_name) as batch:
                for name, condition in missing:
                    batch.create_check_constraint(name, condition)


def downgrade() -> None:
    with op.batch_alter_table("inventory_item_locations") as batch:
        for name, _ in reversed(LOCATION_CHECKS):
            batch.drop_constraint(name, type_="check")
    with op.batch_alter_table("inventory_items") as batch:
        for name, _ in reversed(ITEM_CHECKS):
            batch.drop_constraint(name, type_="check")
    op.drop_index("ix_stock_mutation_requests_status", table_name="stock_mutation_requests")
    op.drop_index("ix_stock_mutation_requests_operation", table_name="stock_mutation_requests")
    op.drop_table("stock_mutation_requests")
