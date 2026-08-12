"""add subscriptions table for decoupled billing (Paystack)

Revision ID: 0006_billing_subscriptions
Revises: 0005_attribution_evidence
Create Date: 2026-08-12 00:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_billing_subscriptions"
down_revision: Union[str, None] = "0005_attribution_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, default="paystack"),
        sa.Column("provider_customer_id", sa.String(200), nullable=True),
        sa.Column("provider_subscription_id", sa.String(200), nullable=True),
        sa.Column("provider_reference", sa.String(200), nullable=True),
        sa.Column("plan", sa.String(50), nullable=False, default="free"),
        sa.Column("status", sa.String(30), nullable=False, default="initiated"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        op.f("ix_subscriptions_organization_id"), "subscriptions", ["organization_id"]
    )
    op.create_index(
        op.f("ix_subscriptions_provider_reference"), "subscriptions", ["provider_reference"]
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
