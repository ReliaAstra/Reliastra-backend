"""Domain constants and enumerations for the Partner Network.

Everything money-related in this package is expressed in **integer minor
units** (cents for USD) together with an explicit ISO-4217 currency code.
Floats are never used for money. Commission *rates* are expressed in basis
points (bps) so that rate arithmetic also stays in integers:

    1 bps = 0.01%      100 bps = 1%      10_000 bps = 100%

Business economics (the actual rates, the ceiling, the hold period, the
payout threshold) live in :mod:`app.config` and are only *named* here.
"""

from __future__ import annotations

from enum import Enum

BPS_DENOMINATOR = 10_000


class StrEnum(str, Enum):
    """Small back-port so values serialise as plain strings in JSON/DB."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


# ─────────────────────────── Partner identity ────────────────────────────


class PartnerType(StrEnum):
    """What kind of organisation/person the partner is."""

    INDIVIDUAL = "individual"
    CONSULTANT = "consultant"
    AGENCY = "agency"
    SYSTEM_INTEGRATOR = "system_integrator"
    TECHNOLOGY_PARTNER = "technology_partner"
    RESELLER = "reseller"
    COMMUNITY = "community"
    EDUCATIONAL = "educational"
    NONPROFIT = "nonprofit"


class PartnerTier(StrEnum):
    """Progression ladder. Tier is *earned*, never self-selected."""

    EXPLORER = "explorer"
    PARTNER = "partner"
    CERTIFIED = "certified"
    AGENCY = "agency"
    STRATEGIC = "strategic"


#: Ordering used for promotion/demotion comparisons.
TIER_ORDER: dict[str, int] = {
    PartnerTier.EXPLORER.value: 0,
    PartnerTier.PARTNER.value: 1,
    PartnerTier.CERTIFIED.value: 2,
    PartnerTier.AGENCY.value: 3,
    PartnerTier.STRATEGIC.value: 4,
}

#: Objective, auditable promotion thresholds evaluated by the
#: ``partner_tier_evaluation`` background job. A partner is promoted to the
#: highest tier whose thresholds they satisfy; they are never auto-demoted
#: below ``PARTNER`` (manual admin action only), which keeps the ladder from
#: flapping around month boundaries.
TIER_REQUIREMENTS: dict[str, dict[str, int]] = {
    PartnerTier.EXPLORER.value: {
        "min_active_customers": 0,
        "min_lifetime_revenue_minor": 0,
    },
    PartnerTier.PARTNER.value: {
        "min_active_customers": 1,
        "min_lifetime_revenue_minor": 0,
    },
    PartnerTier.CERTIFIED.value: {
        "min_active_customers": 5,
        "min_lifetime_revenue_minor": 100_000,  # $1,000.00
    },
    PartnerTier.AGENCY.value: {
        "min_active_customers": 15,
        "min_lifetime_revenue_minor": 500_000,  # $5,000.00
    },
    PartnerTier.STRATEGIC.value: {
        "min_active_customers": 40,
        "min_lifetime_revenue_minor": 2_500_000,  # $25,000.00
    },
}

#: Tier is *not* a commission multiplier — the earning method determines the
#: rate. Tier unlocks capabilities instead, which keeps the economics simple
#: and prevents rate stacking from breaching the ceiling.
TIER_CAPABILITIES: dict[str, list[str]] = {
    PartnerTier.EXPLORER.value: [
        "referral_link",
        "basic_analytics",
    ],
    PartnerTier.PARTNER.value: [
        "referral_link",
        "basic_analytics",
        "campaigns",
        "payouts",
    ],
    PartnerTier.CERTIFIED.value: [
        "referral_link",
        "basic_analytics",
        "campaigns",
        "payouts",
        "deployment_claims",
        "lead_introductions",
        "public_directory_listing",
    ],
    PartnerTier.AGENCY.value: [
        "referral_link",
        "basic_analytics",
        "campaigns",
        "payouts",
        "deployment_claims",
        "lead_introductions",
        "public_directory_listing",
        "managed_clients",
        "co_marketing",
    ],
    PartnerTier.STRATEGIC.value: [
        "referral_link",
        "basic_analytics",
        "campaigns",
        "payouts",
        "deployment_claims",
        "lead_introductions",
        "public_directory_listing",
        "managed_clients",
        "co_marketing",
        "custom_terms",
        "dedicated_support",
    ],
}


class PartnerStatus(StrEnum):
    """Lifecycle of the partner record itself."""

    PENDING = "pending"          # application submitted, awaiting review
    ACTIVE = "active"            # approved and able to earn
    SUSPENDED = "suspended"      # temporarily blocked (fraud review, breach)
    TERMINATED = "terminated"    # permanently ended
    REJECTED = "rejected"        # application declined


#: Statuses in which a partner may accrue new commissions.
EARNING_STATUSES: frozenset[str] = frozenset({PartnerStatus.ACTIVE.value})


class ApplicationStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# ─────────────────────────── Earning methods ─────────────────────────────


class EarningMethod(StrEnum):
    """How a partner earned the right to a commission.

    The method — not the tier — determines the rate:

    ``REFER``      20%  recurring, partner sends a customer
    ``DEPLOY``     30%  recurring, partner implements/operates for the customer
    ``CREATE``     25%  recurring, partner produced the content/integration
    ``INTRODUCE``  15%  Year-1 only, one relationship introduction
    ``RESELL``      0%  reseller keeps the wholesale margin instead
    """

    REFER = "refer"
    DEPLOY = "deploy"
    CREATE = "create"
    INTRODUCE = "introduce"
    RESELL = "resell"


#: Methods whose commission accrues on every collected payment, forever
#: (as long as the relationship stays active).
RECURRING_METHODS: frozenset[str] = frozenset(
    {
        EarningMethod.REFER.value,
        EarningMethod.DEPLOY.value,
        EarningMethod.CREATE.value,
    }
)

#: Methods bounded by the Year-1 window.
YEAR_ONE_METHODS: frozenset[str] = frozenset({EarningMethod.INTRODUCE.value})

#: Methods that never produce a platform commission ledger entry with a
#: non-zero amount. Resellers are compensated through wholesale pricing.
ZERO_COMMISSION_METHODS: frozenset[str] = frozenset({EarningMethod.RESELL.value})


# ───────────────────────── Referral / attribution ────────────────────────


class LinkStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class AttributionModel(StrEnum):
    """v1 ships ``LAST_TOUCH`` only; the column exists so that multi-touch
    models can be introduced without a schema migration or a rewrite of the
    attribution records already on disk."""

    LAST_TOUCH = "last_touch"
    FIRST_TOUCH = "first_touch"
    LINEAR = "linear"
    POSITION_BASED = "position_based"


class AttributionStatus(StrEnum):
    ACTIVE = "active"        # currently the owning touch
    EXPIRED = "expired"      # window elapsed before conversion
    SUPERSEDED = "superseded"  # a later eligible touch took ownership
    VOIDED = "voided"        # invalidated (fraud, admin action)


class TouchpointType(StrEnum):
    CLICK = "click"
    SIGNUP = "signup"
    ACTIVATION = "activation"
    CONVERSION = "conversion"


# ──────────────────────────── Relationships ──────────────────────────────


class RelationshipStatus(StrEnum):
    """State of the partner↔customer earning relationship."""

    ACTIVE = "active"
    CHURNED = "churned"
    EXPIRED = "expired"      # Year-1 window elapsed (introduce)
    REVOKED = "revoked"      # admin/fraud


# ───────────────────────────── Commissions ───────────────────────────────


class CommissionStatus(StrEnum):
    """Immutable-ledger states.

    Legal transitions (enforced in the service layer, audited on every hop):

        pending  → payable | held | reversed
        held     → payable | reversed
        payable  → paid    | reversed
        paid     → reversed          (clawback via a compensating entry)
        reversed → (terminal)
    """

    PENDING = "pending"
    HELD = "held"
    PAYABLE = "payable"
    PAID = "paid"
    REVERSED = "reversed"


#: Allowed state transitions for commission ledger entries.
COMMISSION_TRANSITIONS: dict[str, frozenset[str]] = {
    CommissionStatus.PENDING.value: frozenset(
        {
            CommissionStatus.PAYABLE.value,
            CommissionStatus.HELD.value,
            CommissionStatus.REVERSED.value,
        }
    ),
    CommissionStatus.HELD.value: frozenset(
        {
            # Hold lifted after the holding period had already elapsed.
            CommissionStatus.PAYABLE.value,
            # Hold lifted early: the entry resumes its normal holding period.
            CommissionStatus.PENDING.value,
            CommissionStatus.REVERSED.value,
        }
    ),
    CommissionStatus.PAYABLE.value: frozenset(
        {
            CommissionStatus.PAID.value,
            CommissionStatus.REVERSED.value,
        }
    ),
    CommissionStatus.PAID.value: frozenset({CommissionStatus.REVERSED.value}),
    CommissionStatus.REVERSED.value: frozenset(),
}


class LedgerEntryType(StrEnum):
    """Every row in the ledger is one of these. Corrections are always new
    rows — history is never rewritten."""

    COMMISSION = "commission"          # positive accrual
    REVERSAL = "reversal"              # negative, cancels a COMMISSION
    ADJUSTMENT = "adjustment"          # manual admin correction (+/-)
    PAYOUT = "payout"                  # negative, money left the platform
    PAYOUT_REVERSAL = "payout_reversal"  # failed/returned payout


class ReversalReason(StrEnum):
    REFUND = "refund"
    CHARGEBACK = "chargeback"
    CHURN = "churn"
    FRAUD = "fraud"
    DUPLICATE = "duplicate"
    ADMIN_CORRECTION = "admin_correction"


class HoldReason(StrEnum):
    HOLDING_PERIOD = "holding_period"
    FRAUD_REVIEW = "fraud_review"
    MISSING_PAYOUT_DETAILS = "missing_payout_details"
    PARTNER_SUSPENDED = "partner_suspended"
    TAX_DOCUMENTS = "tax_documents"
    ADMIN_HOLD = "admin_hold"


# ─────────────────────────────── Payouts ─────────────────────────────────


class PayoutStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


PAYOUT_TRANSITIONS: dict[str, frozenset[str]] = {
    PayoutStatus.REQUESTED.value: frozenset(
        {
            PayoutStatus.APPROVED.value,
            PayoutStatus.CANCELLED.value,
            PayoutStatus.FAILED.value,
        }
    ),
    PayoutStatus.APPROVED.value: frozenset(
        {
            PayoutStatus.PROCESSING.value,
            # Manual and bank transfers are settled outside the platform:
            # an operator sends the money and then records it. Forcing them
            # through `processing` would add a step that means nothing for
            # those methods.
            PayoutStatus.PAID.value,
            PayoutStatus.CANCELLED.value,
            PayoutStatus.FAILED.value,
        }
    ),
    PayoutStatus.PROCESSING.value: frozenset(
        {PayoutStatus.PAID.value, PayoutStatus.FAILED.value}
    ),
    PayoutStatus.PAID.value: frozenset(),
    PayoutStatus.FAILED.value: frozenset({PayoutStatus.REQUESTED.value}),
    PayoutStatus.CANCELLED.value: frozenset(),
}


class PayoutMethod(StrEnum):
    PAYSTACK_TRANSFER = "paystack_transfer"
    BANK_TRANSFER = "bank_transfer"
    MANUAL = "manual"


# ──────────────────────────── Leads / claims ─────────────────────────────


class LeadStatus(StrEnum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"
    EXPIRED = "expired"


LEAD_TRANSITIONS: dict[str, frozenset[str]] = {
    LeadStatus.SUBMITTED.value: frozenset(
        {
            LeadStatus.ACCEPTED.value,
            LeadStatus.REJECTED.value,
            LeadStatus.EXPIRED.value,
        }
    ),
    LeadStatus.ACCEPTED.value: frozenset(
        {LeadStatus.CONTACTED.value, LeadStatus.LOST.value, LeadStatus.EXPIRED.value}
    ),
    LeadStatus.CONTACTED.value: frozenset(
        {LeadStatus.QUALIFIED.value, LeadStatus.LOST.value, LeadStatus.EXPIRED.value}
    ),
    LeadStatus.QUALIFIED.value: frozenset(
        {LeadStatus.CONVERTED.value, LeadStatus.LOST.value, LeadStatus.EXPIRED.value}
    ),
    LeadStatus.CONVERTED.value: frozenset(),
    LeadStatus.REJECTED.value: frozenset(),
    LeadStatus.LOST.value: frozenset(),
    LeadStatus.EXPIRED.value: frozenset(),
}

#: Statuses from which a lead can still become a paying relationship.
LEAD_OPEN_STATUSES: frozenset[str] = frozenset(
    {
        LeadStatus.SUBMITTED.value,
        LeadStatus.ACCEPTED.value,
        LeadStatus.CONTACTED.value,
        LeadStatus.QUALIFIED.value,
    }
)


class ClaimStatus(StrEnum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


CLAIM_TRANSITIONS: dict[str, frozenset[str]] = {
    ClaimStatus.SUBMITTED.value: frozenset(
        {
            ClaimStatus.UNDER_REVIEW.value,
            ClaimStatus.APPROVED.value,
            ClaimStatus.REJECTED.value,
            ClaimStatus.WITHDRAWN.value,
        }
    ),
    ClaimStatus.UNDER_REVIEW.value: frozenset(
        {ClaimStatus.APPROVED.value, ClaimStatus.REJECTED.value}
    ),
    ClaimStatus.APPROVED.value: frozenset(),
    ClaimStatus.REJECTED.value: frozenset(),
    ClaimStatus.WITHDRAWN.value: frozenset(),
}


class EvidenceType(StrEnum):
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    URL = "url"
    REPOSITORY = "repository"
    CUSTOMER_CONFIRMATION = "customer_confirmation"
    OTHER = "other"


# ────────────────────────────── Fraud ────────────────────────────────────


class RiskBand(StrEnum):
    LOW = "low"            #  0–29  monitor only
    MEDIUM = "medium"      # 30–59  monitor + soft signals
    HIGH = "high"          # 60–79  hold commissions, manual review
    CRITICAL = "critical"  # 80–100 suspend earning, urgent review


#: Inclusive lower bound → band. Ordered high to low for lookup.
RISK_BANDS: tuple[tuple[int, str], ...] = (
    (80, RiskBand.CRITICAL.value),
    (60, RiskBand.HIGH.value),
    (30, RiskBand.MEDIUM.value),
    (0, RiskBand.LOW.value),
)


def risk_band_for_score(score: int) -> str:
    """Map a 0–100 risk score onto its band."""
    bounded = max(0, min(100, int(score)))
    for lower, band in RISK_BANDS:
        if bounded >= lower:
            return band
    return RiskBand.LOW.value  # pragma: no cover - unreachable


class FraudSignal(StrEnum):
    """Individual weighted signals.

    Deliberately absent: "same IP as referrer". Shared IPs are normal for
    offices, universities, conferences, co-working spaces, mobile carrier
    NAT and VPNs. IP overlap only ever contributes as one weak corroborating
    signal inside ``VELOCITY_ANOMALY`` / ``IDENTITY_CLUSTER``, never on its
    own, and never triggers an automatic ban.
    """

    SELF_REFERRAL = "self_referral"
    VELOCITY_ANOMALY = "velocity_anomaly"
    IDENTITY_CLUSTER = "identity_cluster"
    DISPOSABLE_EMAIL = "disposable_email"
    CLICK_FLOODING = "click_flooding"
    ZERO_ENGAGEMENT_CONVERSIONS = "zero_engagement_conversions"
    PAYMENT_INSTRUMENT_REUSE = "payment_instrument_reuse"
    HIGH_REFUND_RATE = "high_refund_rate"
    CHARGEBACK_HISTORY = "chargeback_history"
    RAPID_CHURN = "rapid_churn"
    GEO_MISMATCH = "geo_mismatch"
    UNVERIFIED_DEPLOYMENT_CLAIM = "unverified_deployment_claim"


#: Signal → weight contributed to the 0–100 score. Weights are additive and
#: the total is clamped to 100. No single behavioural signal can, by itself,
#: push a partner into CRITICAL: only confirmed abuse (self-referral,
#: chargebacks) carries that much weight.
FRAUD_SIGNAL_WEIGHTS: dict[str, int] = {
    FraudSignal.SELF_REFERRAL.value: 45,
    FraudSignal.CHARGEBACK_HISTORY.value: 35,
    FraudSignal.PAYMENT_INSTRUMENT_REUSE.value: 30,
    FraudSignal.HIGH_REFUND_RATE.value: 25,
    FraudSignal.ZERO_ENGAGEMENT_CONVERSIONS.value: 20,
    FraudSignal.RAPID_CHURN.value: 20,
    FraudSignal.IDENTITY_CLUSTER.value: 18,
    FraudSignal.DISPOSABLE_EMAIL.value: 15,
    FraudSignal.VELOCITY_ANOMALY.value: 15,
    FraudSignal.CLICK_FLOODING.value: 10,
    FraudSignal.UNVERIFIED_DEPLOYMENT_CLAIM.value: 10,
    FraudSignal.GEO_MISMATCH.value: 5,
}


class FlagStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED_LEGITIMATE = "resolved_legitimate"
    RESOLVED_FRAUD = "resolved_fraud"
    DISMISSED = "dismissed"


class FlagResolution(StrEnum):
    """Actions an admin may take when resolving a fraud flag."""

    NO_ACTION = "no_action"
    WARN_PARTNER = "warn_partner"
    HOLD_COMMISSIONS = "hold_commissions"
    RELEASE_COMMISSIONS = "release_commissions"
    REVERSE_COMMISSIONS = "reverse_commissions"
    SUSPEND_PARTNER = "suspend_partner"
    TERMINATE_PARTNER = "terminate_partner"


# ──────────────────────────── Misc / limits ──────────────────────────────

#: Character set for generated partner/campaign codes. Excludes look-alike
#: characters (0/O, 1/I/L) so codes survive being read aloud or retyped.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

PARTNER_CODE_LENGTH = 8
CAMPAIGN_CODE_LENGTH = 6
MAX_CAMPAIGNS_PER_PARTNER = 100
MAX_LINKS_PER_CAMPAIGN = 50

#: Reserved codes that must never be handed out — they collide with real
#: routes or are trivially guessable.
RESERVED_CODES: frozenset[str] = frozenset(
    {
        "ADMIN",
        "API",
        "APP",
        "AUTH",
        "BILLING",
        "BLOG",
        "DASHBOARD",
        "DOCS",
        "HELP",
        "LOGIN",
        "PARTNER",
        "PARTNERS",
        "PRICING",
        "PUBLIC",
        "REFERRAL",
        "SETTINGS",
        "SIGNUP",
        "STATUS",
        "SUPPORT",
        "TEST",
        "WWW",
    }
)

#: UTM parameters captured on click. These are *analytics metadata only* —
#: they never determine or override partner ownership of a conversion.
UTM_FIELDS: tuple[str, ...] = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
)

MAX_UTM_VALUE_LENGTH = 255
