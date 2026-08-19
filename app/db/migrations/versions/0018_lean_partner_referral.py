"""lean_partner_referral

Replaces the 22-table Partner Network schema with the minimal Partner
Referral program: four tables covering the single ``refer → subscribe →
30% recurring commission → payout`` lifecycle.

* Drops every Partner Network table from ``0016_partner_network``.
* Creates ``partner_profiles``, ``partner_referrals``,
  ``partner_commissions`` and ``partner_payouts``.
* Partner identity reuses the existing ``referral_codes`` table.

Money is ``BIGINT`` minor units; rates are integer percentages; duplicate
commission accrual is prevented by ``uq_partner_commissions_idempotency``.

Revision ID: 0018_lean_partner_referral
Revises: 0017_soft_delete_members_api_keys
Create Date: 2026-08-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0018_lean_partner_referral"
down_revision: Union[str, None] = "0017_soft_delete_members_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_PARTNER_TABLES = [
    "partner_payout_items",
    "partner_commission_events",
    "partner_commissions",
    "partner_settlements",
    "partner_payouts",
    "partner_payout_accounts",
    "partner_fraud_flags",
    "partner_risk_assessments",
    "partner_claim_evidence",
    "partner_deployment_claims",
    "partner_customer_relationships",
    "partner_leads",
    "partner_attributions",
    "partner_click_events",
    "partner_referral_links",
    "partner_campaigns",
    "partner_tier_history",
    "partner_applications",
    "partners",
    "partner_geo_daily",
    "geo_ip_cache",
    "partner_program_content",
]


def upgrade() -> None:
    # Drop the cyclic FK before dropping the deployment-claims table.
    op.execute(
        "ALTER TABLE IF EXISTS partner_deployment_claims "
        "DROP CONSTRAINT IF EXISTS fk_partner_deployment_claims_relationship_id"
    )
    for table in _OLD_PARTNER_TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.create_table(
        "partner_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referral_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("referral_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("click_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", name="uq_partner_profiles_user_id"),
        sa.UniqueConstraint(
            "referral_code_id", name="uq_partner_profiles_referral_code_id"
        ),
    )
    op.create_index(
        "ix_partner_profiles_user_id", "partner_profiles", ["user_id"], unique=False
    )
    op.create_index(
        "ix_partner_profiles_referral_code_id",
        "partner_profiles",
        ["referral_code_id"],
        unique=False,
    )

    op.create_table(
        "partner_referrals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="signed_up"),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "referred_user_id", name="uq_partner_referrals_referred_user_id"
        ),
    )
    op.create_index(
        "ix_partner_referrals_partner_id", "partner_referrals", ["partner_id"], unique=False
    )
    op.create_index(
        "ix_partner_referrals_referred_user_id",
        "partner_referrals",
        ["referred_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_partner_referrals_partner_status",
        "partner_referrals",
        ["partner_id", "status"],
        unique=False,
    )

    op.create_table(
        "partner_payouts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("period", sa.String(7), nullable=True),
        sa.Column("transaction_reference", sa.String(200), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_partner_payouts_partner_id", "partner_payouts", ["partner_id"], unique=False
    )
    op.create_index(
        "ix_partner_payouts_partner_status",
        "partner_payouts",
        ["partner_id", "status"],
        unique=False,
    )

    op.create_table(
        "partner_commissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referral_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_referrals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("billing_event_id", sa.String(200), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("subscription_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("commission_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("rate", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payable_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversal_reason", sa.String(100), nullable=True),
        sa.Column(
            "payout_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_payouts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "billing_event_id", "partner_id", name="uq_partner_commissions_idempotency"
        ),
    )
    op.create_index(
        "ix_partner_commissions_partner_id", "partner_commissions", ["partner_id"], unique=False
    )
    op.create_index(
        "ix_partner_commissions_status", "partner_commissions", ["status"], unique=False
    )
    op.create_index(
        "ix_partner_commissions_partner_status",
        "partner_commissions",
        ["partner_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    for table in [
        "partner_commissions",
        "partner_payouts",
        "partner_referrals",
        "partner_profiles",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
