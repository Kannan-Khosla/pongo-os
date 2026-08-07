"""Persist encrypted Google Sheets report configuration.

Revision ID: 20260807_0036
Revises: 20260806_0035
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_0036"
down_revision = "20260806_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("google_reports_configuration"):
        op.create_table(
            "google_reports_configuration",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("client_id_ciphertext", sa.Text(), nullable=False),
            sa.Column("client_secret_ciphertext", sa.Text(), nullable=False),
            sa.Column("refresh_token_ciphertext", sa.Text(), nullable=False),
            sa.Column("folder_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("updated_by", sa.String(length=120), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.CheckConstraint("id = 1", name="ck_google_reports_configuration_singleton"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_google_reports_configuration_updated_by", "google_reports_configuration", ["updated_by"])
        op.create_index("ix_google_reports_configuration_updated_at", "google_reports_configuration", ["updated_at"])


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("google_reports_configuration"):
        op.drop_table("google_reports_configuration")
