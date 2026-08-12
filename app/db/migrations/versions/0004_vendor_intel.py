"""add vendor intelligence tables

Revision ID: 0004_vendor_intel
Revises: 0003_observations
Create Date: 2026-08-12 00:03:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_vendor_intel"
down_revision: Union[str, None] = "0003_observations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. vendors (canonical, renamed from vendor_trackings with slug + icon_url)
    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, default=True),
        sa.Column("icon_url", sa.String(500), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_vendors_vendor_name"), "vendors", ["vendor_name"], unique=True)
    op.create_index(op.f("ix_vendors_slug"), "vendors", ["slug"], unique=True)

    # 2. vendor_endpoints
    op.create_table(
        "vendor_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("region", sa.String(50), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_probed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_vendor_endpoints_vendor_id"), "vendor_endpoints", ["vendor_id"])

    # 3. probe_configs
    op.create_table(
        "probe_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_endpoint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(10), nullable=False, default="GET"),
        sa.Column("expected_status_codes", sa.JSON(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, default=300),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, default=10),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["vendor_endpoint_id"], ["vendor_endpoints.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        op.f("ix_probe_configs_vendor_endpoint_id"),
        "probe_configs",
        ["vendor_endpoint_id"],
    )

    # 4. vendor_incidents
    op.create_table(
        "vendor_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, default="open"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_vendor_incidents_vendor_id"), "vendor_incidents", ["vendor_id"])
    op.create_index(op.f("ix_vendor_incidents_status"), "vendor_incidents", ["status"])

    # 5. vendor_metrics_daily
    op.create_table(
        "vendor_metrics_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uptime_percentage", sa.Float(), nullable=False, default=100.0),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, default=0.0),
        sa.Column("total_checks", sa.Integer(), nullable=False, default=0),
        sa.Column("total_up", sa.Integer(), nullable=False, default=0),
        sa.Column("total_down", sa.Integer(), nullable=False, default=0),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="CASCADE"),
    )
    op.create_index(
        op.f("ix_vendor_metrics_daily_vendor_id"), "vendor_metrics_daily", ["vendor_id"]
    )
    op.create_index(
        op.f("ix_vendor_metrics_daily_date"), "vendor_metrics_daily", ["date"]
    )


def downgrade() -> None:
    op.drop_table("vendor_metrics_daily")
    op.drop_table("vendor_incidents")
    op.drop_table("probe_configs")
    op.drop_table("vendor_endpoints")
    op.drop_table("vendors")
