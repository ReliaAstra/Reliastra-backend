"""add ai_providers table

Revision ID: 0007_ai_providers
Revises: 0006_billing_subscriptions
Create Date: 2026-08-12 00:06:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_ai_providers"
down_revision: Union[str, None] = "0006_billing_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("encrypted_api_key", sa.String(500), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, default=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False, default=4096),
        sa.Column("temperature", sa.Float(), nullable=False, default=0.3),
        sa.Column("enabled", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_ai_providers_org_id"), "ai_providers", ["org_id"])


def downgrade() -> None:
    op.drop_table("ai_providers")
