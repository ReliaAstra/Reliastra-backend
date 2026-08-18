from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.feed.service import feed_service

logger = logging.getLogger(__name__)

feed_router = APIRouter(prefix="/v1/feed", tags=["RSS Feed"])

_feed_limiter = SlidingWindowRateLimiter(
    limit=30, window_seconds=60, key_prefix="rl_feed"
)

_CONTENT_TYPES = {
    "atom": "application/atom+xml; charset=utf-8",
    "rss": "application/rss+xml; charset=utf-8",
}


@feed_router.get("/vendors")
async def get_vendor_feed(
    request: Request,
    format: str = Query(default="atom", alias="format"),
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Public feed of all tracked vendors (Atom or RSS)."""
    await enforce_rate_limit(request, _feed_limiter)

    fmt = format.lower().strip()
    if fmt not in _CONTENT_TYPES:
        from app.core.exceptions import ValidationException

        raise ValidationException(
            f"Unsupported format '{format}'. Supported: atom, rss"
        )

    logger.info("Vendor feed requested format=%s category=%s", fmt, category)
    xml_str = await feed_service.generate_vendor_feed(db, format_type=fmt, category=category)

    etag = feed_service.get_etag(xml_str)
    last_modified = feed_service.get_last_modified(xml_str)

    # Check If-None-Match for 304 Not Modified
    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return Response(
        content=xml_str,
        media_type=_CONTENT_TYPES[fmt],
        headers={
            "ETag": etag,
            "Last-Modified": last_modified,
            "Cache-Control": "public, max-age=300",
        },
    )


@feed_router.get("/vendors/{vendor_name}")
async def get_vendor_detail_feed(
    request: Request,
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Per-vendor Atom feed with status changes and incidents."""
    await enforce_rate_limit(request, _feed_limiter)

    logger.info("Vendor detail feed requested vendor_name=%s", vendor_name)
    xml_str = await feed_service.generate_vendor_detail_feed(db, vendor_name)

    etag = feed_service.get_etag(xml_str)
    last_modified = feed_service.get_last_modified(xml_str)

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return Response(
        content=xml_str,
        media_type=_CONTENT_TYPES["atom"],
        headers={
            "ETag": etag,
            "Last-Modified": last_modified,
            "Cache-Control": "public, max-age=300",
        },
    )
