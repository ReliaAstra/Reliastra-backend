"""Public, unauthenticated referral resolution — ``GET /v1/public/referral/{code}``.

This is the single entry point for ``https://reliastra.com/r/{code}``. It is
deliberately tiny: validate the code, resolve the partner, count the click,
and return the destination (a relative path) plus the referral code the
signup form should replay. No PII, no financials, no click analytics.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.partners.constants import EARNING_STATUSES
from app.modules.partners.models import PartnerProfile
from app.modules.partners.repository import PartnerProfileRepository
from app.modules.partners.schemas import ReferralResolveResponse
from app.modules.referrals.repository import ReferralCodeRepository

logger = logging.getLogger(__name__)

public_partners_router = APIRouter(prefix="/v1", tags=["Partners — Public"])

#: Generous on purpose: a partner's launch traffic must not 429 real visitors.
_resolve_limiter = SlidingWindowRateLimiter(
    limit=1200, window_seconds=60, key_prefix="partner_resolve"
)

_DEFAULT_DESTINATION = "/"


@public_partners_router.get(
    "/public/referral/{referral_code}",
    response_model=ReferralResolveResponse,
    summary="Resolve a partner referral link",
)
async def resolve_referral(
    request: Request,
    referral_code: str,
    to: str | None = Query(
        default=None, description="Relative destination path after /r/{code}"
    ),
    db: AsyncSession = Depends(get_db),
) -> ReferralResolveResponse:
    """Validate a referral code and return signup attribution metadata.

    The destination is always a relative path — a crafted ``to`` cannot be
    turned into an open redirect.
    """
    await enforce_rate_limit(request, _resolve_limiter)

    code = await ReferralCodeRepository.get_by_code(db, referral_code)
    if code is None:
        return ReferralResolveResponse(
            valid=False, referral_code=None, destination=_DEFAULT_DESTINATION
        )

    # Resolve the owning partner (if any) and confirm it can earn.
    result = await db.execute(
        select(PartnerProfile).where(PartnerProfile.referral_code_id == code.id)
    )
    partner = result.scalar_one_or_none()
    if partner is None or partner.status not in EARNING_STATUSES:
        return ReferralResolveResponse(
            valid=False, referral_code=None, destination=_DEFAULT_DESTINATION
        )

    # Count the click (a counter, not an analytics platform).
    await PartnerProfileRepository.update(
        db, partner, click_count=(partner.click_count or 0) + 1
    )

    destination = _safe_destination(to)

    return ReferralResolveResponse(
        valid=True,
        referral_code=code.code,
        destination=destination,
    )


def _safe_destination(to: str | None) -> str:
    """Return a safe relative destination path, defaulting to the home page."""
    if not to:
        return _DEFAULT_DESTINATION
    if not to.startswith("/") or to.startswith("//") or "://" in to:
        return _DEFAULT_DESTINATION
    return to
