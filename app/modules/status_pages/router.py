from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.dependencies import require_admin, require_member
from app.modules.status_pages.schemas import (
    PublicStatusResponse,
    StatusPageConfigRequest,
    StatusPageResponse,
)
from app.modules.status_pages.service import status_page_service

logger = logging.getLogger(__name__)

status_router = APIRouter(
    prefix="/v1/public/status", tags=["Status Page"]
)
status_page_router = APIRouter(
    prefix="/v1/orgs/{org_id}/status-page", tags=["Status Page"]
)

_public_status_limiter = SlidingWindowRateLimiter(
    limit=60, window_seconds=60, key_prefix="rl_public_status"
)


@status_router.get("", response_model=PublicStatusResponse)
async def get_public_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PublicStatusResponse:
    """Public system-wide status endpoint."""
    await enforce_rate_limit(request, _public_status_limiter)
    return await status_page_service.get_public_status(db)


@status_router.get("/{slug}")
async def get_public_status_by_slug(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public status page for an organization by slug."""
    await enforce_rate_limit(request, _public_status_limiter)
    logger.info("Public status page requested slug=%s", slug)
    return await status_page_service.get_public_status_page_by_slug(db, slug)


@status_page_router.get(
    "", response_model=StatusPageResponse, dependencies=[Depends(require_member)]
)
async def get_org_status_page(
    org_id: str,
    db: AsyncSession = Depends(get_db),
) -> StatusPageResponse:
    """Get organization's status page configuration (member+)."""
    import uuid

    page = await status_page_service.get_org_status_page(
        db, uuid.UUID(org_id)
    )
    if page is None:
        from app.core.exceptions import ResourceNotFoundException

        raise ResourceNotFoundException("Status page not found for this organization")
    return page


@status_page_router.post(
    "",
    response_model=StatusPageResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_org_status_page(
    org_id: str,
    request: StatusPageConfigRequest,
    db: AsyncSession = Depends(get_db),
) -> StatusPageResponse:
    """Create a status page for the organization (admin+)."""
    import uuid

    return await status_page_service.create_org_status_page(
        db, uuid.UUID(org_id), request
    )
