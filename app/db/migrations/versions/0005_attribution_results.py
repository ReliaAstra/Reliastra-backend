"""Add deterministic attribution results.

Revision ID: 0005_attribution
Revises: 0004_vendor_endpoints
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_attribution"
down_revision = "0004_vendor_endpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attribution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suspected_dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("signal_breakdown", sa.JSON(), nullable=False),
        sa.Column("supporting_evidence", sa.JSON(), nullable=False),
        sa.Column("contradicting_evidence", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(20), nullable=False, server_default="v1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["suspected_dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("incident_id", name="uq_attribution_results_incident_id"),
    )
    op.create_index("ix_attribution_results_incident_id", "attribution_results", ["incident_id"])
    op.create_index("ix_attribution_results_org_id", "attribution_results", ["org_id"])
    op.create_index(
        "ix_attribution_results_suspected_dependency_id",
        "attribution_results",
        ["suspected_dependency_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attribution_results_suspected_dependency_id",
        table_name="attribution_results",
    )
    op.drop_index("ix_attribution_results_org_id", table_name="attribution_results")
    op.drop_index("ix_attribution_results_incident_id", table_name="attribution_results")
    op.drop_table("attribution_results")
