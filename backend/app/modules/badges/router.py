from __future__ import annotations

import asyncio
import hashlib
import logging

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.badges.schemas import BadgeEmbedResponse
from app.modules.badges.service import badge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/vendors", tags=["Badges"])

badge_limiter = SlidingWindowRateLimiter(
    limit=60, window_seconds=60, key_prefix="rl_badge"
)


async def _rate_limit(request: Request) -> None:
    await enforce_rate_limit(request, badge_limiter)


def get_badge_service():
    return badge_service


@router.get("/badge-embed-code", response_model=BadgeEmbedResponse)
async def get_badge_embed_code(
    request: Request,
    vendor_name: str = Query(..., description="Vendor slug (e.g. stripe)"),
    style: str = Query(default="flat"),
    label: str = Query(default="Reliastra"),
    show_latency: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    service = Depends(get_badge_service),
) -> BadgeEmbedResponse:
    """Return the HTML and Markdown embed snippets for a vendor status badge."""
    await _rate_limit(request)
    return await service.get_embed_code(
        session=db,
        vendor_name=vendor_name,
        style=style,
        label=label,
        show_latency=show_latency,
    )


@router.get("/{vendor_name}/badge.svg")
async def get_vendor_badge(
    vendor_name: str,
    request: Request,
    style: str = Query(default="flat"),
    label: str = Query(default="Reliastra"),
    show_latency: bool = Query(default=False),
    utm_source: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Render a vendor status badge as an SVG image.

    Returns ``image/svg+xml`` content-type so the response can be used
    directly inside an ``<img>`` tag or Markdown image syntax.
    """
    await _rate_limit(request)

    svg, status, display_name = await badge_service.generate_badge_svg(
        session=db,
        vendor_name=vendor_name,
        style=style,
        label=label,
        show_latency=show_latency,
    )

    # Record impression in the background (fire-and-forget)
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()
    asyncio.create_task(
        badge_service.record_impression_bg(
            vendor_name=vendor_name,
            ip_hash=ip_hash,
            utm_source=utm_source,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
        )
    )

    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=60, s-maxage=60",
            "X-Badge-Status": status,
            "X-Vendor-Name": display_name,
        },
    )
