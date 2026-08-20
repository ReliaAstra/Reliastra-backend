"""Add founding customer fields to organizations.

Revision ID: 0009_founding_customer
Revises: 0008_ai_providers
Create Date: 2026-08-13
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_founding_customer"
down_revision = "0008_ai_providers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("is_founding_customer", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "organizations",
        sa.Column("founding_discount_pct", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "founding_discount_pct")
    op.drop_column("organizations", "is_founding_customer")
