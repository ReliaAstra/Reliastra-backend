"""Add Paystack subscriptions.

Revision ID: 0002_subscriptions
Revises: 0001_initial
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_subscriptions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="paystack"),
        sa.Column("provider_customer_id", sa.String(200), nullable=True),
        sa.Column("provider_subscription_id", sa.String(200), nullable=True),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("status", sa.String(30), nullable=False, server_default="inactive"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "organization_id", name="uq_subscriptions_organization_id"
        ),
    )
    op.create_index(
        "ix_subscriptions_organization_id",
        "subscriptions",
        ["organization_id"],
    )
    op.create_index(
        "ix_subscriptions_provider_customer_id",
        "subscriptions",
        ["provider_customer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscriptions_provider_customer_id", table_name="subscriptions"
    )
    op.drop_index(
        "ix_subscriptions_organization_id", table_name="subscriptions"
    )
    op.drop_table("subscriptions")
