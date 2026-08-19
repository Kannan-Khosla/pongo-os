"""Add safe order substitution and writeback idempotency fields.

Revision ID: 20260819_0040
Revises: 20260818_0039
"""

from alembic import op
import sqlalchemy as sa


revision = "20260819_0040"
down_revision = "20260818_0039"
branch_labels = None
depends_on = None

ORDER_ITEM_COLUMNS_BEFORE = (
    "id", "order_id", "woo_order_item_id", "woo_product_id", "woo_variation_id", "inventory_item_id",
    "line_number", "sku", "barcode", "description", "name", "quantity_ordered", "quantity_allocated",
    "quantity_picked", "quantity_fulfilled", "quantity_stock_reduced", "stock_reduced_at", "ordered_qty",
    "ordered_uom", "allocated_qty", "picked_qty", "fulfilled_qty", "unit_cost", "unit_price", "line_subtotal",
    "line_total", "line_tax", "matched_status", "availability_status", "allocation_status", "pick_status",
    "allocation_exception_reason", "sellable_snapshot", "shortage_quantity", "sync_status", "sync_error",
    "unit_cost_total", "total_price", "brand", "status", "created_at", "updated_at",
)
ORDER_ITEM_COLUMNS_AFTER = (
    *ORDER_ITEM_COLUMNS_BEFORE[:6],
    "substituted_from_inventory_item_id", "substitution_reason", "substituted_by", "substituted_at",
    *ORDER_ITEM_COLUMNS_BEFORE[6:],
)
WRITEBACK_COLUMNS_BEFORE = (
    "id", "operation_type", "entity_type", "entity_id", "woo_entity_id", "woo_product_id", "woo_variation_id",
    "woo_order_id", "payload_json", "status", "environment", "dry_run", "allowed_host", "preview_json",
    "response_json", "error_message", "requested_by", "approved_by", "created_at", "approved_at", "sent_at",
    "updated_at",
)
WRITEBACK_COLUMNS_AFTER = (*WRITEBACK_COLUMNS_BEFORE[:8], "idempotency_key", *WRITEBACK_COLUMNS_BEFORE[8:])


def upgrade() -> None:
    with op.batch_alter_table("order_items", partial_reordering=[ORDER_ITEM_COLUMNS_AFTER]) as batch:
        batch.add_column(sa.Column("substituted_from_inventory_item_id", sa.Integer()))
        batch.add_column(sa.Column("substitution_reason", sa.Text()))
        batch.add_column(sa.Column("substituted_by", sa.String(120)))
        batch.add_column(sa.Column("substituted_at", sa.DateTime(timezone=True)))
        batch.create_foreign_key(
            "fk_order_items_substituted_from_inventory_item",
            "inventory_items",
            ["substituted_from_inventory_item_id"],
            ["id"],
        )
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("order_items")}
    if "ix_order_items_substituted_from_inventory_item_id" not in indexes:
        op.create_index(
            "ix_order_items_substituted_from_inventory_item_id",
            "order_items",
            ["substituted_from_inventory_item_id"],
        )

    with op.batch_alter_table("woo_writeback_queue", partial_reordering=[WRITEBACK_COLUMNS_AFTER]) as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(120)))
        batch.create_unique_constraint(
            "uq_woo_writeback_operation_idempotency",
            ["operation_type", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("woo_writeback_queue", partial_reordering=[WRITEBACK_COLUMNS_BEFORE]) as batch:
        batch.drop_constraint("uq_woo_writeback_operation_idempotency", type_="unique")
        batch.drop_column("idempotency_key")

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("order_items")}
    if "ix_order_items_substituted_from_inventory_item_id" in indexes:
        op.drop_index("ix_order_items_substituted_from_inventory_item_id", table_name="order_items")
    with op.batch_alter_table("order_items", partial_reordering=[ORDER_ITEM_COLUMNS_BEFORE]) as batch:
        batch.drop_constraint(
            "fk_order_items_substituted_from_inventory_item",
            type_="foreignkey",
        )
        batch.drop_column("substituted_at")
        batch.drop_column("substituted_by")
        batch.drop_column("substitution_reason")
        batch.drop_column("substituted_from_inventory_item_id")
