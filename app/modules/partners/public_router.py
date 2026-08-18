"""Public, unauthenticated partner endpoints — ``/v1/public/*``.

These endpoints sit on the hot path of every shared partner link, so they
are built to be fast, cheap and hard to abuse without breaking legitimate
traffic:

* Rate limits are **generous on purpose**. A partner running a launch
  campaign can legitimately drive thousands of resolutions per minute from
  one CDN egress IP; throttling that would break the product. Link
  resolution therefore gets a high per-IP ceiling, while the endpoints that
  can enumerate data (directory search) get tighter ones.
* No authentication is required and none is inferred. Nothing here returns
  partner PII, contact details, financials or customer data.
* Resolution never trusts the client: the partner, campaign and destination
  all come from the database, and the destination is a relative path so a
  crafted link cannot be turned into an open redirect.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ResourceNotFoundException
from app.core.pagination import OffsetPagination
from app.core.rate_limit import (
    SlidingWindowRateLimiter,
    client_ip_from_request,
    enforce_rate_limit,
)
from app.db.session import get_db
from app.modules.partners.constants import UTM_FIELDS, PartnerStatus
from app.modules.partners.repository import (
    PartnerRepository,
    ProgramContentRepository,
)
from app.modules.partners.schemas import (
    PartnerProgramContentItem,
    PartnerProgramResponse,
    PartnerPublicResponse,
    ReferralResolveResponse,
    ReferralValidateResponse,
)
from app.modules.partners.service import partner_service
from app.modules.partners.tracking import tracking_service

logger = logging.getLogger(__name__)

public_partners_router = APIRouter(prefix="/v1", tags=["Partners — Public"])

#: Link resolution: deliberately high. A viral post or an email blast from a
#: single corporate NAT must not start 429-ing real visitors.
_resolve_limiter = SlidingWindowRateLimiter(
    limit=1200, window_seconds=60, key_prefix="partner_resolve"
)
#: Validation probes are even cheaper and are called from signup forms.
_validate_limiter = SlidingWindowRateLimiter(
    limit=600, window_seconds=60, key_prefix="partner_validate"
)
#: Directory browsing can enumerate; keep it at the standard public ceiling.
_directory_limiter = SlidingWindowRateLimiter(
    limit=60, window_seconds=60, key_prefix="partner_directory"
)


def _utm_from_query(request: Request) -> dict[str, str]:
    """Capture UTM parameters for analytics only.

    These are recorded against the click and the attribution touch. They
    never influence *which partner* owns the visitor — that is decided
    solely by the resolved partner code.
    """
    return {
        field: value
        for field in UTM_FIELDS
        if (value := request.query_params.get(field))
    }


@public_partners_router.get(
    "/referral/{partner_code}",
    response_model=ReferralResolveResponse,
    summary="Resolve a partner referral link",
    responses={404: {"description": "Unknown partner code"}},
)
async def resolve_referral(
    request: Request,
    partner_code: str,
    campaign: str | None = Query(
        default=None, description="Campaign code from ?campaign="
    ),
    to: str | None = Query(default=None, description="Relative destination path"),
    visitor_id: str | None = Query(
        default=None, description="Existing first-party visitor id, if any"
    ),
    db: AsyncSession = Depends(get_db),
) -> ReferralResolveResponse:
    """Resolve ``/r/{partner_code}`` and record the click.

    Returns the destination and an anonymous ``visitor_id`` that the caller
    should persist (first-party cookie or local storage) and replay at
    signup as ``partner_visitor_id`` — that is what links the eventual
    account back to this touch.

    A click is analytics only. It never creates an entitlement to
    commission on its own.
    """
    await enforce_rate_limit(request, _resolve_limiter)

    resolved = await tracking_service.resolve_referral(
        db,
        partner_code=partner_code,
        campaign_code=campaign,
        destination_path=to,
        visitor_id=visitor_id,
        ip=client_ip_from_request(request),
        user_agent=request.headers.get("user-agent"),
        referer=request.headers.get("referer"),
        utm=_utm_from_query(request),
        record_click=True,
    )

    return ReferralResolveResponse(
        partner_code=resolved.partner.partner_code,
        partner_display_name=resolved.partner.display_name,
        partner_slug=resolved.partner.slug,
        campaign_code=(
            resolved.campaign.campaign_code if resolved.campaign else None
        ),
        destination_path=resolved.destination_path,
        visitor_id=resolved.visitor_id,
        attribution_expires_at=resolved.expires_at,
        attribution_window_days=settings.PARTNER_ATTRIBUTION_WINDOW_DAYS,
        is_valid=resolved.partner.status == PartnerStatus.ACTIVE.value,
    )


@public_partners_router.get(
    "/referral/{partner_code}/validate",
    response_model=ReferralValidateResponse,
    summary="Check whether a partner code is valid",
)
async def validate_referral_code(
    request: Request,
    partner_code: str,
    campaign: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ReferralValidateResponse:
    """Validate a partner code without recording a click.

    Intended for signup forms that let a user type a code by hand. Always
    returns 200: an invalid code is a normal outcome, not an error, and the
    response deliberately reveals nothing beyond the public display name.
    """
    await enforce_rate_limit(request, _validate_limiter)

    partner = await PartnerRepository.get_by_code(db, partner_code)
    if partner is None:
        return ReferralValidateResponse(
            partner_code=partner_code, is_valid=False, reason="unknown_code"
        )
    if partner.status != PartnerStatus.ACTIVE.value:
        return ReferralValidateResponse(
            partner_code=partner.partner_code,
            is_valid=False,
            reason="partner_inactive",
        )

    campaign_code = None
    if campaign:
        from app.modules.partners.repository import CampaignRepository

        found = await CampaignRepository.get_by_code(db, partner.id, campaign)
        campaign_code = found.campaign_code if found else None

    return ReferralValidateResponse(
        partner_code=partner.partner_code,
        is_valid=True,
        partner_display_name=partner.display_name,
        campaign_code=campaign_code,
    )


@public_partners_router.get(
    "/partners",
    response_model=OffsetPagination[PartnerPublicResponse],
    summary="Browse the public partner directory",
)
async def list_public_partners(
    request: Request,
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    partner_type: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    expertise: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> OffsetPagination[PartnerPublicResponse]:
    """List partners who have opted into public listing.

    Only active, explicitly opted-in partners appear, and only their
    marketing profile is returned.
    """
    await enforce_rate_limit(request, _directory_limiter)

    partners, total = await PartnerRepository.list_public_directory(
        db,
        country_code=country_code,
        partner_type=partner_type,
        tier=tier,
        expertise=expertise,
        search=search,
        page=page,
        size=size,
    )
    items = [
        PartnerPublicResponse(
            slug=p.slug,
            display_name=p.display_name,
            partner_type=p.partner_type,
            tier=p.tier,
            headline=p.headline,
            bio=p.bio,
            website_url=p.website_url,
            logo_url=p.logo_url,
            country_code=p.country_code,
            expertise=p.expertise,
            languages=p.languages,
            member_since=p.approved_at.date() if p.approved_at else None,
        )
        for p in partners
    ]
    pages = (total + size - 1) // size if size else 0
    return OffsetPagination[PartnerPublicResponse](
        items=items, total=total, page=page, size=size, pages=pages
    )


@public_partners_router.get(
    "/partners/{partner_slug}",
    response_model=PartnerPublicResponse,
    summary="Get a public partner profile",
    responses={404: {"description": "Partner not found or not publicly listed"}},
)
async def get_public_partner(
    request: Request,
    partner_slug: str,
    db: AsyncSession = Depends(get_db),
) -> PartnerPublicResponse:
    """Public marketing profile for one partner.

    Unlisted, suspended and terminated partners return 404 — being listed is
    opt-in, and its absence should not be observable.
    """
    await enforce_rate_limit(request, _directory_limiter)

    partner = await PartnerRepository.get_by_slug(db, partner_slug)
    if (
        partner is None
        or not partner.is_publicly_listed
        or partner.status != PartnerStatus.ACTIVE.value
    ):
        raise ResourceNotFoundException("Partner not found")

    return PartnerPublicResponse(
        slug=partner.slug,
        display_name=partner.display_name,
        partner_type=partner.partner_type,
        tier=partner.tier,
        headline=partner.headline,
        bio=partner.bio,
        website_url=partner.website_url,
        logo_url=partner.logo_url,
        country_code=partner.country_code,
        expertise=partner.expertise,
        languages=partner.languages,
        member_since=partner.approved_at.date() if partner.approved_at else None,
    )


@public_partners_router.get(
    "/partner-program",
    response_model=PartnerProgramResponse,
    summary="Partner program terms and economics",
)
async def get_partner_program(
    request: Request,
    locale: str = Query(default="en", max_length=10),
    db: AsyncSession = Depends(get_db),
) -> PartnerProgramResponse:
    """Backend-managed program description.

    Tiers, earning methods, rates, attribution window, holding period and
    payout minimum all come from configuration and the content table, so
    that no client has to hardcode the commission structure or the
    marketing copy.
    """
    await enforce_rate_limit(request, _directory_limiter)
    return await partner_service.program(db, locale=locale)


@public_partners_router.get(
    "/partner-program/content",
    response_model=list[PartnerProgramContentItem],
    summary="Partner program content blocks",
)
async def get_partner_program_content(
    request: Request,
    section: str | None = Query(default=None, max_length=60),
    locale: str = Query(default="en", max_length=10),
    db: AsyncSession = Depends(get_db),
) -> list[PartnerProgramContentItem]:
    """Published, backend-managed copy blocks (FAQ, terms, benefits)."""
    await enforce_rate_limit(request, _directory_limiter)
    content = await ProgramContentRepository.list_published(
        db, locale=locale, section=section
    )
    return [PartnerProgramContentItem.model_validate(c) for c in content]


__all__ = ["public_partners_router"]
