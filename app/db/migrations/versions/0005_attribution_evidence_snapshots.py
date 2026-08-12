"""add attribution_results and immutable evidence_snapshots

Revision ID: 0005_attribution_evidence
Revises: 0004_vendor_intel
Create Date: 2026-08-12 00:04:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_attribution_evidence"
down_revision: Union[str, None] = "0004_vendor_intel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. attribution_results
    op.create_table(
        "attribution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("methodology_version", sa.String(50), nullable=False, default="v1.0"),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("evidence_chain", sa.JSON(), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_attribution_results_incident_id"), "attribution_results", ["incident_id"])
    op.create_index(op.f("ix_attribution_results_org_id"), "attribution_results", ["org_id"])

    # 2. evidence_snapshots (immutable)
    op.create_table(
        "evidence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("time_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_ids", sa.JSON(), nullable=False),
        sa.Column("attribution_result", sa.JSON(), nullable=False),
        sa.Column("methodology_version", sa.String(50), nullable=False, default="v1.0"),
        sa.Column("data_hash", sa.String(64), nullable=False),
        sa.Column("verification_id", sa.String(32), nullable=False),
        sa.Column("report_file_path", sa.String(500), nullable=False),
        sa.Column("report_checksum", sa.String(64), nullable=False),
        sa.Column("json_evidence_path", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_evidence_snapshots_incident_id"), "evidence_snapshots", ["incident_id"])
    op.create_index(op.f("ix_evidence_snapshots_org_id"), "evidence_snapshots", ["org_id"])
    op.create_index(op.f("ix_evidence_snapshots_verification_id"), "evidence_snapshots", ["verification_id"], unique=True)


def downgrade() -> None:
    op.drop_table("evidence_snapshots")
    op.drop_table("attribution_results")
