"""add unified observations table (range-partitioned)

Revision ID: 0003_observations
Revises: 0002_agency_hierarchy
Create Date: 2026-08-12 00:02:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_observations"
down_revision: Union[str, None] = "0002_agency_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.engine.name == "postgresql":
        op.execute(
            """
            CREATE TABLE observations (
                id UUID NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                source_type VARCHAR(30) NOT NULL,
                source_id UUID NULL,
                org_id UUID NULL,
                region VARCHAR(50) NOT NULL,
                endpoint_url VARCHAR(500) NOT NULL,
                latency_ms FLOAT NOT NULL,
                status_code INTEGER NULL,
                response_time_ms FLOAT NULL,
                tls_version VARCHAR(20) NULL,
                tls_certificate_issuer VARCHAR(200) NULL,
                tls_certificate_expiry TIMESTAMP WITH TIME ZONE NULL,
                error_type VARCHAR(50) NULL,
                error_message VARCHAR(500) NULL,
                extra_data JSON NULL,
                CONSTRAINT pk_observations PRIMARY KEY (id, timestamp),
                CONSTRAINT fk_observations_source_id FOREIGN KEY (source_id) REFERENCES dependencies(id) ON DELETE CASCADE,
                CONSTRAINT fk_observations_org_id FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
            ) PARTITION BY RANGE (timestamp);
            """
        )
        op.execute(
            "CREATE TABLE IF NOT EXISTS observations_default PARTITION OF observations DEFAULT;"
        )
        op.create_index(
            "ix_observations_source_id", "observations", ["source_id"]
        )
        op.create_index("ix_observations_org_id", "observations", ["org_id"])
        op.create_index("ix_observations_timestamp", "observations", ["timestamp"])
    else:
        op.create_table(
            "observations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True),
            sa.Column("source_type", sa.String(30), nullable=False),
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
            sa.Column("extra_data", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["source_id"], ["dependencies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        )
        op.create_index(op.f("ix_observations_source_id"), "observations", ["source_id"])
        op.create_index(op.f("ix_observations_org_id"), "observations", ["org_id"])
        op.create_index(op.f("ix_observations_timestamp"), "observations", ["timestamp"])


def downgrade() -> None:
    op.drop_table("observations")
