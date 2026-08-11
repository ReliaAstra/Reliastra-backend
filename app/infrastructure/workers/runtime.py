"""Short-lived async runtime for Celery tasks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.session import DatabaseManager


@asynccontextmanager
async def worker_session(settings: Settings) -> AsyncIterator[AsyncSession]:
    database = DatabaseManager(settings.database_url)
    async with database.sessions() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await database.dispose()
