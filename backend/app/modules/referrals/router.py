from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.dependencies import get_current_user
from app.modules.referrals.schemas import (
    ClaimRewardRequest,
    ClaimRewardResponse,
    LeaderboardResponse,
    ReferralInfoResponse,
)
from app.modules.referrals.service import ReferralService, referral_service
from app.modules.users.models import User

referrals_router = APIRouter(prefix="/v1/referrals", tags=["Referrals"])


def get_referral_service() -> ReferralService:
    return referral_service


async def _optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID | None:
    """Attempt to resolve the current user from the Authorization header.

    Returns the user ID if a valid Bearer token is present, or None if
    no authentication is provided.  Raises only for malformed tokens.
    """
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    bearer = HTTPBearer(auto_error=False)
    credentials: HTTPAuthorizationCredentials | None = await bearer(request)
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        return None
    if payload.get("type") != "access":
        return None
    user_id_str = payload.get("sub")
    if not user_id_str:
        return None
    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        return None


@referrals_router.get("/my-referral", response_model=ReferralInfoResponse)
async def get_my_referral(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReferralService = Depends(get_referral_service),
) -> ReferralInfoResponse:
    """Get the authenticated user's referral information including code and stats."""
    return await service.get_referral_info(db, current_user.id)


@referrals_router.post("/claim-reward", response_model=ClaimRewardResponse)
async def claim_reward(
    request: ClaimRewardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReferralService = Depends(get_referral_service),
) -> ClaimRewardResponse:
    """Claim a pending referral reward."""
    return await service.claim_reward(db, current_user.id, request.reward_id)


@referrals_router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    period: str = Query(default="all_time", pattern="^(all_time|weekly|monthly)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user_id: uuid.UUID | None = Depends(_optional_current_user),
    service: ReferralService = Depends(get_referral_service),
) -> LeaderboardResponse:
    """Get the public referral leaderboard.

    Authentication is optional. When authenticated, the current user's
    entry will be flagged with ``is_self=True`` and show their referral code.
    """
    entries, total = await service.get_leaderboard(
        db, period=period, page=page, page_size=page_size, current_user_id=current_user_id
    )
    return LeaderboardResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
    )
