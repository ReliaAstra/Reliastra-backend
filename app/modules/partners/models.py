"""SQLAlchemy models for the Partner Network & Distribution Infrastructure.

Design rules enforced throughout this module:

* **Money is never a float.** Every monetary column is a ``BigInteger``
  holding *minor units* (cents) and is always paired with a ``currency``
  column. Rates are ``Integer`` basis points.
* **The commission ledger is append-only.** ``PartnerCommission`` rows are
  never mutated except for their status field (whose transitions are
  themselves recorded in ``PartnerCommissionEvent``). Corrections are new
  rows of type ``reversal``/``adjustment`` that point back at the original.
* **Partner identity reuses the existing referral system.** A partner links
  to their existing ``referral_codes`` row via ``referral_code_id`` instead
  of introducing a parallel identity; ``partner_code`` is the public,
  human-shareable handle used in ``/r/{partner_code}`` links.
* **Soft deletes are respected** wherever the platform already uses them.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

# ─────────────────────────────────────────────────────────────────────────
# Partner identity
# ─────────────────────────────────────────────────────────────────────────


class Partner(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A partner account.

    One partner per user. The partner may optionally be backed by an
    organisation (agencies, resellers, system integrators).
    """

    __tablename__ = "partners"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_partners_user_id"),
        UniqueConstraint("partner_code", name="uq_partners_partner_code"),
        UniqueConstraint("slug", name="uq_partners_slug"),
        Index("ix_partners_status_tier", "status", "tier"),
        Index("ix_partners_directory", "is_publicly_listed", "status"),
        CheckConstraint(
            "lifetime_revenue_minor >= 0", name="ck_partners_lifetime_revenue_nonneg"
        ),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_partners_risk_score"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    #: Link to the pre-existing PLG referral identity. The partner does not
    #: get a second, competing referral identity — this is the same code.
    referral_code_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("referral_codes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    #: Public handle used in https://<public-url>/r/{partner_code}
    partner_code: Mapped[str] = mapped_column(String(32), nullable=False)
    #: URL-safe handle for the public partner directory page.
    slug: Mapped[str] = mapped_column(String(80), nullable=False)

    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    partner_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="individual"
    )
    tier: Mapped[str] = mapped_column(String(30), nullable=False, default="explorer")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")

    # Public profile (safe to expose on /v1/public/partners/{slug})
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    #: Free-form service/expertise tags used by the public directory filter.
    expertise: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    languages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_publicly_listed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Contact — never exposed publicly
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Commercial terms. NULL means "use the configured default for the
    # earning method". Custom terms are a STRATEGIC-tier capability and are
    # always capped by PARTNER_MAX_TOTAL_COMMISSION_BPS at calculation time.
    custom_rate_bps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    payout_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD"
    )
    min_payout_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Cached aggregates. These are a *cache*, never the source of truth —
    # the ledger is. Recomputed by background jobs.
    lifetime_revenue_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    lifetime_commission_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    active_customer_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_signup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aggregates_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Risk
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_band: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    risk_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: When set, new commissions are created HELD instead of PENDING.
    commissions_held: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Compliance / lifecycle
    agreement_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agreement_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tax_form_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_required"
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    terminated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tier_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PartnerApplication(UUIDMixin, TimestampMixin, Base):
    """An application to join the partner network.

    Kept separate from :class:`Partner` so that rejected/withdrawn
    applications remain fully auditable and a user may reapply.
    """

    __tablename__ = "partner_applications"
    __table_args__ = (
        Index("ix_partner_applications_status_created", "status", "created_at"),
        Index("ix_partner_applications_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partners.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="submitted", index=True
    )
    partner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    #: Which earning methods the applicant intends to use.
    intended_methods: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    audience_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_monthly_reach: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    answers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    agreement_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agreement_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnerTierHistory(UUIDMixin, TimestampMixin, Base):
    """Append-only record of every tier change, manual or automatic."""

    __tablename__ = "partner_tier_history"
    __table_args__ = (
        Index("ix_partner_tier_history_partner_created", "partner_id", "created_at"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_tier: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_tier: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Snapshot of the metrics that justified the change (auditability).
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_automatic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ─────────────────────────────────────────────────────────────────────────
# Campaigns & referral links
# ─────────────────────────────────────────────────────────────────────────


class PartnerCampaign(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A named campaign owned by a partner.

    Campaigns segment a partner's traffic. They never create a second
    identity: the canonical link stays ``/r/{partner_code}`` and the campaign
    travels as ``?campaign={campaign_code}``.
    """

    __tablename__ = "partner_campaigns"
    __table_args__ = (
        UniqueConstraint(
            "partner_id", "campaign_code", name="uq_partner_campaigns_partner_code"
        ),
        Index("ix_partner_campaigns_partner_status", "partner_id", "status"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

    #: Default landing path on the public site (validated to be a same-origin
    #: relative path — open-redirect protection).
    destination_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: Default UTM values applied when the visitor supplies none.
    default_utm: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    channel: Mapped[str | None] = mapped_column(String(60), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Cached counters (source of truth is the click/attribution tables).
    click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_visitor_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    signup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributed_revenue_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )

    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PartnerReferralLink(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A concrete, shareable link.

    Every partner has exactly one default link (``is_default``) pointing at
    ``/r/{partner_code}``. Additional links add a campaign and/or a landing
    path, but always resolve back to the same partner code.
    """

    __tablename__ = "partner_referral_links"
    __table_args__ = (
        UniqueConstraint("link_token", name="uq_partner_referral_links_token"),
        Index("ix_partner_referral_links_partner_status", "partner_id", "status"),
        Index("ix_partner_referral_links_campaign", "campaign_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_campaigns.id", ondelete="CASCADE"), nullable=True
    )

    #: Stable opaque identifier for this link row (used for analytics joins
    #: and short links). Not the public partner code.
    link_token: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    destination_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    utm: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_visitor_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    signup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_clicked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ─────────────────────────────────────────────────────────────────────────
# Click tracking & attribution
# ─────────────────────────────────────────────────────────────────────────


class PartnerClickEvent(UUIDMixin, Base):
    """A single resolution of a partner link.

    Clicks are **analytics only and are never payable**. No commission,
    bounty or reward is ever derived from a row in this table.

    Follows the ``badge_impressions`` precedent: no ``updated_at`` (rows are
    immutable), hashed IP rather than raw IP, and generous nullability
    because visitor-supplied headers cannot be trusted to exist.
    """

    __tablename__ = "partner_click_events"
    __table_args__ = (
        Index("ix_partner_click_events_partner_created", "partner_id", "created_at"),
        Index("ix_partner_click_events_campaign_created", "campaign_id", "created_at"),
        Index("ix_partner_click_events_visitor", "visitor_id", "created_at"),
        Index("ix_partner_click_events_country", "country_code", "created_at"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_referral_links.id", ondelete="SET NULL"), nullable=True
    )

    #: Anonymous first-party visitor identifier issued as a cookie value by
    #: the public resolver. Used to stitch click → signup.
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: SHA-256 of (client IP + server-side salt). Raw IPs are never stored.
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    referer: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # UTM parameters — analytics metadata only. These NEVER override partner
    # ownership; the partner_code in the path is always authoritative.
    utm_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    utm_content: Mapped[str | None] = mapped_column(String(255), nullable=True)

    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    #: True when this click was collapsed into a recent identical click.
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: True when the request looks automated (bot UA, prefetch header). Bot
    #: clicks are retained for analysis but excluded from reported metrics.
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class PartnerAttribution(UUIDMixin, TimestampMixin, Base):
    """A recorded partner touch on a visitor/user.

    v1 resolves ownership with a **last eligible touch** model inside a
    configurable window. The table is deliberately modelled for multi-touch:
    several rows may exist per subject, each carrying its ``touchpoint_type``,
    ``position`` and a ``weight_bps`` that currently is 10000 for the single
    owning touch and 0 for the rest. Introducing a linear or position-based
    model later is a weight recalculation, not a migration.
    """

    __tablename__ = "partner_attributions"
    __table_args__ = (
        Index("ix_partner_attributions_visitor", "visitor_id", "occurred_at"),
        Index("ix_partner_attributions_user", "user_id", "occurred_at"),
        Index("ix_partner_attributions_partner", "partner_id", "occurred_at"),
        Index("ix_partner_attributions_status_expires", "status", "expires_at"),
        CheckConstraint(
            "weight_bps BETWEEN 0 AND 10000", name="ck_partner_attributions_weight"
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    link_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_referral_links.id", ondelete="SET NULL"), nullable=True
    )
    click_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_click_events.id", ondelete="SET NULL"), nullable=True
    )

    #: Subject of the attribution. Starts as an anonymous visitor and is
    #: bound to a user/org at signup.
    visitor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )

    model: Mapped[str] = mapped_column(
        String(30), nullable=False, default="last_touch"
    )
    touchpoint_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="click"
    )
    #: 1-based ordering of this touch within the subject's journey.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Share of credit in basis points. 10000 = full credit (single-touch).
    weight_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", index=True
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    converted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Preserved analytics context at the moment of the touch.
    utm: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnerCustomerRelationship(UUIDMixin, TimestampMixin, Base):
    """The durable, revenue-bearing link between a partner and a customer.

    This is what the commission engine reads. It is created once at
    conversion time from the winning attribution (or from an approved
    deployment claim / converted lead) and then governs every subsequent
    collected payment from that organisation.
    """

    __tablename__ = "partner_customer_relationships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "partner_id",
            "earning_method",
            name="uq_partner_customer_rel_unique",
        ),
        Index("ix_partner_customer_rel_partner_status", "partner_id", "status"),
        Index("ix_partner_customer_rel_org_status", "organization_id", "status"),
        CheckConstraint(
            "rate_bps BETWEEN 0 AND 10000", name="ck_partner_customer_rel_rate"
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    earning_method: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Effective rate snapshotted at relationship creation so that later
    #: config changes cannot silently rewrite historical economics.
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", index=True
    )

    # Provenance — exactly one of these is normally set.
    attribution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_attributions.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_leads.id", ondelete="SET NULL"), nullable=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_deployment_claims.id", ondelete="SET NULL"), nullable=True
    )
    #: Reuses the existing PLG referral row when the relationship originated
    #: from the standard referral flow.
    referral_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("referrals.id", ondelete="SET NULL"), nullable=True
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: For Year-1 methods (introduce) this is started_at + window.
    eligible_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    end_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)

    total_revenue_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    total_commission_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ─────────────────────────────────────────────────────────────────────────
# Commission ledger
# ─────────────────────────────────────────────────────────────────────────


class PartnerCommission(UUIDMixin, TimestampMixin, Base):
    """Immutable commission ledger entry — the authoritative financial record.

    Rows are append-only. The only mutable column is ``status`` (plus its
    timestamps), and every status change writes a
    :class:`PartnerCommissionEvent`. Money that needs to be taken back is
    represented by a *new* ``reversal`` row referencing ``reverses_id``; the
    original row is never edited or deleted.

    ``amount_minor`` is signed: positive for accruals, negative for
    reversals and payouts, so that a partner's balance is always a plain
    ``SUM(amount_minor)`` over the ledger.
    """

    __tablename__ = "partner_commissions"
    __table_args__ = (
        # Hard idempotency: one commission per (relationship, source event).
        UniqueConstraint(
            "partner_id",
            "entry_type",
            "idempotency_key",
            name="uq_partner_commissions_idempotency",
        ),
        Index("ix_partner_commissions_partner_status", "partner_id", "status"),
        Index("ix_partner_commissions_status_payable", "status", "payable_at"),
        Index("ix_partner_commissions_relationship", "relationship_id", "created_at"),
        Index("ix_partner_commissions_period", "partner_id", "period_month"),
        Index("ix_partner_commissions_payout", "payout_id"),
        CheckConstraint(
            "rate_bps BETWEEN 0 AND 10000", name="ck_partner_commissions_rate"
        ),
        CheckConstraint(
            "source_amount_minor >= 0", name="ck_partner_commissions_source_nonneg"
        ),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_customer_relationships.id", ondelete="RESTRICT"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_campaigns.id", ondelete="SET NULL"), nullable=True
    )

    entry_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="commission"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    earning_method: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # ── Money. Integer minor units only. ──
    #: Actual revenue COLLECTED from the customer for this event — taken from
    #: the verified payment, never from a list price.
    source_amount_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    #: Revenue base the rate was applied to (source minus non-commissionable
    #: components such as tax or processing fees).
    commissionable_amount_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Signed commission amount in minor units.
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    #: Human-auditable trace of how amount_minor was derived.
    calculation_basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Source event ──
    #: Stable key derived from the payment/provider reference. Combined with
    #: (partner_id, entry_type) this makes commission creation idempotent.
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="payment"
    )
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    #: YYYY-MM of the revenue event — the settlement grouping key.
    period_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # ── Lifecycle ──
    hold_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: End of the holding period; the hold-release job promotes at/after this.
    payable_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    became_payable_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reversal_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: Set on a reversal row, pointing at the commission it cancels.
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_commissions.id", ondelete="RESTRICT"), nullable=True
    )
    payout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_payouts.id", ondelete="SET NULL"), nullable=True
    )
    settlement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_settlements.id", ondelete="SET NULL"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class PartnerCommissionEvent(UUIDMixin, Base):
    """Append-only audit trail of every commission state transition."""

    __tablename__ = "partner_commission_events"
    __table_args__ = (
        Index(
            "ix_partner_commission_events_commission",
            "commission_id",
            "created_at",
        ),
    )

    commission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_commissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: NULL for automated (background job) transitions.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="system"
    )
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PartnerSettlement(UUIDMixin, TimestampMixin, Base):
    """Monthly close for one partner.

    Produced by the ``commission_monthly_settlement`` job. Freezes the set of
    commissions belonging to a period so that reporting is stable even as
    later reversals arrive (which land in the following period).
    """

    __tablename__ = "partner_settlements"
    __table_args__ = (
        UniqueConstraint(
            "partner_id", "period_month", name="uq_partner_settlements_period"
        ),
        Index("ix_partner_settlements_period_status", "period_month", "status"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    gross_commission_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    reversal_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    adjustment_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    net_commission_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    commission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payout_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_payouts.id", ondelete="SET NULL"), nullable=True
    )
    breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ─────────────────────────────────────────────────────────────────────────
# Payouts
# ─────────────────────────────────────────────────────────────────────────


class PartnerPayoutAccount(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Encrypted payout destination.

    The sensitive payload (account number, bank code, recipient identifiers)
    is stored Fernet-encrypted in ``encrypted_details`` using the platform's
    existing ``encrypt_jsonb``/``decrypt_jsonb`` helpers. Only a masked
    fingerprint is ever returned by the API, and the plaintext is never
    logged.
    """

    __tablename__ = "partner_payout_accounts"
    __table_args__ = (
        Index("ix_partner_payout_accounts_partner", "partner_id", "is_default"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(
        String(40), nullable=False, default="paystack_transfer"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)

    #: Safe-to-display label, e.g. "GTBank ••••4321".
    display_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Last 4 characters only — never the full account number.
    account_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    #: Fernet-encrypted JSON blob. Never returned by any endpoint.
    encrypted_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Provider-side recipient handle (Paystack transfer recipient code).
    provider_recipient_code: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )

    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PartnerPayout(UUIDMixin, TimestampMixin, Base):
    """A payout of payable commissions.

    Idempotency is enforced in the database via ``idempotency_key`` so that a
    retried request or a duplicated job run can never double-pay, regardless
    of whether the Redis-backed middleware was available.
    """

    __tablename__ = "partner_payouts"
    __table_args__ = (
        UniqueConstraint(
            "partner_id", "idempotency_key", name="uq_partner_payouts_idempotency"
        ),
        UniqueConstraint("reference", name="uq_partner_payouts_reference"),
        Index("ix_partner_payouts_partner_status", "partner_id", "status"),
        Index("ix_partner_payouts_status_created", "status", "created_at"),
        CheckConstraint("amount_minor >= 0", name="ck_partner_payouts_amount_nonneg"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payout_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_payout_accounts.id", ondelete="SET NULL"), nullable=True
    )

    #: Internal, unique, human-quotable reference.
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="requested", index=True
    )
    method: Mapped[str] = mapped_column(
        String(40), nullable=False, default="paystack_transfer"
    )

    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    net_amount_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    commission_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_month: Mapped[str | None] = mapped_column(String(7), nullable=True)

    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(60), nullable=True)
    #: Provider response with all sensitive fields stripped before storage.
    provider_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PartnerPayoutItem(UUIDMixin, Base):
    """Join row binding one commission to one payout.

    A unique constraint on ``commission_id`` guarantees a commission can be
    paid at most once.
    """

    __tablename__ = "partner_payout_items"
    __table_args__ = (
        UniqueConstraint("commission_id", name="uq_partner_payout_items_commission"),
        Index("ix_partner_payout_items_payout", "payout_id"),
    )

    payout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_payouts.id", ondelete="CASCADE"), nullable=False
    )
    commission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_commissions.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ─────────────────────────────────────────────────────────────────────────
# Leads & deployment claims
# ─────────────────────────────────────────────────────────────────────────


class PartnerLead(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A lead introduced by a partner (the INTRODUCE earning method).

    The prospect's contact details belong to the platform, not to other
    partners: they are only ever returned to the submitting partner and to
    system admins.
    """

    __tablename__ = "partner_leads"
    __table_args__ = (
        Index("ix_partner_leads_partner_status", "partner_id", "status"),
        Index("ix_partner_leads_email_hash", "contact_email_hash"),
        Index("ix_partner_leads_status_created", "status", "created_at"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="submitted", index=True
    )

    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    #: Lowercased SHA-256 of the email, used for duplicate detection without
    #: exposing addresses across partners.
    contact_email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_title: Mapped[str | None] = mapped_column(String(120), nullable=True)

    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(40), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(80), nullable=True)
    use_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_value_minor: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The partner attested that the prospect agreed to be introduced.
    #: Recorded because an introduction hands a third party's contact
    #: details to the sales team, and that needs a basis.
    consent_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Exclusivity window: while open, another partner cannot claim the same
    #: prospect. Prevents lead-stuffing races.
    exclusive_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    converted_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class PartnerDeploymentClaim(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A claim that the partner deployed/implemented Reliastra for a customer.

    Approval creates a DEPLOY relationship (30%). Claims require evidence and
    human review — this is the highest-rate method, so it is never granted
    automatically.
    """

    __tablename__ = "partner_deployment_claims"
    __table_args__ = (
        Index("ix_partner_deployment_claims_partner_status", "partner_id", "status"),
        Index("ix_partner_deployment_claims_org", "organization_id"),
        Index("ix_partner_deployment_claims_status_created", "status", "created_at"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: The customer organisation the work was performed for.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    #: Free-text identifier when the org is not yet on the platform.
    customer_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="submitted", index=True
    )
    earning_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="deploy"
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    deployed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: Set when the customer confirms the partner's involvement in-app.
    customer_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    customer_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Set once the claim is approved and the earning relationship exists.
    #:
    #: ``partner_customer_relationships`` also points back here (a
    #: relationship records the claim that created it), so these two tables
    #: form a genuine FK cycle. ``use_alter=True`` tells SQLAlchemy and
    #: Alembic to add this constraint with a separate ``ALTER TABLE`` after
    #: both tables exist, which is what makes the schema creatable at all.
    relationship_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "partner_customer_relationships.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_partner_deployment_claims_relationship_id",
        ),
        nullable=True,
    )


class PartnerClaimEvidence(UUIDMixin, TimestampMixin, Base):
    """A piece of evidence supporting a deployment claim."""

    __tablename__ = "partner_claim_evidence"
    __table_args__ = (Index("ix_partner_claim_evidence_claim", "claim_id"),)

    claim_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partner_deployment_claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: Object-storage key when the evidence is an uploaded file.
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


# ─────────────────────────────────────────────────────────────────────────
# Fraud
# ─────────────────────────────────────────────────────────────────────────


class PartnerRiskAssessment(UUIDMixin, Base):
    """Point-in-time risk evaluation produced by the fraud_analysis job.

    Append-only: each run writes a new row so that score movement over time
    is auditable and an admin can see exactly which signals fired when a
    partner's commissions were held.
    """

    __tablename__ = "partner_risk_assessments"
    __table_args__ = (
        Index(
            "ix_partner_risk_assessments_partner_created",
            "partner_id",
            "created_at",
        ),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_partner_risk_score"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    band: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    #: List of {signal, weight, detail} dicts — the full reasoning trace.
    signals: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    triggered_hold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PartnerFraudFlag(UUIDMixin, TimestampMixin, Base):
    """An open question about a partner's activity requiring human judgement.

    A flag is *not* a verdict. Nothing is auto-banned. Flags are resolved by
    an admin choosing an explicit action, and the resolution is recorded.
    """

    __tablename__ = "partner_fraud_flags"
    __table_args__ = (
        Index("ix_partner_fraud_flags_partner_status", "partner_id", "status"),
        Index("ix_partner_fraud_flags_status_created", "status", "created_at"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_risk_assessments.id", ondelete="SET NULL"), nullable=True
    )
    signal: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="open", index=True
    )
    score_at_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    #: Related entities, when the flag is about specific records.
    related_commission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partner_commissions.id", ondelete="SET NULL"), nullable=True
    )
    related_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ─────────────────────────────────────────────────────────────────────────
# Geo
# ─────────────────────────────────────────────────────────────────────────


class GeoIpCache(UUIDMixin, TimestampMixin, Base):
    """Durable cache of IP→country lookups.

    Only country-level data is retained (``country_code``/``country_name``) —
    no city, no coordinates, no ASN. Lookups hit the local MaxMind database;
    this table plus Redis keeps repeat lookups off the disk entirely. No
    external GeoIP call is ever made on the request path.
    """

    __tablename__ = "geo_ip_cache"
    __table_args__ = (
        UniqueConstraint("ip_hash", name="uq_geo_ip_cache_ip_hash"),
        Index("ix_geo_ip_cache_country", "country_code"),
    )

    #: SHA-256 of the IP + salt. The raw IP is never persisted.
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="maxmind")
    looked_up_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PartnerGeoDaily(UUIDMixin, TimestampMixin, Base):
    """Daily per-country rollup, written by the ``geo_aggregation`` job.

    ``partner_id`` NULL means the platform-wide row for that day/country,
    which powers the admin geo endpoints without scanning raw click events.
    """

    __tablename__ = "partner_geo_daily"
    __table_args__ = (
        UniqueConstraint(
            "day",
            "country_code",
            "partner_id",
            name="uq_partner_geo_daily_day_country_partner",
        ),
        Index("ix_partner_geo_daily_day", "day"),
        Index("ix_partner_geo_daily_partner_day", "partner_id", "day"),
    )

    day: Mapped[date] = mapped_column(Date, nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    country_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partners.id", ondelete="CASCADE"), nullable=True
    )

    click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unique_visitor_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    signup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conversion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    commission_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")


# ─────────────────────────────────────────────────────────────────────────
# Partner-facing content managed by the backend
# ─────────────────────────────────────────────────────────────────────────


class PartnerProgramContent(UUIDMixin, TimestampMixin, Base):
    """Backend-managed marketing/program copy.

    Program terms, tier benefit descriptions, FAQ entries and onboarding copy
    live here rather than being hardcoded in a client, so they can be updated
    without a deploy and are served from ``/v1/public/partner-program``.
    """

    __tablename__ = "partner_program_content"
    __table_args__ = (
        UniqueConstraint("key", "locale", name="uq_partner_program_content_key_locale"),
        Index("ix_partner_program_content_section", "section", "sort_order"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    section: Mapped[str] = mapped_column(String(60), nullable=False, default="general")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


__all__ = [
    "Partner",
    "PartnerApplication",
    "PartnerTierHistory",
    "PartnerCampaign",
    "PartnerReferralLink",
    "PartnerClickEvent",
    "PartnerAttribution",
    "PartnerCustomerRelationship",
    "PartnerCommission",
    "PartnerCommissionEvent",
    "PartnerSettlement",
    "PartnerPayoutAccount",
    "PartnerPayout",
    "PartnerPayoutItem",
    "PartnerLead",
    "PartnerDeploymentClaim",
    "PartnerClaimEvidence",
    "PartnerRiskAssessment",
    "PartnerFraudFlag",
    "GeoIpCache",
    "PartnerGeoDaily",
    "PartnerProgramContent",
]
