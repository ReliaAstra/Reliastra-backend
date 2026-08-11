"""Async SQLAlchemy engine/session lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseManager:
    def __init__(self, database_url: str, replica_url: str | None = None) -> None:
        self.engine = self._make_engine(database_url)
        self.replica_engine = self._make_engine(replica_url) if replica_url else self.engine
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.replica_sessions = async_sessionmaker(
            self.replica_engine, expire_on_commit=False, autoflush=False
        )

    @staticmethod
    def _make_engine(url: str) -> AsyncEngine:
        return create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def replica_session(self) -> AsyncIterator[AsyncSession]:
        async with self.replica_sessions() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
        if self.replica_engine is not self.engine:
            await self.replica_engine.dispose()
