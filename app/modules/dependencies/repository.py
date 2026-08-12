import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.dependencies.models import Dependency


class DependencyRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, dep_id: uuid.UUID
    ) -> Dependency | None:
        query = select(Dependency).where(
            Dependency.id == dep_id,
            Dependency.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
        cursor: uuid.UUID | None = None,
    ) -> list[Dependency]:
        query = (
            select(Dependency)
            .where(
                Dependency.org_id == org_id,
                Dependency.is_deleted == False,  # noqa: E712
            )
            .order_by(Dependency.created_at.desc())
            .limit(limit)
        )
        if cursor:
            query = query.where(Dependency.created_at < (
                select(Dependency.created_at)
                .where(Dependency.id == cursor)
                .correlate(None)
                .scalar_subquery()
            ))
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def count_for_org(
        session: AsyncSession, org_id: uuid.UUID
    ) -> int:
        query = select(func.count(Dependency.id)).where(
            Dependency.org_id == org_id,
            Dependency.is_deleted == False,  # noqa: E712
        )
        result = await session.execute(query)
        return int(result.scalar() or 0)

    @staticmethod
    async def count_by_endpoint(
        session: AsyncSession, endpoint_url: str, exclude_id: uuid.UUID | None = None
    ) -> int:
        """Count other active dependencies pointing at the same endpoint."""
        query = select(func.count(Dependency.id)).where(
            Dependency.endpoint_url == endpoint_url,
            Dependency.is_deleted == False,  # noqa: E712
        )
        if exclude_id is not None:
            query = query.where(Dependency.id != exclude_id)
        result = await session.execute(query)
        return int(result.scalar() or 0)

    @staticmethod
    async def get_due_dependencies(
        session: AsyncSession,
    ) -> list[Dependency]:
        now = datetime.now(timezone.utc)
        query = select(Dependency).where(
            Dependency.is_active == True,  # noqa: E712
            Dependency.is_deleted == False,  # noqa: E712
            Dependency.next_check_at <= now,
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        name: str,
        endpoint_url: str,
        method: str,
        headers: dict[str, Any] | None,
        expected_status_codes: list[int],
        timeout_seconds: int,
        check_interval_seconds: int,
        regions: list[str],
        alert_threshold_ms: int | None = None,
        is_active: bool = True,
    ) -> Dependency:
        dep = Dependency(
            org_id=org_id,
            name=name,
            endpoint_url=endpoint_url,
            method=method,
            headers=headers,
            expected_status_codes=expected_status_codes,
            timeout_seconds=timeout_seconds,
            check_interval_seconds=check_interval_seconds,
            next_check_at=datetime.now(timezone.utc),
            regions=regions,
            alert_threshold_ms=alert_threshold_ms,
            is_active=is_active,
            is_deleted=False,
        )
        session.add(dep)
        await session.flush()
        return dep

    @staticmethod
    async def update(
        session: AsyncSession, dep: Dependency, **kwargs: Any
    ) -> Dependency:
        for key, value in kwargs.items():
            if value is not None and hasattr(dep, key):
                setattr(dep, key, value)
        session.add(dep)
        await session.flush()
        return dep

    @staticmethod
    async def soft_delete(session: AsyncSession, dep: Dependency) -> None:
        dep.is_deleted = True
        dep.is_active = False
        dep.deleted_at = datetime.now(timezone.utc)
        session.add(dep)
        await session.flush()
