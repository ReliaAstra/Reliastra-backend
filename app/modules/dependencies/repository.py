"""Dependency persistence and scheduler claims."""

from __future__ import annotations

import builtins
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dependencies.models import Dependency


class DependencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count(self, org_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Dependency)
                .where(Dependency.org_id == org_id, Dependency.deleted_at.is_(None))
            )
            or 0
        )

    async def create(self, values: dict[str, object]) -> Dependency:
        model = Dependency(**values)
        self.session.add(model)
        await self.session.flush()
        return model

    async def get(self, org_id: UUID, dependency_id: UUID) -> Dependency | None:
        return cast(
            Dependency | None,
            await self.session.scalar(
                select(Dependency).where(
                    Dependency.id == dependency_id,
                    Dependency.org_id == org_id,
                    Dependency.deleted_at.is_(None),
                )
            ),
        )

    async def get_any_org(self, dependency_id: UUID) -> Dependency | None:
        return cast(
            Dependency | None,
            await self.session.scalar(
                select(Dependency).where(
                    Dependency.id == dependency_id, Dependency.deleted_at.is_(None)
                )
            ),
        )

    async def list(
        self, org_id: UUID, limit: int, cursor: UUID | None
    ) -> builtins.list[Dependency]:
        statement = select(Dependency).where(
            Dependency.org_id == org_id, Dependency.deleted_at.is_(None)
        )
        if cursor:
            statement = statement.where(Dependency.id < cursor)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(Dependency.id.desc()).limit(limit + 1)
                )
            ).all()
        )

    async def update(self, model: Dependency, values: dict[str, object]) -> Dependency:
        for field, value in values.items():
            setattr(model, field, value)
        await self.session.flush()
        return model

    async def claim_due(self, now: datetime, batch_size: int = 100) -> builtins.list[Dependency]:
        statement = (
            select(Dependency)
            .where(
                Dependency.is_active.is_(True),
                Dependency.deleted_at.is_(None),
                Dependency.next_check_at <= now,
            )
            .order_by(Dependency.next_check_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        dependencies = list((await self.session.scalars(statement)).all())
        for dependency in dependencies:
            dependency.next_check_at = now + timedelta(seconds=dependency.check_interval_seconds)
        await self.session.flush()
        return dependencies
