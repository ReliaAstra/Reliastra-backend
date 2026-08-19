"""Pydantic schemas for the Partner Network API.

Conventions carried over from the rest of the platform:

* ``model_config = ConfigDict(from_attributes=True)`` on response models.
* Errors use the platform-wide ``{"error": {...}}`` envelope produced by
  :mod:`app.core.exceptions` — no bespoke error shapes are defined here.
* List endpoints return :class:`app.core.pagination.OffsetPagination`.

Security conventions:

* No request model accepts ``partner_id``, ``campaign_id`` or any other
  ownership identifier from the client. Ownership is always derived
  server-side from the authenticated principal.
* Payout account details are write-only: the response models expose only a
  masked label and the last four characters.
* Referred-customer emails are masked by default at every tier.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.partners.constants import (
    MAX_UTM_VALUE_LENGTH,
    ApplicationStatus,
    CampaignStatus,
    ClaimStatus,
    EarningMethod,
    EvidenceType,
    FlagResolution,
    FlagStatus,
    LeadStatus,
    LinkStatus,
    PartnerTier,
    PartnerType,
    PayoutMethod,
    ReversalReason,
)

_SAFE_PATH = re.compile(r"^/[A-Za-z0-9\-._~/?#\[\]@!$&'()*+,;=%]*$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_destination_path(value: str | None) -> str | None:
    """Only same-origin relative paths are accepted as link destinations.

    Accepting an absolute URL here would turn every partner link into an
    open redirect, so anything that is not a leading-slash relative path is
    rejected outright.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if value.startswith("//") or "://" in value:
        raise ValueError("destination_path must be a relative path, not a URL")
    if not _SAFE_PATH.match(value):
        raise ValueError("destination_path must start with '/' and be URL-safe")
    if len(value) > 500:
        raise ValueError("destination_path is too long")
    return value


# ═════════════════════════════ Applications ══════════════════════════════


class PartnerApplicationCreate(BaseModel):
    """Submit an application to join the partner network."""

    partner_type: PartnerType
    display_name: str = Field(min_length=2, max_length=160)
    legal_name: str | None = Field(default=None, max_length=200)
    contact_email: EmailStr
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    website_url: str | None = Field(default=None, max_length=500)
    intended_methods: list[EarningMethod] = Field(default_factory=list)
    audience_description: str | None = Field(default=None, max_length=4000)
    estimated_monthly_reach: int | None = Field(default=None, ge=0, le=1_000_000_000)
    experience: str | None = Field(default=None, max_length=4000)
    motivation: str | None = Field(default=None, max_length=4000)
    answers: dict | None = None
    agreement_version: str | None = Field(default=None, max_length=30)
    accept_agreement: bool = Field(
        default=False,
        description="Applicant confirms acceptance of the partner agreement.",
    )

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PartnerApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ApplicationStatus
    partner_type: PartnerType
    display_name: str
    contact_email: str
    country_code: str | None = None
    website_url: str | None = None
    intended_methods: list[str] | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    rejection_reason: str | None = None
    partner_id: uuid.UUID | None = None
    created_at: datetime


class PartnerApplicationAdminItem(PartnerApplicationResponse):
    """Admin view adds reviewer bookkeeping and applicant identity."""

    user_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    audience_description: str | None = None
    estimated_monthly_reach: int | None = None
    experience: str | None = None
    motivation: str | None = None
    reviewed_by_id: uuid.UUID | None = None


class PartnerApplicationReviewRequest(BaseModel):
    approve: bool
    tier: PartnerTier | None = Field(
        default=None,
        description="Starting tier on approval. Defaults to 'explorer'.",
    )
    review_notes: str | None = Field(default=None, max_length=4000)
    rejection_reason: str | None = Field(default=None, max_length=4000)


# ══════════════════════════════ Partner ══════════════════════════════════


class PartnerProfileUpdate(BaseModel):
    """Fields a partner may edit on their own profile.

    Deliberately excludes tier, status, rates, risk score and every other
    field that would let a partner grant themselves economics or standing.
    """

    display_name: str | None = Field(default=None, min_length=2, max_length=160)
    headline: str | None = Field(default=None, max_length=255)
    bio: str | None = Field(default=None, max_length=8000)
    website_url: str | None = Field(default=None, max_length=500)
    logo_url: str | None = Field(default=None, max_length=500)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    expertise: list[str] | None = Field(default=None, max_length=25)
    languages: list[str] | None = Field(default=None, max_length=25)
    is_publicly_listed: bool | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PartnerCapabilities(BaseModel):
    tier: PartnerTier
    capabilities: list[str]
    next_tier: PartnerTier | None = None
    next_tier_requirements: dict | None = None


class PartnerResponse(BaseModel):
    """The partner's own view of their account."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partner_code: str
    slug: str
    display_name: str
    legal_name: str | None = None
    partner_type: PartnerType
    tier: PartnerTier
    status: str
    headline: str | None = None
    bio: str | None = None
    website_url: str | None = None
    logo_url: str | None = None
    country_code: str | None = None
    expertise: list[str] | None = None
    languages: list[str] | None = None
    is_publicly_listed: bool
    contact_email: str | None = None
    payout_currency: str
    referral_url: str | None = Field(
        default=None, description="Canonical https://<public-url>/r/{partner_code}"
    )
    lifetime_revenue_minor: int
    lifetime_commission_minor: int
    active_customer_count: int
    total_click_count: int
    total_signup_count: int
    agreement_accepted_at: datetime | None = None
    approved_at: datetime | None = None
    created_at: datetime


class PartnerAdminItem(PartnerResponse):
    """Admin view adds risk and lifecycle fields never shown to the partner."""

    user_id: uuid.UUID
    organization_id: uuid.UUID | None = None
    risk_score: int
    risk_band: str
    risk_evaluated_at: datetime | None = None
    commissions_held: bool
    suspended_at: datetime | None = None
    suspension_reason: str | None = None
    terminated_at: datetime | None = None
    custom_rate_bps: dict | None = None
    notes: str | None = None


class PartnerPublicResponse(BaseModel):
    """Public directory profile. Contains no contact or financial data."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    partner_type: PartnerType
    tier: PartnerTier
    headline: str | None = None
    bio: str | None = None
    website_url: str | None = None
    logo_url: str | None = None
    country_code: str | None = None
    expertise: list[str] | None = None
    languages: list[str] | None = None
    member_since: date | None = None


class PartnerStatusUpdateRequest(BaseModel):
    status: str = Field(description="active | suspended | terminated")
    reason: str | None = Field(default=None, max_length=2000)


class PartnerTierUpdateRequest(BaseModel):
    tier: PartnerTier
    reason: str = Field(min_length=3, max_length=500)


class PartnerRateUpdateRequest(BaseModel):
    """Negotiated per-method rates. Always clamped to the global ceiling."""

    custom_rate_bps: dict[EarningMethod, int] = Field(
        description="Earning method → rate in basis points (max 10000)."
    )
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("custom_rate_bps")
    @classmethod
    def _bounded(cls, v: dict) -> dict:
        for method, bps in v.items():
            if not isinstance(bps, int) or bps < 0 or bps > 10_000:
                raise ValueError(f"rate for {method} must be an int in 0..10000")
        return v


class PartnerTierHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_tier: str | None = None
    to_tier: str
    reason: str
    is_automatic: bool
    metrics_snapshot: dict | None = None
    created_at: datetime


# ══════════════════════════ Campaigns & links ════════════════════════════


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    campaign_code: str | None = Field(
        default=None,
        min_length=3,
        max_length=32,
        description="Optional custom code. Generated when omitted.",
    )
    destination_path: str | None = Field(default=None, max_length=500)
    default_utm: dict[str, str] | None = None
    channel: str | None = Field(default=None, max_length=60)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("campaign_code")
    @classmethod
    def _code_shape(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-_]{1,30}[A-Z0-9]", v):
            raise ValueError(
                "campaign_code must be alphanumeric with - or _ separators"
            )
        return v

    @field_validator("destination_path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        return _validate_destination_path(v)

    @field_validator("default_utm")
    @classmethod
    def _utm(cls, v: dict | None) -> dict | None:
        return _validate_utm(v)


def _validate_utm(v: dict | None) -> dict | None:
    if not v:
        return None
    allowed = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
    cleaned: dict[str, str] = {}
    for key, value in v.items():
        if key not in allowed:
            raise ValueError(f"unsupported utm parameter: {key}")
        if value is None:
            continue
        text = str(value).strip()
        if len(text) > MAX_UTM_VALUE_LENGTH:
            raise ValueError(f"{key} exceeds {MAX_UTM_VALUE_LENGTH} characters")
        cleaned[key] = text
    return cleaned or None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    status: CampaignStatus | None = None
    destination_path: str | None = Field(default=None, max_length=500)
    default_utm: dict[str, str] | None = None
    channel: str | None = Field(default=None, max_length=60)
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("destination_path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        return _validate_destination_path(v)

    @field_validator("default_utm")
    @classmethod
    def _utm(cls, v: dict | None) -> dict | None:
        return _validate_utm(v)


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_code: str
    name: str
    description: str | None = None
    status: CampaignStatus
    destination_path: str | None = None
    default_utm: dict | None = None
    channel: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    referral_url: str | None = None
    click_count: int
    unique_visitor_count: int
    signup_count: int
    conversion_count: int
    attributed_revenue_minor: int
    created_at: datetime


class ReferralLinkCreate(BaseModel):
    label: str | None = Field(default=None, max_length=160)
    campaign_id: uuid.UUID | None = Field(
        default=None,
        description="Must be a campaign owned by the authenticated partner.",
    )
    destination_path: str | None = Field(default=None, max_length=500)
    utm: dict[str, str] | None = None
    expires_at: datetime | None = None

    @field_validator("destination_path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        return _validate_destination_path(v)

    @field_validator("utm")
    @classmethod
    def _utm_v(cls, v: dict | None) -> dict | None:
        return _validate_utm(v)


class ReferralLinkUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=160)
    status: LinkStatus | None = None
    destination_path: str | None = Field(default=None, max_length=500)
    utm: dict[str, str] | None = None
    expires_at: datetime | None = None

    @field_validator("destination_path")
    @classmethod
    def _path(cls, v: str | None) -> str | None:
        return _validate_destination_path(v)

    @field_validator("utm")
    @classmethod
    def _utm_v(cls, v: dict | None) -> dict | None:
        return _validate_utm(v)


class ReferralLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    link_token: str
    label: str | None = None
    status: LinkStatus
    is_default: bool
    campaign_id: uuid.UUID | None = None
    campaign_code: str | None = None
    destination_path: str | None = None
    utm: dict | None = None
    url: str = Field(description="Fully-built shareable URL.")
    short_url: str | None = None
    qr_payload: str | None = Field(
        default=None, description="Value to encode in a QR code (the URL)."
    )
    click_count: int
    unique_visitor_count: int
    signup_count: int
    last_clicked_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


# ═══════════════════════════ Public resolution ═══════════════════════════


class ReferralResolveResponse(BaseModel):
    """Response for ``GET /v1/public/referral/{partner_code}``.

    Returns the data a client needs to complete the redirect and to persist
    attribution. Contains no partner PII beyond the public display name.
    """

    partner_code: str
    partner_display_name: str
    partner_slug: str
    campaign_code: str | None = None
    destination_path: str
    visitor_id: str = Field(
        description="Anonymous first-party visitor id to store and replay at signup."
    )
    attribution_expires_at: datetime
    attribution_window_days: int
    is_valid: bool = True


class ReferralValidateResponse(BaseModel):
    """Lightweight validity probe used by signup forms."""

    partner_code: str
    is_valid: bool
    partner_display_name: str | None = None
    campaign_code: str | None = None
    reason: str | None = None


class PartnerProgramContentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    section: str
    locale: str
    title: str | None = None
    body: str | None = None
    payload: dict | None = None
    sort_order: int
    version: str | None = None


class PartnerProgramResponse(BaseModel):
    """Backend-managed program copy + the live economics.

    Rates are served from configuration so that no client ever hardcodes the
    commission structure. ``landing`` is the public /partners page contract.
    """

    tiers: list[dict]
    earning_methods: list[dict]
    attribution_window_days: int
    commission_hold_days: int
    min_payout_minor: int
    currency: str
    max_total_commission_bps: int
    content: list[PartnerProgramContentItem]
    landing: dict = Field(default_factory=dict)


class PartnerResourceItem(BaseModel):
    id: str
    title: str
    kind: str
    available: bool
    body: str | None = None
    href: str | None = None


class PartnerResourceCenterResponse(BaseModel):
    """Partner resource catalog. Missing files are marked unavailable."""

    items: list[PartnerResourceItem]
    referral_url: str | None = None


# ═════════════════════════════ Analytics ═════════════════════════════════


class PartnerDashboardResponse(BaseModel):
    partner_id: uuid.UUID
    partner_code: str
    tier: PartnerTier
    status: str
    referral_url: str
    currency: str

    clicks_30d: int
    signups_30d: int
    conversions_30d: int
    active_customers: int

    pending_commission_minor: int
    held_commission_minor: int
    payable_commission_minor: int
    paid_commission_minor: int
    reversed_commission_minor: int
    lifetime_commission_minor: int
    lifetime_revenue_minor: int

    next_payout_eligible: bool
    min_payout_minor: int
    open_leads: int
    pending_claims: int


class TimeseriesPoint(BaseModel):
    day: date
    clicks: int = 0
    unique_visitors: int = 0
    signups: int = 0
    conversions: int = 0
    revenue_minor: int = 0
    commission_minor: int = 0


class PartnerAnalyticsResponse(BaseModel):
    from_date: date
    to_date: date
    currency: str
    totals: TimeseriesPoint
    series: list[TimeseriesPoint]
    by_campaign: list[dict] = Field(default_factory=list)
    by_country: list[dict] = Field(default_factory=list)


class ReferredCustomerItem(BaseModel):
    """A customer attributed to the partner.

    The customer's email is **masked at every tier**. Partners see enough to
    recognise their own referral and to support it, never enough to contact
    or export the platform's customer base.
    """

    relationship_id: uuid.UUID
    organization_name: str | None = None
    masked_email: str | None = None
    country_code: str | None = None
    earning_method: EarningMethod
    status: str
    plan: str | None = None
    started_at: datetime
    eligible_until: datetime | None = None
    total_revenue_minor: int
    total_commission_minor: int
    currency: str


# ════════════════════════════ Commissions ════════════════════════════════


class CommissionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entry_type: str
    status: str
    earning_method: str | None = None
    amount_minor: int
    currency: str
    rate_bps: int
    source_amount_minor: int
    commissionable_amount_minor: int
    period_month: str | None = None
    earned_at: datetime
    payable_at: datetime | None = None
    became_payable_at: datetime | None = None
    paid_at: datetime | None = None
    reversed_at: datetime | None = None
    reversal_reason: str | None = None
    hold_reason: str | None = None
    organization_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None
    reverses_id: uuid.UUID | None = None
    payout_id: uuid.UUID | None = None
    created_at: datetime


class CommissionAdminItem(CommissionItem):
    partner_id: uuid.UUID
    relationship_id: uuid.UUID | None = None
    idempotency_key: str
    source_type: str
    source_reference: str | None = None
    calculation_basis: dict | None = None
    notes: str | None = None


class CommissionBalanceResponse(BaseModel):
    currency: str
    pending_minor: int
    held_minor: int
    payable_minor: int
    paid_minor: int
    reversed_minor: int
    lifetime_minor: int
    min_payout_minor: int
    can_request_payout: bool
    next_release_at: datetime | None = None


class CommissionEventItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_status: str | None = None
    to_status: str
    reason: str | None = None
    actor_type: str
    actor_user_id: uuid.UUID | None = None
    context: dict | None = None
    created_at: datetime


class CommissionAdjustmentRequest(BaseModel):
    """Manual admin correction. Always creates a new ledger row."""

    amount_minor: int = Field(
        description="Signed minor units. Negative reduces the partner balance."
    )
    currency: str = Field(default="USD", min_length=3, max_length=3)
    reason: str = Field(min_length=5, max_length=1000)
    partner_id: uuid.UUID
    organization_id: uuid.UUID | None = None


class CommissionReversalRequest(BaseModel):
    reason: ReversalReason
    refunded_minor: int | None = Field(
        default=None,
        ge=0,
        description="Partial refund amount; omit for a full reversal.",
    )
    notes: str | None = Field(default=None, max_length=2000)


class SettlementItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partner_id: uuid.UUID
    period_month: str
    status: str
    currency: str
    gross_commission_minor: int
    reversal_minor: int
    adjustment_minor: int
    net_commission_minor: int
    commission_count: int
    revenue_minor: int
    closed_at: datetime | None = None
    payout_id: uuid.UUID | None = None


# ══════════════════════════════ Payouts ══════════════════════════════════


class PayoutAccountCreate(BaseModel):
    """Write-only payout details.

    The whole ``details`` blob is encrypted at rest with the platform Fernet
    key and is never returned by any endpoint or written to a log.
    """

    method: PayoutMethod = PayoutMethod.PAYSTACK_TRANSFER
    currency: str = Field(default="USD", min_length=3, max_length=3)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    bank_name: str | None = Field(default=None, max_length=120)
    account_name: str = Field(min_length=2, max_length=160)
    account_number: str = Field(min_length=4, max_length=64)
    bank_code: str | None = Field(default=None, max_length=32)
    details: dict | None = Field(
        default=None, description="Additional provider-specific fields."
    )
    set_default: bool = True

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return v.upper()


class PayoutAccountResponse(BaseModel):
    """Masked representation. Full account data is never exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    method: PayoutMethod
    currency: str
    country_code: str | None = None
    bank_name: str | None = None
    display_label: str | None = None
    account_last4: str | None = None
    is_default: bool
    is_verified: bool
    verified_at: datetime | None = None
    created_at: datetime


class PayoutRequestCreate(BaseModel):
    """Request a payout of the currently payable balance.

    The amount is computed server-side from the ledger; a client cannot ask
    for an arbitrary sum.
    """

    payout_account_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the partner's default account."
    )
    notes: str | None = Field(default=None, max_length=1000)


class PayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reference: str
    status: str
    method: str
    amount_minor: int
    fee_minor: int
    net_amount_minor: int
    currency: str
    commission_count: int
    period_month: str | None = None
    requested_at: datetime
    approved_at: datetime | None = None
    processed_at: datetime | None = None
    paid_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime


class PayoutAdminItem(PayoutResponse):
    partner_id: uuid.UUID
    payout_account_id: uuid.UUID | None = None
    provider: str | None = None
    provider_reference: str | None = None
    provider_status: str | None = None
    approved_by_id: uuid.UUID | None = None
    notes: str | None = None


class PayoutActionRequest(BaseModel):
    action: str = Field(description="approve | process | mark_paid | fail | cancel")
    reason: str | None = Field(default=None, max_length=2000)
    provider_reference: str | None = Field(default=None, max_length=200)


# ═══════════════════════════════ Leads ═══════════════════════════════════


class LeadCreate(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=160)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_title: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    company_size: str | None = Field(default=None, max_length=40)
    industry: str | None = Field(default=None, max_length=80)
    use_case: str | None = Field(default=None, max_length=4000)
    estimated_value_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    notes: str | None = Field(default=None, max_length=4000)
    consent_confirmed: bool = Field(
        default=False,
        description="Partner confirms the prospect consented to the introduction.",
    )

    @field_validator("country_code")
    @classmethod
    def _upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: LeadStatus
    company_name: str
    contact_name: str
    masked_contact_email: str | None = None
    country_code: str | None = None
    industry: str | None = None
    company_size: str | None = None
    estimated_value_minor: int | None = None
    currency: str
    exclusive_until: datetime | None = None
    accepted_at: datetime | None = None
    contacted_at: datetime | None = None
    qualified_at: datetime | None = None
    converted_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime


class LeadAdminItem(LeadResponse):
    """Admins see the real contact details; partners never see other
    partners' leads at all."""

    partner_id: uuid.UUID
    contact_email: str
    contact_phone: str | None = None
    contact_title: str | None = None
    use_case: str | None = None
    notes: str | None = None
    converted_organization_id: uuid.UUID | None = None


class LeadStatusUpdateRequest(BaseModel):
    status: LeadStatus
    reason: str | None = Field(default=None, max_length=2000)
    converted_organization_id: uuid.UUID | None = Field(
        default=None,
        description="Required when transitioning to 'converted'.",
    )


# ═════════════════════════ Deployment claims ═════════════════════════════


class ClaimEvidenceCreate(BaseModel):
    evidence_type: EvidenceType
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    url: str | None = Field(default=None, max_length=1000)
    storage_key: str | None = Field(default=None, max_length=500)


class ClaimEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    evidence_type: EvidenceType
    title: str | None = None
    description: str | None = None
    url: str | None = None
    storage_key: str | None = None
    created_at: datetime


class DeploymentClaimCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=20, max_length=8000)
    organization_id: uuid.UUID | None = Field(
        default=None, description="Customer organisation, if already on-platform."
    )
    customer_identifier: str | None = Field(default=None, max_length=255)
    earning_method: EarningMethod = EarningMethod.DEPLOY
    deployed_at: datetime | None = None
    evidence: list[ClaimEvidenceCreate] = Field(
        default_factory=list,
        max_length=20,
        description="At least one item is required to submit a claim.",
    )


class DeploymentClaimResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ClaimStatus
    title: str
    description: str
    earning_method: EarningMethod
    organization_id: uuid.UUID | None = None
    customer_identifier: str | None = None
    deployed_at: datetime | None = None
    customer_confirmed: bool
    reviewed_at: datetime | None = None
    review_notes: str | None = None
    rejection_reason: str | None = None
    relationship_id: uuid.UUID | None = None
    evidence: list[ClaimEvidenceResponse] = Field(default_factory=list)
    created_at: datetime


class DeploymentClaimAdminItem(DeploymentClaimResponse):
    partner_id: uuid.UUID
    reviewed_by_id: uuid.UUID | None = None


class ClaimReviewRequest(BaseModel):
    approve: bool
    review_notes: str | None = Field(default=None, max_length=4000)
    rejection_reason: str | None = Field(default=None, max_length=4000)
    rate_bps_override: int | None = Field(
        default=None,
        ge=0,
        le=10_000,
        description="Override the DEPLOY rate for this relationship.",
    )


# ═══════════════════════════════ Fraud ═══════════════════════════════════


class RiskAssessmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partner_id: uuid.UUID
    score: int
    band: str
    signals: list | None = None
    metrics: dict | None = None
    triggered_hold: bool
    created_at: datetime


class FraudFlagItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    partner_id: uuid.UUID
    signal: str
    severity: str
    status: FlagStatus
    score_at_flag: int
    summary: str
    evidence: dict | None = None
    related_commission_id: uuid.UUID | None = None
    related_organization_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolved_by_id: uuid.UUID | None = None
    resolution: FlagResolution | None = None
    resolution_notes: str | None = None
    created_at: datetime


class FraudFlagResolveRequest(BaseModel):
    """Resolve a flag with an explicit, recorded action.

    Nothing here is automatic: a human chooses the outcome, and both the
    choice and the reasoning are persisted.
    """

    status: FlagStatus
    resolution: FlagResolution
    notes: str = Field(min_length=5, max_length=4000)


# ════════════════════════════════ Geo ════════════════════════════════════


class CountryStatsItem(BaseModel):
    country_code: str
    country_name: str | None = None
    clicks: int = 0
    unique_visitors: int = 0
    signups: int = 0
    conversions: int = 0
    revenue_minor: int = 0
    commission_minor: int = 0
    currency: str = "USD"


class GeoAnalyticsResponse(BaseModel):
    from_date: date
    to_date: date
    currency: str
    total_countries: int
    countries: list[CountryStatsItem]


class GeoCoverageResponse(BaseModel):
    """Operational view of the local MaxMind database."""

    database_available: bool
    database_path: str
    database_build_epoch: int | None = None
    database_age_days: int | None = None
    cached_lookups: int
    resolved_countries: int
    unresolved_lookups: int


__all__ = [name for name in dir() if name[0].isupper()]
