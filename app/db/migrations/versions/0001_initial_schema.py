"""initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-08-11 16:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid
from datetime import datetime, timezone

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, default="free"),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True)

    # 3. organization_members
    op.create_table(
        "organization_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_organization_members_org_id"), "organization_members", ["org_id"])
    op.create_index(op.f("ix_organization_members_user_id"), "organization_members", ["user_id"])

    # 4. dependencies
    op.create_table(
        "dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("method", sa.String(10), nullable=False, default="GET"),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("expected_status_codes", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, default=10),
        sa.Column("check_interval_seconds", sa.Integer(), nullable=False, default=300),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("alert_threshold_ms", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, default=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_dependencies_org_id"), "dependencies", ["org_id"])
    op.create_index(op.f("ix_dependencies_next_check_at"), "dependencies", ["next_check_at"])

    # 5. check_results (partitioned by RANGE on executed_at in Postgres)
    bind = op.get_bind()
    if bind.engine.name == "postgresql":
        op.execute(
            """
            CREATE TABLE check_results (
                id UUID NOT NULL,
                executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
                dependency_id UUID NOT NULL,
                org_id UUID NOT NULL,
                region VARCHAR(50) NOT NULL,
                latency_ms FLOAT NOT NULL,
                status_code INTEGER NULL,
                is_up BOOLEAN NOT NULL,
                error_message VARCHAR(500) NULL,
                quorum_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                CONSTRAINT pk_check_results PRIMARY KEY (id, executed_at),
                CONSTRAINT fk_check_results_dependency_id FOREIGN KEY (dependency_id) REFERENCES dependencies(id) ON DELETE CASCADE,
                CONSTRAINT fk_check_results_org_id FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
            ) PARTITION BY RANGE (executed_at);
            """
        )
        op.execute("CREATE TABLE IF NOT EXISTS check_results_default PARTITION OF check_results DEFAULT;")
    else:
        op.create_table(
            "check_results",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("executed_at", sa.DateTime(timezone=True), primary_key=True),
            sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("region", sa.String(50), nullable=False),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("is_up", sa.Boolean(), nullable=False),
            sa.Column("error_message", sa.String(500), nullable=True),
            sa.Column("quorum_confirmed", sa.Boolean(), nullable=False, default=False),
            sa.ForeignKeyConstraint(["dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        )
    op.create_index(op.f("ix_check_results_dependency_id"), "check_results", ["dependency_id"])
    op.create_index(op.f("ix_check_results_org_id"), "check_results", ["org_id"])
    op.create_index(op.f("ix_check_results_executed_at"), "check_results", ["executed_at"])

    # 6. incidents
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("severity", sa.String(30), nullable=False, default="major"),
        sa.Column("status", sa.String(30), nullable=False, default="open"),
        sa.Column("root_cause", sa.String(50), nullable=False, default="unknown"),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("evidence_report_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_incidents_org_id"), "incidents", ["org_id"])
    op.create_index(op.f("ix_incidents_dependency_id"), "incidents", ["dependency_id"])
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"])
    op.create_index(op.f("ix_incidents_started_at"), "incidents", ["started_at"])

    # 7. incident_correlations
    op.create_table(
        "incident_correlations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlated_dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_confidence", sa.Float(), nullable=False, default=0.85),
        sa.Column("time_window_seconds", sa.Integer(), nullable=False, default=300),
        sa.Column("correlation_method", sa.String(50), nullable=False, default="temporal"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["correlated_dependency_id"], ["dependencies.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_incident_correlations_incident_id"), "incident_correlations", ["incident_id"])
    op.create_index(op.f("ix_incident_correlations_correlated_dependency_id"), "incident_correlations", ["correlated_dependency_id"])

    # 8. evidence_reports
    op.create_table(
        "evidence_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(100), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_evidence_reports_org_id"), "evidence_reports", ["org_id"])
    op.create_index(op.f("ix_evidence_reports_incident_id"), "evidence_reports", ["incident_id"])
    op.create_index(op.f("ix_evidence_reports_checksum"), "evidence_reports", ["checksum"])

    # 9. vendor_trackings
    vendor_table = op.create_table(
        "vendor_trackings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, default=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_vendor_trackings_vendor_name"), "vendor_trackings", ["vendor_name"], unique=True)

    # Seed 5 public vendors
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        vendor_table,
        [
            {
                "id": uuid.uuid4(),
                "vendor_name": "stripe",
                "display_name": "Stripe",
                "endpoint_url": "https://status.stripe.com",
                "category": "payments",
                "is_public": True,
                "last_check_at": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.uuid4(),
                "vendor_name": "auth0",
                "display_name": "Auth0",
                "endpoint_url": "https://status.auth0.com",
                "category": "auth",
                "is_public": True,
                "last_check_at": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.uuid4(),
                "vendor_name": "cloudflare",
                "display_name": "Cloudflare",
                "endpoint_url": "https://www.cloudflarestatus.com",
                "category": "cdn",
                "is_public": True,
                "last_check_at": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.uuid4(),
                "vendor_name": "openai",
                "display_name": "OpenAI",
                "endpoint_url": "https://status.openai.com",
                "category": "ai",
                "is_public": True,
                "last_check_at": None,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": uuid.uuid4(),
                "vendor_name": "twilio",
                "display_name": "Twilio",
                "endpoint_url": "https://status.twilio.com",
                "category": "communications",
                "is_public": True,
                "last_check_at": None,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )

    # 10. alert_configs
    op.create_table(
        "alert_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel_type", sa.String(50), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_alert_configs_org_id"), "alert_configs", ["org_id"])

    # 11. api_keys
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("prefix", sa.String(20), nullable=False),
        sa.Column("hashed_key", sa.String(100), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_api_keys_org_id"), "api_keys", ["org_id"])
    op.create_index(op.f("ix_api_keys_hashed_key"), "api_keys", ["hashed_key"], unique=True)

    # 12. refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(100), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, default=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"])
    op.create_index(op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True)

    # 13. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_audit_logs_org_id"), "audit_logs", ["org_id"])
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"])
    op.create_index(op.f("ix_audit_logs_event_type"), "audit_logs", ["event_type"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("api_keys")
    op.drop_table("alert_configs")
    op.drop_table("vendor_trackings")
    op.drop_table("evidence_reports")
    op.drop_table("incident_correlations")
    op.drop_table("incidents")
    op.drop_table("check_results")
    op.drop_table("dependencies")
    op.drop_table("organization_members")
    op.drop_table("organizations")
    op.drop_table("users")
