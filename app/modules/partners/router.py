"""Partner-facing API — ``/v1/partners/*``.

Every route in this module is scoped to the authenticated user's own
partner account. The partner is resolved server-side from the JWT/API key
(:meth:`PartnerService.get_partner_for_user`); no endpoint accepts a
``partner_id``, ``campaign_id`` owner hint or any other client-supplied
ownership claim.

Conventions followed from the rest of the codebase: ``OffsetPagination`` for
lists, ``AppException`` subclasses for errors (rendered into the standard
``{"error": {...}}`` envelope), and ``Depends(get_db)`` for the
request-scoped session that owns the transaction.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.core.pagination import OffsetPagination
from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.dependencies import get_current_user
from app.modules.partners.commissions import commission_service
from app.modules.partners.constants import ClaimStatus, LeadStatus
from app.modules.partners.payouts import payout_service
from app.modules.partners.repository import (
    CampaignRepository,
    ClaimRepository,
    CommissionRepository,
    LeadRepository,
    PayoutRepository,
    ReferralLinkRepository,
    SettlementRepository,
)
from app.modules.partners.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    ClaimEvidenceResponse,
    CommissionBalanceResponse,
    CommissionEventItem,
    CommissionItem,
    DeploymentClaimCreate,
    DeploymentClaimResponse,
    LeadCreate,
    LeadResponse,
    PartnerAnalyticsResponse,
    PartnerApplicationCreate,
    PartnerApplicationResponse,
    PartnerCapabilities,
    PartnerDashboardResponse,
    PartnerProfileUpdate,
    PartnerResponse,
    PartnerTierHistoryItem,
    PayoutAccountCreate,
    PayoutAccountResponse,
    PayoutRequestCreate,
    PayoutResponse,
    ReferralLinkCreate,
    ReferralLinkResponse,
    ReferralLinkUpdate,
    ReferredCustomerItem,
    SettlementItem,
)
from app.modules.partners.service import partner_service
from app.modules.users.models import User

logger = logging.getLogger(__name__)


async def require_partner_user(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """Authenticate a human partner, never an organization API key.

    ``get_current_user`` resolves an organization API key to that org's
    *owner* user. These routes hang off a user-bound partner identity and
    expose commissions, payout accounts and payout requests, so an org-scoped
    integration key must not reach them: it would let any holder of an API key
    act on the owner's partner earnings.
    """
    if getattr(request.state, "auth_method", None) == "apikey":
        raise ForbiddenException(
            "Organization API keys cannot access partner self-service routes"
        )
    return current_user


partners_router = APIRouter(prefix="/v1/partners", tags=["Partners"])

#: Applying is cheap to abuse and expensive to review.
_application_limiter = SlidingWindowRateLimiter(
    limit=5, window_seconds=3600, key_prefix="partner_apply"
)
#: Payout requests touch money; keep them deliberate.
_payout_limiter = SlidingWindowRateLimiter(
    limit=10, window_seconds=3600, key_prefix="partner_payout"
)
#: Generous ceiling for ordinary authoring traffic.
_write_limiter = SlidingWindowRateLimiter(
    limit=120, window_seconds=60, key_prefix="partner_write"
)


def _pages(total: int, size: int) -> int:
    return (total + size - 1) // size if size else 0


# ═══════════════════════════ Applications ════════════════════════════════


@partners_router.post(
    "/apply",
    response_model=PartnerApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply to the partner network",
    responses={
        409: {"description": "An application is pending or the user is already a partner"},
        422: {"description": "The partner agreement was not accepted"},
    },
)
async def apply_to_partner_network(
    request: Request,
    payload: PartnerApplicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerApplicationResponse:
    """Submit a partner application for review.

    One in-flight application per user. Approval is a manual admin action
    unless ``PARTNER_AUTO_APPROVE_APPLICATIONS`` is enabled.
    """
    await enforce_rate_limit(request, _application_limiter, str(current_user.id))
    application = await partner_service.apply(db, current_user, payload)
    return PartnerApplicationResponse.model_validate(application)


@partners_router.get(
    "/applications",
    response_model=list[PartnerApplicationResponse],
    summary="List my partner applications",
)
async def list_my_applications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> list[PartnerApplicationResponse]:
    """All partner applications submitted by this user, newest first."""
    applications = await partner_service.list_my_applications(db, current_user)
    return [PartnerApplicationResponse.model_validate(a) for a in applications]


# ═════════════════════════════ Profile ═══════════════════════════════════


@partners_router.get(
    "/me",
    response_model=PartnerResponse,
    summary="Get my partner profile",
    responses={404: {"description": "No partner account exists for this user"}},
)
async def get_my_partner_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerResponse:
    """The authenticated user's partner account, including their
    canonical referral URL and lifetime totals.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    return partner_service.to_response(partner)


@partners_router.patch(
    "/me",
    response_model=PartnerResponse,
    summary="Update my partner profile",
)
async def update_my_partner_profile(
    request: Request,
    payload: PartnerProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerResponse:
    """Update editable profile fields.

    Tier, status, rates and risk are not editable here — they are outcomes,
    not inputs.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    partner = await partner_service.update_profile(db, partner, payload)
    return partner_service.to_response(partner)


@partners_router.get(
    "/me/capabilities",
    response_model=PartnerCapabilities,
    summary="Get my tier capabilities and next-tier requirements",
)
async def get_my_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerCapabilities:
    """What the current tier unlocks, plus the requirements for the next
    tier. Tiers grant capabilities only — commission rates are per
    earning method and identical at every tier.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    return partner_service.capabilities(partner)


@partners_router.get(
    "/me/tier-history",
    response_model=list[PartnerTierHistoryItem],
    summary="Get my tier change history",
)
async def get_my_tier_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> list[PartnerTierHistoryItem]:
    """Every tier change on this account, with the reason and whether it
    was automatic or set by an admin.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    history = await partner_service.tier_history(db, partner)
    return [PartnerTierHistoryItem.model_validate(h) for h in history]


# ═════════════════════════════ Dashboard ═════════════════════════════════


@partners_router.get(
    "/me/dashboard",
    response_model=PartnerDashboardResponse,
    summary="Partner dashboard summary",
)
async def get_partner_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerDashboardResponse:
    """Headline metrics and balances.

    All monetary figures are summed live from the commission ledger.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    return await partner_service.dashboard(db, partner)


@partners_router.get(
    "/me/analytics",
    response_model=PartnerAnalyticsResponse,
    summary="Partner performance analytics",
)
async def get_partner_analytics(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerAnalyticsResponse:
    """Daily click/conversion/revenue series plus campaign and country splits.

    Defaults to the last 30 days; the maximum range is 366 days.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    return await partner_service.analytics(
        db, partner, from_date=from_date, to_date=to_date
    )


@partners_router.get(
    "/me/resources",
    response_model=PartnerResourceCenterResponse,
    summary="Partner resource center",
)
async def get_partner_resources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PartnerResourceCenterResponse:
    """Copy and asset catalog for introductions.

    Downloadable files that do not exist are returned with
    ``available: false`` rather than invented URLs.
    """
    from app.modules.partners.landing import _resources
    from app.modules.partners.links import ReferralLinkService

    partner = await partner_service.get_partner_for_user(db, current_user)
    return PartnerResourceCenterResponse(
        items=[PartnerResourceItem(**item) for item in _resources()],
        referral_url=ReferralLinkService.build(partner.partner_code),
    )


@partners_router.get(
    "/me/customers",
    response_model=OffsetPagination[ReferredCustomerItem],
    summary="List customers attributed to me",
)
async def list_my_customers(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[ReferredCustomerItem]:
    """Referred customers with **masked** contact details at every tier."""
    partner = await partner_service.get_partner_for_user(db, current_user)
    items, total = await partner_service.list_referred_customers(
        db, partner, status=status_filter, page=page, size=size
    )
    return OffsetPagination[ReferredCustomerItem](
        items=items, total=total, page=page, size=size, pages=_pages(total, size)
    )


# ═════════════════════════════ Campaigns ═════════════════════════════════


@partners_router.post(
    "/me/campaigns",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campaign",
)
async def create_campaign(
    request: Request,
    payload: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> CampaignResponse:
    """Create a campaign to group and measure links.

    The returned ``referral_url`` is the canonical shareable link for
    the campaign; clients should use it verbatim rather than building
    their own.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    campaign = await partner_service.create_campaign(db, partner, payload)
    return partner_service.campaign_to_response(partner, campaign)


@partners_router.get(
    "/me/campaigns",
    response_model=OffsetPagination[CampaignResponse],
    summary="List my campaigns",
)
async def list_campaigns(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[CampaignResponse]:
    """Campaigns owned by the authenticated partner. Another partner's
    campaigns are never visible here.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    campaigns, total = await CampaignRepository.list_for_partner(
        db, partner.id, status=status_filter, page=page, size=size
    )
    return OffsetPagination[CampaignResponse](
        items=[partner_service.campaign_to_response(partner, c) for c in campaigns],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@partners_router.get(
    "/me/campaigns/{campaign_id}",
    response_model=CampaignResponse,
    summary="Get one of my campaigns",
    responses={404: {"description": "Campaign not found or not owned by this partner"}},
)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> CampaignResponse:
    """One campaign owned by the authenticated partner."""
    partner = await partner_service.get_partner_for_user(db, current_user)
    campaign = await partner_service.get_owned_campaign(db, partner, campaign_id)
    return partner_service.campaign_to_response(partner, campaign)


@partners_router.patch(
    "/me/campaigns/{campaign_id}",
    response_model=CampaignResponse,
    summary="Update one of my campaigns",
)
async def update_campaign(
    request: Request,
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> CampaignResponse:
    """Update a campaign the authenticated partner owns. Historical
    attribution and commissions are unaffected.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    campaign = await partner_service.update_campaign(
        db, partner, campaign_id, payload
    )
    return partner_service.campaign_to_response(partner, campaign)


@partners_router.delete(
    "/me/campaigns/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive one of my campaigns",
)
async def delete_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> None:
    """Soft delete. Historical attribution and commissions are preserved."""
    partner = await partner_service.get_partner_for_user(db, current_user)
    await partner_service.delete_campaign(db, partner, campaign_id)


# ═══════════════════════════ Referral links ══════════════════════════════


@partners_router.post(
    "/me/links",
    response_model=ReferralLinkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a referral link",
)
async def create_referral_link(
    request: Request,
    payload: ReferralLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> ReferralLinkResponse:
    """Create a trackable link.

    The shareable URL is always built by ``ReferralLinkService`` from
    configuration — clients must use the returned ``url`` rather than
    assembling one.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    link = await partner_service.create_link(db, partner, payload)
    return await partner_service.link_to_response(db, partner, link)


@partners_router.get(
    "/me/links",
    response_model=OffsetPagination[ReferralLinkResponse],
    summary="List my referral links",
)
async def list_referral_links(
    campaign_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[ReferralLinkResponse]:
    """Referral links owned by the authenticated partner, optionally
    filtered by campaign or status.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    links, total = await ReferralLinkRepository.list_for_partner(
        db, partner.id, campaign_id=campaign_id, status=status_filter, page=page, size=size
    )
    items = [await partner_service.link_to_response(db, partner, l) for l in links]
    return OffsetPagination[ReferralLinkResponse](
        items=items, total=total, page=page, size=size, pages=_pages(total, size)
    )


@partners_router.patch(
    "/me/links/{link_id}",
    response_model=ReferralLinkResponse,
    summary="Update one of my referral links",
)
async def update_referral_link(
    request: Request,
    link_id: uuid.UUID,
    payload: ReferralLinkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> ReferralLinkResponse:
    """Update a link the authenticated partner owns. Pausing or archiving
    a link stops new clicks; it never affects commissions already
    earned through it.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    link = await partner_service.update_link(db, partner, link_id, payload)
    return await partner_service.link_to_response(db, partner, link)


@partners_router.delete(
    "/me/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive one of my referral links",
)
async def delete_referral_link(
    link_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> None:
    """Archive a referral link (soft delete). The default link cannot be
    removed. Past attribution and commissions are preserved.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    await partner_service.delete_link(db, partner, link_id)


# ═══════════════════════════ Commissions ═════════════════════════════════


@partners_router.get(
    "/me/commissions",
    response_model=OffsetPagination[CommissionItem],
    summary="List my commission ledger entries",
)
async def list_my_commissions(
    status_filter: str | None = Query(default=None, alias="status"),
    entry_type: str | None = Query(default=None),
    period_month: str | None = Query(
        default=None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"
    ),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[CommissionItem]:
    """Immutable ledger entries, newest first.

    Amounts are signed integer minor units: positive accruals, negative
    reversals and payouts.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    commissions, total = await CommissionRepository.list_for_partner(
        db,
        partner.id,
        status=status_filter,
        entry_type=entry_type,
        period_month=period_month,
        page=page,
        size=size,
    )
    return OffsetPagination[CommissionItem](
        items=[CommissionItem.model_validate(c) for c in commissions],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@partners_router.get(
    "/me/commissions/balance",
    response_model=CommissionBalanceResponse,
    summary="My commission balance",
)
async def get_my_balance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> CommissionBalanceResponse:
    """Balances by ledger status, plus payout eligibility."""
    partner = await partner_service.get_partner_for_user(db, current_user)
    balance = await commission_service.balance(db, partner)
    return CommissionBalanceResponse(**balance)


@partners_router.get(
    "/me/commissions/{commission_id}/events",
    response_model=list[CommissionEventItem],
    summary="Audit trail for one commission",
    responses={404: {"description": "Commission not found or not owned by this partner"}},
)
async def get_commission_events(
    commission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> list[CommissionEventItem]:
    """The full state-transition history of one commission: who or what
    moved it, when, and why. This is the audit trail behind every
    balance change.
    """
    from app.core.exceptions import ResourceNotFoundException

    partner = await partner_service.get_partner_for_user(db, current_user)
    commission = await CommissionRepository.get_owned(db, commission_id, partner.id)
    if commission is None:
        raise ResourceNotFoundException("Commission not found")
    events = await CommissionRepository.list_events(db, commission.id)
    return [CommissionEventItem.model_validate(e) for e in events]


@partners_router.get(
    "/me/settlements",
    response_model=OffsetPagination[SettlementItem],
    summary="My monthly settlements",
)
async def list_my_settlements(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[SettlementItem]:
    """Closed monthly settlements, newest first. A settlement is a frozen
    summary of the ledger for one month; the ledger itself remains the
    source of truth.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    settlements, total = await SettlementRepository.list_for_partner(
        db, partner.id, page=page, size=size
    )
    return OffsetPagination[SettlementItem](
        items=[SettlementItem.model_validate(s) for s in settlements],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


# ═════════════════════════════ Payouts ═══════════════════════════════════


@partners_router.post(
    "/me/payout-accounts",
    response_model=PayoutAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a payout account",
)
async def add_payout_account(
    request: Request,
    payload: PayoutAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PayoutAccountResponse:
    """Store payout details.

    The payload is encrypted at rest; responses only ever contain a masked
    label and the last four characters.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    account = await payout_service.add_account(db, partner, payload)
    return PayoutAccountResponse.model_validate(account)


@partners_router.get(
    "/me/payout-accounts",
    response_model=list[PayoutAccountResponse],
    summary="List my payout accounts (masked)",
)
async def list_payout_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> list[PayoutAccountResponse]:
    """Payout accounts for the authenticated partner. Only a masked label
    and the last four characters are returned — the stored details are
    encrypted and never exposed.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    accounts = await payout_service.list_accounts(db, partner)
    return [PayoutAccountResponse.model_validate(a) for a in accounts]


@partners_router.delete(
    "/me/payout-accounts/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a payout account",
)
async def delete_payout_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> None:
    """Remove a payout account. Refused while a payout referencing it is
    still in progress.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    await payout_service.delete_account(db, partner, account_id)


@partners_router.post(
    "/me/payouts",
    response_model=PayoutResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Request a payout of my payable balance",
    responses={
        409: {"description": "A payout is already in progress, or commissions are held"},
        422: {"description": "Balance is below the minimum payout threshold"},
    },
)
async def request_payout(
    request: Request,
    payload: PayoutRequestCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> PayoutResponse:
    """Request a payout.

    The amount is derived server-side from payable ledger entries. Supply an
    ``Idempotency-Key`` header to make retries safe; the same key always
    returns the same payout.
    """
    await enforce_rate_limit(request, _payout_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    payout = await payout_service.request_payout(
        db,
        partner,
        payout_account_id=payload.payout_account_id,
        idempotency_key=idempotency_key,
        notes=payload.notes,
        actor_user_id=current_user.id,
    )
    return PayoutResponse.model_validate(payout)


@partners_router.get(
    "/me/payouts",
    response_model=OffsetPagination[PayoutResponse],
    summary="List my payouts",
)
async def list_my_payouts(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[PayoutResponse]:
    """Payouts requested by the authenticated partner, newest first."""
    partner = await partner_service.get_partner_for_user(db, current_user)
    payouts, total = await PayoutRepository.list_for_partner(
        db, partner.id, status=status_filter, page=page, size=size
    )
    return OffsetPagination[PayoutResponse](
        items=[PayoutResponse.model_validate(p) for p in payouts],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


# ══════════════════════════════ Leads ════════════════════════════════════


@partners_router.post(
    "/me/leads",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Introduce a lead",
    responses={409: {"description": "This prospect already has an open introduction"}},
)
async def create_lead(
    request: Request,
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> LeadResponse:
    """Submit a lead introduction.

    Prospect consent must be confirmed. Duplicate introductions are
    rejected without revealing who else holds the claim.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    lead = await partner_service.create_lead(db, partner, payload)
    return LeadResponse(**partner_service.lead_to_response(lead))


@partners_router.get(
    "/me/leads",
    response_model=OffsetPagination[LeadResponse],
    summary="List my lead introductions",
)
async def list_my_leads(
    status_filter: LeadStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[LeadResponse]:
    """Lead introductions submitted by the authenticated partner. Contact
    emails are masked.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    leads, total = await LeadRepository.list_for_partner(
        db,
        partner.id,
        status=status_filter.value if status_filter else None,
        page=page,
        size=size,
    )
    return OffsetPagination[LeadResponse](
        items=[LeadResponse(**partner_service.lead_to_response(l)) for l in leads],
        total=total,
        page=page,
        size=size,
        pages=_pages(total, size),
    )


@partners_router.get(
    "/me/leads/{lead_id}",
    response_model=LeadResponse,
    summary="Get one of my leads",
)
async def get_my_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> LeadResponse:
    """One lead owned by the authenticated partner, with its contact email
    masked.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    lead = await partner_service.get_owned_lead(db, partner, lead_id)
    return LeadResponse(**partner_service.lead_to_response(lead))


# ═══════════════════════════ Deployment claims ═══════════════════════════


@partners_router.post(
    "/me/claims",
    response_model=DeploymentClaimResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a deployment or creation claim",
)
async def create_claim(
    request: Request,
    payload: DeploymentClaimCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> DeploymentClaimResponse:
    """Claim a deploy/create engagement.

    At least one piece of evidence is required; approval creates the
    earning relationship.
    """
    await enforce_rate_limit(request, _write_limiter, str(current_user.id))
    partner = await partner_service.get_partner_for_user(db, current_user)
    claim = await partner_service.create_claim(db, partner, payload)
    evidence = await ClaimRepository.list_evidence(db, claim.id)
    response = DeploymentClaimResponse.model_validate(claim)
    return response.model_copy(
        update={"evidence": [ClaimEvidenceResponse.model_validate(e) for e in evidence]}
    )


@partners_router.get(
    "/me/claims",
    response_model=OffsetPagination[DeploymentClaimResponse],
    summary="List my deployment claims",
)
async def list_my_claims(
    status_filter: ClaimStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> OffsetPagination[DeploymentClaimResponse]:
    """Deployment and creation claims submitted by the authenticated
    partner, each with its supporting evidence.
    """
    partner = await partner_service.get_partner_for_user(db, current_user)
    claims, total = await ClaimRepository.list_for_partner(
        db,
        partner.id,
        status=status_filter.value if status_filter else None,
        page=page,
        size=size,
    )
    evidence_map = await ClaimRepository.list_evidence_for_claims(
        db, [c.id for c in claims]
    )
    items = []
    for claim in claims:
        item = DeploymentClaimResponse.model_validate(claim)
        items.append(
            item.model_copy(
                update={
                    "evidence": [
                        ClaimEvidenceResponse.model_validate(e)
                        for e in evidence_map.get(claim.id, [])
                    ]
                }
            )
        )
    return OffsetPagination[DeploymentClaimResponse](
        items=items, total=total, page=page, size=size, pages=_pages(total, size)
    )


@partners_router.get(
    "/me/claims/{claim_id}",
    response_model=DeploymentClaimResponse,
    summary="Get one of my deployment claims",
)
async def get_my_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_partner_user),
) -> DeploymentClaimResponse:
    """One claim owned by the authenticated partner, with its evidence."""
    partner = await partner_service.get_partner_for_user(db, current_user)
    claim = await partner_service.get_owned_claim(db, partner, claim_id)
    evidence = await ClaimRepository.list_evidence(db, claim.id)
    response = DeploymentClaimResponse.model_validate(claim)
    return response.model_copy(
        update={"evidence": [ClaimEvidenceResponse.model_validate(e) for e in evidence]}
    )


__all__ = ["partners_router"]
