from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.dependencies import require_owner
from app.modules.growth.schemas import GrowthFunnelResponse, TopVendorStat
from app.modules.growth.service import growth_service

logger = logging.getLogger(__name__)

growth_router = APIRouter(prefix="/v1/admin/growth", tags=["Growth Analytics"])

_growth_limiter = SlidingWindowRateLimiter(
    limit=30, window_seconds=60, key_prefix="rl_growth"
)


async def _rate_limit(request: Request) -> None:
    await enforce_rate_limit(request, _growth_limiter)


@growth_router.get("/funnel", response_model=GrowthFunnelResponse)
async def get_growth_funnel(
    request: Request,
    period: str = Query(default="30d"),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_owner),
) -> GrowthFunnelResponse:
    await _rate_limit(request)
    logger.info("Growth funnel requested for period=%s", period)
    return await growth_service.get_funnel(db, period)


@growth_router.get("/top-vendors", response_model=list[TopVendorStat])
async def get_top_vendors(
    request: Request,
    sort_by: str = Query(default="views"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_owner),
) -> list[TopVendorStat]:
    await _rate_limit(request)
    logger.info("Top vendors requested sort_by=%s limit=%d", sort_by, limit)
    return await growth_service.get_top_vendors(db, sort_by, limit)


@growth_router.get("/referral-stats")
async def get_referral_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(require_owner),
) -> dict:
    await _rate_limit(request)
    logger.info("Referral stats requested")
    return await growth_service.get_referral_stats(db)
