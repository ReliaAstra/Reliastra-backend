from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.timeline_share.schemas import (
    TimelineShareCreateRequest,
    TimelineShareResponse,
)
from app.modules.timeline_share.service import (
    TimelineShareService,
    timeline_share_service,
)

if TYPE_CHECKING:
    from app.modules.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/vendors", tags=["Timeline Share"])

timeline_share_limiter = SlidingWindowRateLimiter(
    limit=30,
    window_seconds=60,
    key_prefix="rl_timeline_share",
)


def get_timeline_share_service() -> TimelineShareService:
    return timeline_share_service


@router.get("/{vendor_name}/timeline/share.png")
async def get_timeline_share_png(
    vendor_name: str,
    request: Request,
    window: str = Query(default="24h"),
    region: str = Query(default="us-east"),
    width: int = Query(default=1200, ge=400, le=2400),
    height: int = Query(default=630, ge=300, le=1200),
    include_qr: bool = Query(default=True),
    utm_source: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    service: TimelineShareService = Depends(get_timeline_share_service),
) -> Response:
    """Generate and return a shareable timeline PNG image for a vendor.

    This is a public endpoint (no auth required) that renders the vendor's
    status timeline as a PNG with a dark theme, latency chart, availability
    band, incident markers, and optional QR code.
    """
    await enforce_rate_limit(request, timeline_share_limiter)
    png_bytes, _ = await service.generate_timeline_png(
        db, vendor_name, window, region, width, height, include_qr, utm_source
    )
    return Response(content=png_bytes, media_type="image/png")


@router.post(
    "/{vendor_name}/timeline/share",
    status_code=status.HTTP_201_CREATED,
    response_model=TimelineShareResponse,
)
async def create_timeline_share(
    vendor_name: str,
    request: Request,
    body: TimelineShareCreateRequest,
    db: AsyncSession = Depends(get_db),
    service: TimelineShareService = Depends(get_timeline_share_service),
) -> TimelineShareResponse:
    """Create a short-lived share link for a vendor's timeline PNG.

    Optionally authenticated: if a valid Bearer token or API key is provided,
    the share is attributed to that user.  Otherwise the share is anonymous.
    """
    await enforce_rate_limit(request, timeline_share_limiter)

    # Optional auth: attempt to identify the user without requiring it
    user_id: uuid.UUID | None = None
    try:
        from app.dependencies import get_current_user

        user: User = await get_current_user(request, db)
        user_id = user.id
    except Exception:
        # No valid auth — proceed as anonymous share
        pass

    return await service.create_share_link(
        session=db,
        vendor_name=vendor_name,
        user_id=user_id,
        request=body,
    )
