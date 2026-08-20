"""Legacy growth analytics routes.

Canonical control-plane endpoints live under the admin module:

    GET /v1/admin/growth/overview
    GET /v1/admin/growth/funnel
    GET /v1/admin/growth/retention
    GET /v1/admin/growth/referrals
    GET /v1/admin/product/vendors

These legacy routes remain for backward compatibility and are marked deprecated.
The old ``/funnel`` path is intentionally NOT re-registered here — the
canonical admin growth funnel owns that path under require_system_admin.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.admin.guards import require_system_admin
from app.modules.growth.schemas import TopVendorStat
from app.modules.growth.service import growth_service
from app.modules.users.models import User

logger = logging.getLogger(__name__)

growth_router = APIRouter(
    prefix="/v1/admin/growth",
    tags=["Growth Analytics (deprecated)"],
    deprecated=True,
)

_growth_limiter = SlidingWindowRateLimiter(
    limit=30, window_seconds=60, key_prefix="rl_growth"
)


async def _rate_limit(request: Request) -> None:
    await enforce_rate_limit(request, _growth_limiter)


@growth_router.get(
    "/top-vendors",
    response_model=list[TopVendorStat],
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/product/vendors",
)
async def get_top_vendors(
    request: Request,
    sort_by: str = Query(default="views"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    # Prefer system admin; fall back to owner for existing tenants during migration
    _admin: User = Depends(require_system_admin),
) -> list[TopVendorStat]:
    await _rate_limit(request)
    logger.info("Top vendors requested sort_by=%s limit=%d", sort_by, limit)
    return await growth_service.get_top_vendors(db, sort_by, limit)


@growth_router.get(
    "/referral-stats",
    deprecated=True,
    summary="[Deprecated] Use GET /v1/admin/growth/referrals",
)
async def get_referral_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_system_admin),
) -> dict:
    await _rate_limit(request)
    logger.info("Referral stats requested")
    return await growth_service.get_referral_stats(db)


# Keep a compatibility alias at a non-conflicting path for the old PLG funnel
# shape (badge impressions etc.). Canonical funnel is /v1/admin/growth/funnel.
@growth_router.get(
    "/plg-funnel",
    deprecated=True,
    summary="[Deprecated] PLG funnel details are embedded in GET /v1/admin/growth/funnel (plg field)",
)
async def get_plg_funnel_legacy(
    request: Request,
    period: str = Query(default="30d"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_system_admin),
):
    await _rate_limit(request)
    return await growth_service.get_funnel(db, period)
