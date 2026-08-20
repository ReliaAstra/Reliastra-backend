"""Add organization-scoped AI providers.

Revision ID: 0008_ai_providers
Revises: 0007_agency_hierarchy
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_ai_providers"
down_revision = "0007_agency_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider_type", sa.String(50), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="4096"),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.3"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_ai_providers_organization_id", "ai_providers", ["organization_id"]
    )
    # PostgreSQL enforces at most one default provider per organization.
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "uq_ai_providers_default_per_org",
            "ai_providers",
            ["organization_id"],
            unique=True,
            postgresql_where=sa.text("is_default = true"),
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index(
            "uq_ai_providers_default_per_org", table_name="ai_providers"
        )
    op.drop_index("ix_ai_providers_organization_id", table_name="ai_providers")
    op.drop_table("ai_providers")
