"""Bound and safely deduplicate WooCommerce sync errors.

Revision ID: 20260807_0037
Revises: 20260807_0036
"""

import hashlib
import json

from alembic import op
import sqlalchemy as sa


revision = "20260807_0037"
down_revision = "20260807_0036"
branch_labels = None
depends_on = None


SIGNATURE_FIELDS = (
    "remote_order_id",
    "remote_line_item_id",
    "remote_product_id",
    "remote_variation_id",
    "sku",
    "barcode",
    "error_message",
)


def _fingerprint(row) -> str:
    normalized = json.dumps(
        [row[field] for field in SIGNATURE_FIELDS],
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("woocommerce_sync_errors")}
    if "fingerprint" not in columns:
        op.add_column("woocommerce_sync_errors", sa.Column("fingerprint", sa.String(64), nullable=True))

    errors = sa.table(
        "woocommerce_sync_errors",
        sa.column("id", sa.Integer),
        sa.column("sync_run_id", sa.Integer),
        *(sa.column(field) for field in SIGNATURE_FIELDS),
        sa.column("fingerprint", sa.String(64)),
    )
    seen: set[tuple[int, str]] = set()
    rows = bind.execute(sa.select(errors).order_by(errors.c.id)).mappings().all()
    for row in rows:
        fingerprint = _fingerprint(row)
        key = (row["sync_run_id"], fingerprint)
        if key in seen:
            bind.execute(sa.delete(errors).where(errors.c.id == row["id"]))
            continue
        seen.add(key)
        bind.execute(sa.update(errors).where(errors.c.id == row["id"]).values(fingerprint=fingerprint))

    inspector = sa.inspect(bind)
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("woocommerce_sync_errors")}
    with op.batch_alter_table("woocommerce_sync_errors") as batch:
        batch.alter_column("fingerprint", existing_type=sa.String(64), nullable=False)
        if "uq_woocommerce_sync_errors_run_fingerprint" not in unique_constraints:
            batch.create_unique_constraint(
                "uq_woocommerce_sync_errors_run_fingerprint",
                ["sync_run_id", "fingerprint"],
            )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("woocommerce_sync_errors")}
    if "ix_woocommerce_sync_errors_created_at" not in indexes:
        op.create_index("ix_woocommerce_sync_errors_created_at", "woocommerce_sync_errors", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("woocommerce_sync_errors")}
    if "ix_woocommerce_sync_errors_created_at" in indexes:
        op.drop_index("ix_woocommerce_sync_errors_created_at", table_name="woocommerce_sync_errors")

    columns = {column["name"] for column in inspector.get_columns("woocommerce_sync_errors")}
    unique_constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("woocommerce_sync_errors")}
    if "fingerprint" in columns:
        with op.batch_alter_table("woocommerce_sync_errors") as batch:
            if "uq_woocommerce_sync_errors_run_fingerprint" in unique_constraints:
                batch.drop_constraint("uq_woocommerce_sync_errors_run_fingerprint", type_="unique")
            batch.drop_column("fingerprint")
