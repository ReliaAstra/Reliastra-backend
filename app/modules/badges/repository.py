from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.badges.models import BadgeImpression

logger = logging.getLogger(__name__)


class BadgeRepository:
    @staticmethod
    async def create_impression(
        session: AsyncSession,
        vendor_name: str,
        ip_hash: str,
        utm_source: str | None = None,
        user_agent: str | None = None,
        referer: str | None = None,
    ) -> BadgeImpression:
        """Insert a badge impression row and flush (non-blocking fire-and-forget pattern)."""
        impression = BadgeImpression(
            vendor_name=vendor_name,
            ip_hash=ip_hash,
            utm_source=utm_source,
            user_agent=user_agent,
            referer=referer,
        )
        session.add(impression)
        await session.flush()
        return impression
