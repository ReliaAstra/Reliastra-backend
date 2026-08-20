"""plg_growth_features

Add all tables for the PLG & Growth features:
  - badge_impressions (Module 1: Badges)
  - timeline_shares (Module 2: Timeline Share PNG)
  - vendor_submissions + vendor_submission_endpoints (Module 3: Vendor Submission)
  - public_evidence_reports + evidence_gate_tokens + lead_capture_events (Module 4: Evidence Gate)
  - referral_codes + referrals + referral_rewards + org_plan_overrides (Module 5: Referrals)
  - webhooks + webhook_deliveries (Module 7: Webhooks)
  - status_pages + status_components (Module 9: Status Pages)

Revision ID: 0011_plg_growth_features
Revises: 0010_timeline_indexes

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0011_plg_growth_features"
down_revision: Union[str, None] = "0010_timeline_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # MODULE 1: Badge Impressions
    # =========================================================================
    op.create_table(
        "badge_impressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("vendor_name", sa.String(255), nullable=False, index=True),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("utm_source", sa.String(255), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("referer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_badge_impressions_vendor", "badge_impressions", ["vendor_name", "created_at"])
    op.create_index("idx_badge_impressions_date", "badge_impressions", ["created_at"])

    # =========================================================================
    # MODULE 2: Timeline Shares
    # =========================================================================
    op.create_table(
        "timeline_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("vendor_name", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("share_token", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("window", sa.String(50), nullable=False, server_default="24h"),
        sa.Column("region", sa.String(50), nullable=False, server_default="us-east"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.String(255), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # =========================================================================
    # MODULE 3: Vendor Submissions
    # =========================================================================
    op.create_table(
        "vendor_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("vendor_name", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("website_url", sa.Text(), nullable=True),
        sa.Column("submitter_email", sa.String(255), nullable=False, index=True),
        sa.Column("submitter_name", sa.String(255), nullable=True),
        sa.Column("submitter_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("endpoints_data", postgresql.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_review"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "vendor_submission_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor_submissions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("method", sa.String(10), nullable=False, server_default="GET"),
        sa.Column("expected_status", sa.Integer(), nullable=False, server_default="200"),
    )

    # =========================================================================
    # MODULE 4: Evidence Gate
    # =========================================================================
    op.create_table(
        "public_evidence_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("vendor_name", sa.String(255), nullable=False, index=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("evidence_reports.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("custom_title", sa.String(500), nullable=True),
        sa.Column("custom_summary", sa.Text(), nullable=True),
        sa.Column("download_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "evidence_gate_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("public_evidence_reports.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "lead_capture_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(50), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ref_code", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("converted_to_signup", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_lead_capture_source", "lead_capture_events", ["source", "created_at"])
    op.create_index("idx_lead_capture_email", "lead_capture_events", ["email"])

    # =========================================================================
    # MODULE 5: Referral System
    # =========================================================================
    op.create_table(
        "referral_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("code", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("referrer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("referred_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("referral_code", sa.String(20), nullable=False),
        sa.Column("referral_tier", sa.String(20), nullable=False, server_default="standard"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("referred_email", sa.String(255), nullable=False),
        sa.Column("referred_org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("referrer_id", "referred_id", name="uq_referrals_referrer_referred"),
    )

    op.create_table(
        "referral_rewards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("referral_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("referrals.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("beneficiary_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("beneficiary_org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "org_plan_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("override_type", sa.String(30), nullable=False),
        sa.Column("override_value", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_referral_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # =========================================================================
    # MODULE 7: Webhooks
    # =========================================================================
    op.create_table(
        "webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("events", postgresql.JSON(), nullable=False),
        sa.Column("secret_hash", sa.String(255), nullable=True),
        sa.Column("custom_headers", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("webhook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("webhooks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_webhook_deliveries_webhook", "webhook_deliveries", ["webhook_id", "created_at"])
    op.create_index("idx_webhook_deliveries_pending", "webhook_deliveries", ["status", "next_retry_at"],
                     postgresql_where=sa.text("status IN ('pending', 'failed')"))

    # =========================================================================
    # MODULE 9: Status Pages
    # =========================================================================
    op.create_table(
        "status_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("show_uptime_graph", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("show_incident_history", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("branding", postgresql.JSON(), nullable=True),
        sa.Column("allowed_domains", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "status_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="operational"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("uptime_30d", sa.Float(), nullable=False, server_default="100.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # =========================================================================
    # SEED DATA: Default system status components
    # =========================================================================
    op.execute("""
        INSERT INTO status_components (name, display_name, status, description, order_index, is_public, uptime_30d)
        VALUES
            ('api', 'API', 'operational', 'Core API service', 1, true, 100.0),
            ('check-engine', 'Check Engine', 'operational', 'Endpoint monitoring engine', 2, true, 100.0),
            ('dashboard', 'Dashboard', 'operational', 'Web dashboard and UI', 3, true, 100.0),
            ('auth', 'Authentication', 'operational', 'Login, OAuth, and API keys', 4, true, 100.0),
            ('billing', 'Billing', 'operational', 'Subscription and payment processing', 5, true, 100.0)
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    # Drop in reverse order
    op.drop_table("status_components")
    op.drop_table("status_pages")
    op.drop_index("idx_webhook_deliveries_pending", table_name="webhook_deliveries")
    op.drop_index("idx_webhook_deliveries_webhook", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_table("webhooks")
    op.drop_table("org_plan_overrides")
    op.drop_table("referral_rewards")
    op.drop_table("referrals")
    op.drop_table("referral_codes")
    op.drop_index("idx_lead_capture_email", table_name="lead_capture_events")
    op.drop_index("idx_lead_capture_source", table_name="lead_capture_events")
    op.drop_table("lead_capture_events")
    op.drop_table("evidence_gate_tokens")
    op.drop_table("public_evidence_reports")
    op.drop_table("vendor_submission_endpoints")
    op.drop_table("vendor_submissions")
    op.drop_table("timeline_shares")
    op.drop_index("idx_badge_impressions_date", table_name="badge_impressions")
    op.drop_index("idx_badge_impressions_vendor", table_name="badge_impressions")
    op.drop_table("badge_impressions")
