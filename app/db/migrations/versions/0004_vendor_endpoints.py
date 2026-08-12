"""Expand vendor intelligence with endpoints.

Revision ID: 0004_vendor_endpoints
Revises: 0003_observations
Create Date: 2026-08-12
"""

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_vendor_endpoints"
down_revision = "0003_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendor_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("check_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("regions", sa.JSON(), nullable=False, server_default='["us-east", "eu-west"]'),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor_trackings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("vendor_id", "endpoint_url", name="uq_vendor_endpoints_vendor_url"),
    )
    op.create_index("ix_vendor_endpoints_vendor_id", "vendor_endpoints", ["vendor_id"])

    vendor_table = sa.table(
        "vendor_trackings",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("endpoint_url", sa.String()),
    )
    endpoint_table = sa.table(
        "vendor_endpoints",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("vendor_id", postgresql.UUID(as_uuid=True)),
        sa.column("endpoint_url", sa.String()),
        sa.column("check_interval_seconds", sa.Integer()),
        sa.column("regions", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("health_status", sa.String()),
        sa.column("last_check_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = op.get_bind().execute(sa.select(vendor_table.c.id, vendor_table.c.endpoint_url))
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        endpoint_table,
        [
            {
                "id": uuid.uuid4(),
                "vendor_id": row.id,
                "endpoint_url": row.endpoint_url,
                "check_interval_seconds": 300,
                "regions": ["us-east", "eu-west"],
                "is_active": True,
                "health_status": "unknown",
                "last_check_at": None,
                "created_at": now,
                "updated_at": now,
            }
            for row in rows
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_vendor_endpoints_vendor_id", table_name="vendor_endpoints")
    op.drop_table("vendor_endpoints")
