"""Add immutable observations.

Revision ID: 0003_observations
Revises: 0002_subscriptions
Create Date: 2026-08-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_observations"
down_revision = "0002_subscriptions"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("region", sa.String(50), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Float(), nullable=True),
        sa.Column("tls_version", sa.String(20), nullable=True),
        sa.Column("tls_certificate_issuer", sa.String(200), nullable=True),
        sa.Column("tls_certificate_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(50), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_table(
            "observations", *_columns(), postgresql_partition_by="RANGE (timestamp)"
        )
        # The default partition guarantees uninterrupted writes. Retention can
        # later detach/drop bounded monthly partitions without changing callers.
        op.execute(
            "CREATE TABLE observations_default "
            "PARTITION OF observations DEFAULT"
        )
    else:
        op.create_table("observations", *_columns())

    for name, columns in (
        ("ix_observations_timestamp", ["timestamp"]),
        ("ix_observations_source_type", ["source_type"]),
        ("ix_observations_source_id", ["source_id"]),
        ("ix_observations_org_id", ["org_id"]),
        ("ix_observations_source_timestamp", ["source_id", "timestamp"]),
        ("ix_observations_org_timestamp", ["org_id", "timestamp"]),
    ):
        op.create_index(name, "observations", columns)


def downgrade() -> None:
    op.drop_table("observations")
