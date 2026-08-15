"""Add immutable evidence snapshots.

Revision ID: 0006_evidence_snapshots
Revises: 0005_attribution
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_evidence_snapshots"
down_revision = "0005_attribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("time_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_ids", sa.JSON(), nullable=False),
        sa.Column("attribution_result", sa.JSON(), nullable=True),
        sa.Column("methodology_version", sa.String(20), nullable=False, server_default="v1.0"),
        sa.Column("data_hash", sa.String(64), nullable=False),
        sa.Column("verification_id", sa.String(32), nullable=False),
        sa.Column("report_file_path", sa.String(500), nullable=True),
        sa.Column("report_checksum", sa.String(64), nullable=True),
        sa.Column("json_evidence_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("verification_id", name="uq_evidence_snapshots_verification_id"),
    )
    for name, columns in (
        ("ix_evidence_snapshots_incident_id", ["incident_id"]),
        ("ix_evidence_snapshots_org_id", ["org_id"]),
        ("ix_evidence_snapshots_dependency_id", ["dependency_id"]),
        ("ix_evidence_snapshots_data_hash", ["data_hash"]),
        ("ix_evidence_snapshots_verification_id", ["verification_id"]),
    ):
        op.create_index(name, "evidence_snapshots", columns)


def downgrade() -> None:
    op.drop_table("evidence_snapshots")
