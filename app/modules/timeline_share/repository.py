from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.timeline_share.models import TimelineShare

logger = logging.getLogger(__name__)


class TimelineShareRepository:
    @staticmethod
    async def create_share(
        session: AsyncSession,
        **kwargs: object,
    ) -> TimelineShare:
        """Create a new TimelineShare record and flush to get the ID."""
        share = TimelineShare(**kwargs)
        session.add(share)
        await session.flush()
        return share

    @staticmethod
    async def get_by_token(
        session: AsyncSession,
        token: str,
    ) -> TimelineShare | None:
        """Fetch a TimelineShare record by its unique share_token."""
        result = await session.execute(
            select(TimelineShare).where(TimelineShare.share_token == token)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def increment_view_count(
        session: AsyncSession,
        share_id: uuid.UUID,
    ) -> None:
        """Atomically increment the view_count for a share record."""
        await session.execute(
            update(TimelineShare)
            .where(TimelineShare.id == share_id)
            .values(view_count=TimelineShare.view_count + 1)
        )
        await session.flush()
