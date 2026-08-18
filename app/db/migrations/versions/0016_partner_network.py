"""partner_network

Creates the Partner Network & Distribution schema: 22 tables covering
partner accounts and applications, campaigns and referral links, click
tracking and attribution, the immutable commission ledger, monthly
settlements, payouts, lead introductions, deployment claims, fraud risk
assessment, geo caching and backend-managed program content.

Design decisions that are load-bearing here:

* Status columns are plain ``VARCHAR`` rather than PostgreSQL ``ENUM``
  types, matching the rest of this schema — adding a state stays a code
  change instead of an ``ALTER TYPE`` migration.
* All money is ``BIGINT`` minor units paired with a 3-character
  ``currency``. There is no floating point anywhere in the ledger.
* Rate columns are integer basis points guarded by
  ``BETWEEN 0 AND 10000`` check constraints.
* Idempotency is enforced by the database, not merely by application code.
  ``uq_partner_commissions_idempotency`` makes double accrual impossible,
  ``uq_partner_payouts_idempotency`` makes double payment impossible, and
  ``uq_partner_payout_items_commission`` guarantees a commission can be
  paid at most once.
* ``partner_commissions`` references its partner and relationship with
  ``ON DELETE RESTRICT`` — financial history must not vanish because a
  parent row was removed.
* ``partner_deployment_claims.relationship_id`` and
  ``partner_customer_relationships.claim_id`` reference each other, so that
  one constraint is added by a separate ``ALTER TABLE`` after both tables
  exist.

The migration is purely additive: no existing table is altered and no
existing column is dropped.

Revision ID: 0016_partner_network
Revises: 0015_production_hardening
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_partner_network"
down_revision: Union[str, None] = "0015_production_hardening"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Drop order for downgrade — children before parents.
_TABLES_IN_DROP_ORDER = [
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
    op.create_table('geo_ip_cache',
    sa.Column('ip_hash', sa.String(length=64), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('country_name', sa.String(length=100), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('looked_up_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ip_hash', name='uq_geo_ip_cache_ip_hash')
    )
    op.create_index('ix_geo_ip_cache_country', 'geo_ip_cache', ['country_code'], unique=False)
    op.create_table('partner_program_content',
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('locale', sa.String(length=10), nullable=False),
    sa.Column('section', sa.String(length=60), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('version', sa.String(length=30), nullable=True),
    sa.Column('updated_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key', 'locale', name='uq_partner_program_content_key_locale')
    )
    op.create_index('ix_partner_program_content_section', 'partner_program_content', ['section', 'sort_order'], unique=False)
    op.create_table('partners',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('referral_code_id', sa.UUID(), nullable=True),
    sa.Column('partner_code', sa.String(length=32), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=True),
    sa.Column('partner_type', sa.String(length=40), nullable=False),
    sa.Column('tier', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('headline', sa.String(length=255), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('website_url', sa.String(length=500), nullable=True),
    sa.Column('logo_url', sa.String(length=500), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('expertise', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('languages', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('is_publicly_listed', sa.Boolean(), nullable=False),
    sa.Column('contact_email', sa.String(length=320), nullable=True),
    sa.Column('contact_phone', sa.String(length=50), nullable=True),
    sa.Column('custom_rate_bps', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('payout_currency', sa.String(length=3), nullable=False),
    sa.Column('min_payout_minor', sa.BigInteger(), nullable=True),
    sa.Column('lifetime_revenue_minor', sa.BigInteger(), nullable=False),
    sa.Column('lifetime_commission_minor', sa.BigInteger(), nullable=False),
    sa.Column('active_customer_count', sa.Integer(), nullable=False),
    sa.Column('total_click_count', sa.Integer(), nullable=False),
    sa.Column('total_signup_count', sa.Integer(), nullable=False),
    sa.Column('aggregates_updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('risk_score', sa.Integer(), nullable=False),
    sa.Column('risk_band', sa.String(length=20), nullable=False),
    sa.Column('risk_evaluated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('commissions_held', sa.Boolean(), nullable=False),
    sa.Column('agreement_version', sa.String(length=30), nullable=True),
    sa.Column('agreement_accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tax_form_status', sa.String(length=30), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('suspended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('suspension_reason', sa.Text(), nullable=True),
    sa.Column('terminated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tier_evaluated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('lifetime_revenue_minor >= 0', name='ck_partners_lifetime_revenue_nonneg'),
    sa.CheckConstraint('risk_score BETWEEN 0 AND 100', name='ck_partners_risk_score'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['referral_code_id'], ['referral_codes.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_code', name='uq_partners_partner_code'),
    sa.UniqueConstraint('slug', name='uq_partners_slug'),
    sa.UniqueConstraint('user_id', name='uq_partners_user_id')
    )
    op.create_index(op.f('ix_partners_country_code'), 'partners', ['country_code'], unique=False)
    op.create_index('ix_partners_directory', 'partners', ['is_publicly_listed', 'status'], unique=False)
    op.create_index(op.f('ix_partners_organization_id'), 'partners', ['organization_id'], unique=False)
    op.create_index(op.f('ix_partners_referral_code_id'), 'partners', ['referral_code_id'], unique=False)
    op.create_index('ix_partners_status_tier', 'partners', ['status', 'tier'], unique=False)
    op.create_index(op.f('ix_partners_user_id'), 'partners', ['user_id'], unique=False)
    op.create_table('partner_applications',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('partner_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('partner_type', sa.String(length=40), nullable=False),
    sa.Column('display_name', sa.String(length=160), nullable=False),
    sa.Column('legal_name', sa.String(length=200), nullable=True),
    sa.Column('contact_email', sa.String(length=320), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('website_url', sa.String(length=500), nullable=True),
    sa.Column('intended_methods', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('audience_description', sa.Text(), nullable=True),
    sa.Column('estimated_monthly_reach', sa.Integer(), nullable=True),
    sa.Column('experience', sa.Text(), nullable=True),
    sa.Column('motivation', sa.Text(), nullable=True),
    sa.Column('answers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('agreement_version', sa.String(length=30), nullable=True),
    sa.Column('agreement_accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_partner_applications_partner_id'), 'partner_applications', ['partner_id'], unique=False)
    op.create_index(op.f('ix_partner_applications_status'), 'partner_applications', ['status'], unique=False)
    op.create_index('ix_partner_applications_status_created', 'partner_applications', ['status', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_applications_user_id'), 'partner_applications', ['user_id'], unique=False)
    op.create_index('ix_partner_applications_user_status', 'partner_applications', ['user_id', 'status'], unique=False)
    op.create_table('partner_campaigns',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('campaign_code', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('destination_path', sa.String(length=500), nullable=True),
    sa.Column('default_utm', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('channel', sa.String(length=60), nullable=True),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('click_count', sa.Integer(), nullable=False),
    sa.Column('unique_visitor_count', sa.Integer(), nullable=False),
    sa.Column('signup_count', sa.Integer(), nullable=False),
    sa.Column('conversion_count', sa.Integer(), nullable=False),
    sa.Column('attributed_revenue_minor', sa.BigInteger(), nullable=False),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'campaign_code', name='uq_partner_campaigns_partner_code')
    )
    op.create_index(op.f('ix_partner_campaigns_partner_id'), 'partner_campaigns', ['partner_id'], unique=False)
    op.create_index('ix_partner_campaigns_partner_status', 'partner_campaigns', ['partner_id', 'status'], unique=False)
    op.create_table('partner_deployment_claims',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('customer_identifier', sa.String(length=255), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('earning_method', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('customer_confirmed', sa.Boolean(), nullable=False),
    sa.Column('customer_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
    sa.Column('review_notes', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('relationship_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_deployment_claims_org', 'partner_deployment_claims', ['organization_id'], unique=False)
    op.create_index(op.f('ix_partner_deployment_claims_partner_id'), 'partner_deployment_claims', ['partner_id'], unique=False)
    op.create_index('ix_partner_deployment_claims_partner_status', 'partner_deployment_claims', ['partner_id', 'status'], unique=False)
    op.create_index(op.f('ix_partner_deployment_claims_status'), 'partner_deployment_claims', ['status'], unique=False)
    op.create_index('ix_partner_deployment_claims_status_created', 'partner_deployment_claims', ['status', 'created_at'], unique=False)
    op.create_table('partner_geo_daily',
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=False),
    sa.Column('country_name', sa.String(length=100), nullable=True),
    sa.Column('partner_id', sa.UUID(), nullable=True),
    sa.Column('click_count', sa.Integer(), nullable=False),
    sa.Column('unique_visitor_count', sa.Integer(), nullable=False),
    sa.Column('signup_count', sa.Integer(), nullable=False),
    sa.Column('conversion_count', sa.Integer(), nullable=False),
    sa.Column('revenue_minor', sa.BigInteger(), nullable=False),
    sa.Column('commission_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('day', 'country_code', 'partner_id', name='uq_partner_geo_daily_day_country_partner')
    )
    op.create_index('ix_partner_geo_daily_day', 'partner_geo_daily', ['day'], unique=False)
    op.create_index('ix_partner_geo_daily_partner_day', 'partner_geo_daily', ['partner_id', 'day'], unique=False)
    op.create_table('partner_leads',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('company_name', sa.String(length=200), nullable=False),
    sa.Column('contact_name', sa.String(length=160), nullable=False),
    sa.Column('contact_email', sa.String(length=320), nullable=False),
    sa.Column('contact_email_hash', sa.String(length=64), nullable=False),
    sa.Column('contact_phone', sa.String(length=50), nullable=True),
    sa.Column('contact_title', sa.String(length=120), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('company_size', sa.String(length=40), nullable=True),
    sa.Column('industry', sa.String(length=80), nullable=True),
    sa.Column('use_case', sa.Text(), nullable=True),
    sa.Column('estimated_value_minor', sa.BigInteger(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('consent_confirmed', sa.Boolean(), nullable=False),
    sa.Column('consent_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exclusive_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('contacted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('converted_organization_id', sa.UUID(), nullable=True),
    sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['converted_organization_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_leads_email_hash', 'partner_leads', ['contact_email_hash'], unique=False)
    op.create_index(op.f('ix_partner_leads_partner_id'), 'partner_leads', ['partner_id'], unique=False)
    op.create_index('ix_partner_leads_partner_status', 'partner_leads', ['partner_id', 'status'], unique=False)
    op.create_index(op.f('ix_partner_leads_status'), 'partner_leads', ['status'], unique=False)
    op.create_index('ix_partner_leads_status_created', 'partner_leads', ['status', 'created_at'], unique=False)
    op.create_table('partner_payout_accounts',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('method', sa.String(length=40), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('display_label', sa.String(length=120), nullable=True),
    sa.Column('account_last4', sa.String(length=4), nullable=True),
    sa.Column('bank_name', sa.String(length=120), nullable=True),
    sa.Column('encrypted_details', sa.Text(), nullable=True),
    sa.Column('provider_recipient_code', sa.String(length=120), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('is_verified', sa.Boolean(), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_payout_accounts_partner', 'partner_payout_accounts', ['partner_id', 'is_default'], unique=False)
    op.create_index(op.f('ix_partner_payout_accounts_partner_id'), 'partner_payout_accounts', ['partner_id'], unique=False)
    op.create_table('partner_risk_assessments',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('band', sa.String(length=20), nullable=False),
    sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('triggered_hold', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.CheckConstraint('score BETWEEN 0 AND 100', name='ck_partner_risk_score'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_risk_assessments_partner_created', 'partner_risk_assessments', ['partner_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_risk_assessments_partner_id'), 'partner_risk_assessments', ['partner_id'], unique=False)
    op.create_table('partner_tier_history',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('from_tier', sa.String(length=30), nullable=True),
    sa.Column('to_tier', sa.String(length=30), nullable=False),
    sa.Column('reason', sa.String(length=80), nullable=False),
    sa.Column('metrics_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('changed_by_id', sa.UUID(), nullable=True),
    sa.Column('is_automatic', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_tier_history_partner_created', 'partner_tier_history', ['partner_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_tier_history_partner_id'), 'partner_tier_history', ['partner_id'], unique=False)
    op.create_table('partner_claim_evidence',
    sa.Column('claim_id', sa.UUID(), nullable=False),
    sa.Column('evidence_type', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('url', sa.String(length=1000), nullable=True),
    sa.Column('storage_key', sa.String(length=500), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('uploaded_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['claim_id'], ['partner_deployment_claims.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_claim_evidence_claim', 'partner_claim_evidence', ['claim_id'], unique=False)
    op.create_index(op.f('ix_partner_claim_evidence_claim_id'), 'partner_claim_evidence', ['claim_id'], unique=False)
    op.create_table('partner_payouts',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('payout_account_id', sa.UUID(), nullable=True),
    sa.Column('reference', sa.String(length=64), nullable=False),
    sa.Column('idempotency_key', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('method', sa.String(length=40), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('fee_minor', sa.BigInteger(), nullable=False),
    sa.Column('net_amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('commission_count', sa.Integer(), nullable=False),
    sa.Column('period_month', sa.String(length=7), nullable=True),
    sa.Column('provider', sa.String(length=40), nullable=True),
    sa.Column('provider_reference', sa.String(length=200), nullable=True),
    sa.Column('provider_status', sa.String(length=60), nullable=True),
    sa.Column('provider_response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by_id', sa.UUID(), nullable=True),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('amount_minor >= 0', name='ck_partner_payouts_amount_nonneg'),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payout_account_id'], ['partner_payout_accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'idempotency_key', name='uq_partner_payouts_idempotency'),
    sa.UniqueConstraint('reference', name='uq_partner_payouts_reference')
    )
    op.create_index(op.f('ix_partner_payouts_partner_id'), 'partner_payouts', ['partner_id'], unique=False)
    op.create_index('ix_partner_payouts_partner_status', 'partner_payouts', ['partner_id', 'status'], unique=False)
    op.create_index(op.f('ix_partner_payouts_status'), 'partner_payouts', ['status'], unique=False)
    op.create_index('ix_partner_payouts_status_created', 'partner_payouts', ['status', 'created_at'], unique=False)
    op.create_table('partner_referral_links',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('link_token', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=160), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('is_default', sa.Boolean(), nullable=False),
    sa.Column('destination_path', sa.String(length=500), nullable=True),
    sa.Column('utm', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('click_count', sa.Integer(), nullable=False),
    sa.Column('unique_visitor_count', sa.Integer(), nullable=False),
    sa.Column('signup_count', sa.Integer(), nullable=False),
    sa.Column('last_clicked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['campaign_id'], ['partner_campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('link_token', name='uq_partner_referral_links_token')
    )
    op.create_index('ix_partner_referral_links_campaign', 'partner_referral_links', ['campaign_id'], unique=False)
    op.create_index(op.f('ix_partner_referral_links_partner_id'), 'partner_referral_links', ['partner_id'], unique=False)
    op.create_index('ix_partner_referral_links_partner_status', 'partner_referral_links', ['partner_id', 'status'], unique=False)
    op.create_table('partner_click_events',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('link_id', sa.UUID(), nullable=True),
    sa.Column('visitor_id', sa.String(length=64), nullable=False),
    sa.Column('ip_hash', sa.String(length=64), nullable=True),
    sa.Column('user_agent', sa.String(length=500), nullable=True),
    sa.Column('referer', sa.String(length=500), nullable=True),
    sa.Column('utm_source', sa.String(length=255), nullable=True),
    sa.Column('utm_medium', sa.String(length=255), nullable=True),
    sa.Column('utm_campaign', sa.String(length=255), nullable=True),
    sa.Column('utm_term', sa.String(length=255), nullable=True),
    sa.Column('utm_content', sa.String(length=255), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('country_name', sa.String(length=100), nullable=True),
    sa.Column('is_duplicate', sa.Boolean(), nullable=False),
    sa.Column('is_bot', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['campaign_id'], ['partner_campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['link_id'], ['partner_referral_links.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_click_events_campaign_created', 'partner_click_events', ['campaign_id', 'created_at'], unique=False)
    op.create_index('ix_partner_click_events_country', 'partner_click_events', ['country_code', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_click_events_created_at'), 'partner_click_events', ['created_at'], unique=False)
    op.create_index('ix_partner_click_events_partner_created', 'partner_click_events', ['partner_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_click_events_partner_id'), 'partner_click_events', ['partner_id'], unique=False)
    op.create_index('ix_partner_click_events_visitor', 'partner_click_events', ['visitor_id', 'created_at'], unique=False)
    op.create_table('partner_settlements',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('period_month', sa.String(length=7), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('gross_commission_minor', sa.BigInteger(), nullable=False),
    sa.Column('reversal_minor', sa.BigInteger(), nullable=False),
    sa.Column('adjustment_minor', sa.BigInteger(), nullable=False),
    sa.Column('net_commission_minor', sa.BigInteger(), nullable=False),
    sa.Column('commission_count', sa.Integer(), nullable=False),
    sa.Column('revenue_minor', sa.BigInteger(), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('payout_id', sa.UUID(), nullable=True),
    sa.Column('breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['payout_id'], ['partner_payouts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'period_month', name='uq_partner_settlements_period')
    )
    op.create_index(op.f('ix_partner_settlements_partner_id'), 'partner_settlements', ['partner_id'], unique=False)
    op.create_index('ix_partner_settlements_period_status', 'partner_settlements', ['period_month', 'status'], unique=False)
    op.create_table('partner_attributions',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('link_id', sa.UUID(), nullable=True),
    sa.Column('click_event_id', sa.UUID(), nullable=True),
    sa.Column('visitor_id', sa.String(length=64), nullable=True),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('model', sa.String(length=30), nullable=False),
    sa.Column('touchpoint_type', sa.String(length=30), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('weight_bps', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('utm', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('weight_bps BETWEEN 0 AND 10000', name='ck_partner_attributions_weight'),
    sa.ForeignKeyConstraint(['campaign_id'], ['partner_campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['click_event_id'], ['partner_click_events.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['link_id'], ['partner_referral_links.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_partner_attributions_organization_id'), 'partner_attributions', ['organization_id'], unique=False)
    op.create_index('ix_partner_attributions_partner', 'partner_attributions', ['partner_id', 'occurred_at'], unique=False)
    op.create_index(op.f('ix_partner_attributions_partner_id'), 'partner_attributions', ['partner_id'], unique=False)
    op.create_index(op.f('ix_partner_attributions_status'), 'partner_attributions', ['status'], unique=False)
    op.create_index('ix_partner_attributions_status_expires', 'partner_attributions', ['status', 'expires_at'], unique=False)
    op.create_index('ix_partner_attributions_user', 'partner_attributions', ['user_id', 'occurred_at'], unique=False)
    op.create_index('ix_partner_attributions_visitor', 'partner_attributions', ['visitor_id', 'occurred_at'], unique=False)
    op.create_table('partner_customer_relationships',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('organization_id', sa.UUID(), nullable=False),
    sa.Column('customer_user_id', sa.UUID(), nullable=True),
    sa.Column('earning_method', sa.String(length=30), nullable=False),
    sa.Column('rate_bps', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('attribution_id', sa.UUID(), nullable=True),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('lead_id', sa.UUID(), nullable=True),
    sa.Column('claim_id', sa.UUID(), nullable=True),
    sa.Column('referral_id', sa.UUID(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('eligible_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_reason', sa.String(length=60), nullable=True),
    sa.Column('total_revenue_minor', sa.BigInteger(), nullable=False),
    sa.Column('total_commission_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('rate_bps BETWEEN 0 AND 10000', name='ck_partner_customer_rel_rate'),
    sa.ForeignKeyConstraint(['attribution_id'], ['partner_attributions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['campaign_id'], ['partner_campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['claim_id'], ['partner_deployment_claims.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['customer_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['lead_id'], ['partner_leads.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['referral_id'], ['referrals.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'partner_id', 'earning_method', name='uq_partner_customer_rel_unique')
    )
    op.create_index('ix_partner_customer_rel_org_status', 'partner_customer_relationships', ['organization_id', 'status'], unique=False)
    op.create_index('ix_partner_customer_rel_partner_status', 'partner_customer_relationships', ['partner_id', 'status'], unique=False)
    op.create_index(op.f('ix_partner_customer_relationships_organization_id'), 'partner_customer_relationships', ['organization_id'], unique=False)
    op.create_index(op.f('ix_partner_customer_relationships_partner_id'), 'partner_customer_relationships', ['partner_id'], unique=False)
    op.create_index(op.f('ix_partner_customer_relationships_status'), 'partner_customer_relationships', ['status'], unique=False)
    op.create_table('partner_commissions',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('relationship_id', sa.UUID(), nullable=True),
    sa.Column('organization_id', sa.UUID(), nullable=True),
    sa.Column('campaign_id', sa.UUID(), nullable=True),
    sa.Column('entry_type', sa.String(length=30), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('earning_method', sa.String(length=30), nullable=True),
    sa.Column('source_amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('commissionable_amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('rate_bps', sa.Integer(), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('calculation_basis', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('idempotency_key', sa.String(length=255), nullable=False),
    sa.Column('source_type', sa.String(length=40), nullable=False),
    sa.Column('source_reference', sa.String(length=255), nullable=True),
    sa.Column('payment_provider', sa.String(length=40), nullable=True),
    sa.Column('period_month', sa.String(length=7), nullable=True),
    sa.Column('earned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hold_reason', sa.String(length=50), nullable=True),
    sa.Column('payable_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('became_payable_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reversed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reversal_reason', sa.String(length=50), nullable=True),
    sa.Column('reverses_id', sa.UUID(), nullable=True),
    sa.Column('payout_id', sa.UUID(), nullable=True),
    sa.Column('settlement_id', sa.UUID(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('rate_bps BETWEEN 0 AND 10000', name='ck_partner_commissions_rate'),
    sa.CheckConstraint('source_amount_minor >= 0', name='ck_partner_commissions_source_nonneg'),
    sa.ForeignKeyConstraint(['campaign_id'], ['partner_campaigns.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payout_id'], ['partner_payouts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['relationship_id'], ['partner_customer_relationships.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reverses_id'], ['partner_commissions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['settlement_id'], ['partner_settlements.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partner_id', 'entry_type', 'idempotency_key', name='uq_partner_commissions_idempotency')
    )
    op.create_index(op.f('ix_partner_commissions_organization_id'), 'partner_commissions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_partner_commissions_partner_id'), 'partner_commissions', ['partner_id'], unique=False)
    op.create_index('ix_partner_commissions_partner_status', 'partner_commissions', ['partner_id', 'status'], unique=False)
    op.create_index('ix_partner_commissions_payout', 'partner_commissions', ['payout_id'], unique=False)
    op.create_index('ix_partner_commissions_period', 'partner_commissions', ['partner_id', 'period_month'], unique=False)
    op.create_index('ix_partner_commissions_relationship', 'partner_commissions', ['relationship_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_commissions_status'), 'partner_commissions', ['status'], unique=False)
    op.create_index('ix_partner_commissions_status_payable', 'partner_commissions', ['status', 'payable_at'], unique=False)
    op.create_table('partner_commission_events',
    sa.Column('commission_id', sa.UUID(), nullable=False),
    sa.Column('from_status', sa.String(length=30), nullable=True),
    sa.Column('to_status', sa.String(length=30), nullable=False),
    sa.Column('reason', sa.String(length=80), nullable=True),
    sa.Column('actor_user_id', sa.UUID(), nullable=True),
    sa.Column('actor_type', sa.String(length=20), nullable=False),
    sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['commission_id'], ['partner_commissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_partner_commission_events_commission', 'partner_commission_events', ['commission_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_partner_commission_events_commission_id'), 'partner_commission_events', ['commission_id'], unique=False)
    op.create_table('partner_fraud_flags',
    sa.Column('partner_id', sa.UUID(), nullable=False),
    sa.Column('assessment_id', sa.UUID(), nullable=True),
    sa.Column('signal', sa.String(length=60), nullable=False),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('score_at_flag', sa.Integer(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('related_commission_id', sa.UUID(), nullable=True),
    sa.Column('related_organization_id', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_id', sa.UUID(), nullable=True),
    sa.Column('resolution', sa.String(length=40), nullable=True),
    sa.Column('resolution_notes', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['assessment_id'], ['partner_risk_assessments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['partner_id'], ['partners.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['related_commission_id'], ['partner_commissions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['related_organization_id'], ['organizations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_partner_fraud_flags_partner_id'), 'partner_fraud_flags', ['partner_id'], unique=False)
    op.create_index('ix_partner_fraud_flags_partner_status', 'partner_fraud_flags', ['partner_id', 'status'], unique=False)
    op.create_index(op.f('ix_partner_fraud_flags_status'), 'partner_fraud_flags', ['status'], unique=False)
    op.create_index('ix_partner_fraud_flags_status_created', 'partner_fraud_flags', ['status', 'created_at'], unique=False)
    op.create_table('partner_payout_items',
    sa.Column('payout_id', sa.UUID(), nullable=False),
    sa.Column('commission_id', sa.UUID(), nullable=False),
    sa.Column('amount_minor', sa.BigInteger(), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['commission_id'], ['partner_commissions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['payout_id'], ['partner_payouts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('commission_id', name='uq_partner_payout_items_commission')
    )
    op.create_index('ix_partner_payout_items_payout', 'partner_payout_items', ['payout_id'], unique=False)

    # Close the deployment-claim <-> relationship cycle now that both
    # tables exist.
    op.create_foreign_key(
        "fk_partner_deployment_claims_relationship_id",
        "partner_deployment_claims",
        "partner_customer_relationships",
        ["relationship_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop every partner table.

    The cyclic FK is dropped first, then tables go children-before-parents;
    ``CASCADE`` clears the remaining dependent indexes and constraints.
    """
    op.execute(
        "ALTER TABLE IF EXISTS partner_deployment_claims "
        "DROP CONSTRAINT IF EXISTS fk_partner_deployment_claims_relationship_id"
    )
    for table in _TABLES_IN_DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
