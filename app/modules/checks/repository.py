"""Check-result persistence and quorum queries."""

from __future__ import annotations

import builtins
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checks.models import CheckResult
from app.modules.checks.schemas import CheckResultCreateDTO, HistoryPoint


class CheckRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, result: CheckResultCreateDTO) -> CheckResult:
        model = CheckResult(**result.model_dump())
        self.session.add(model)
        await self.session.flush()
        return model

    async def set_quorum(self, result: CheckResult) -> None:
        result.quorum_confirmed = True
        await self.session.flush()

    async def recent(
        self, dependency_id: UUID, since: datetime, limit: int = 100
    ) -> list[CheckResult]:
        statement = (
            select(CheckResult)
            .where(CheckResult.dependency_id == dependency_id, CheckResult.executed_at >= since)
            .order_by(CheckResult.executed_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def list(
        self,
        org_id: UUID,
        dependency_id: UUID,
        start: datetime,
        end: datetime,
        limit: int,
        cursor: UUID | None,
    ) -> list[CheckResult]:
        statement = select(CheckResult).where(
            CheckResult.org_id == org_id,
            CheckResult.dependency_id == dependency_id,
            CheckResult.executed_at.between(start, end),
        )
        if cursor:
            statement = statement.where(CheckResult.id < cursor)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(CheckResult.executed_at.desc()).limit(limit + 1)
                )
            ).all()
        )

    async def history(
        self, org_id: UUID, dependency_id: UUID, start: datetime, end: datetime
    ) -> builtins.list[HistoryPoint]:
        bucket = func.date_trunc("hour", CheckResult.executed_at)
        statement = (
            select(
                bucket.label("bucket"),
                (func.avg(case((CheckResult.is_up.is_(True), 1.0), else_=0.0)) * 100).label(
                    "uptime"
                ),
                func.avg(CheckResult.latency_ms).label("latency"),
                func.count().label("checks"),
            )
            .where(
                CheckResult.org_id == org_id,
                CheckResult.dependency_id == dependency_id,
                CheckResult.executed_at.between(start, end),
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            HistoryPoint(
                bucket=row.bucket,
                uptime_percent=float(row.uptime or 0),
                average_latency_ms=float(row.latency or 0),
                checks=int(row.checks),
            )
            for row in rows
        ]

    async def org_summary(self, org_id: UUID, start: datetime) -> tuple[int, float]:
        statement = select(
            func.count(), func.avg(case((CheckResult.is_up.is_(True), 1.0), else_=0.0))
        ).where(CheckResult.org_id == org_id, CheckResult.executed_at >= start)
        count, uptime = (await self.session.execute(statement)).one()
        return int(count), float(uptime or 0) * 100
