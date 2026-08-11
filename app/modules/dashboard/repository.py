"""Dashboard read-model repository marker.

Aggregates are composed through public module services to preserve domain boundaries.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class DashboardRepository:
    def __init__(self, replica_session: AsyncSession) -> None:
        self.replica_session = replica_session
