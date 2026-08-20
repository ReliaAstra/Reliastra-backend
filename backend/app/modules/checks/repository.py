import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select, func, update, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.checks.models import CheckResult
from app.modules.dependencies.models import Dependency


class CheckRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        dependency_id: uuid.UUID,
        org_id: uuid.UUID,
        region: str,
        latency_ms: float,
        is_up: bool,
        status_code: int | None = None,
        error_message: str | None = None,
        quorum_confirmed: bool = False,
    ) -> CheckResult:
        result = CheckResult(
            id=uuid.uuid4(),
            dependency_id=dependency_id,
            org_id=org_id,
            region=region,
            executed_at=datetime.now(timezone.utc),
            latency_ms=latency_ms,
            status_code=status_code,
            is_up=is_up,
            error_message=error_message,
            quorum_confirmed=quorum_confirmed,
        )
        session.add(result)
        await session.flush()
        return result

    @staticmethod
    async def list_for_dependency(
        session: AsyncSession,
        dependency_id: uuid.UUID,
        limit: int = 50,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[CheckResult]:
        # FIX 37: exclude results of soft-deleted dependencies.
        query = (
            select(CheckResult)
            .join(Dependency, CheckResult.dependency_id == Dependency.id)
            .where(
                CheckResult.dependency_id == dependency_id,
                Dependency.is_deleted == False,  # noqa: E712
            )
        )
        if start_time:
            query = query.where(CheckResult.executed_at >= start_time)
        if end_time:
            query = query.where(CheckResult.executed_at <= end_time)
        query = query.order_by(CheckResult.executed_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_recent_for_dependency(
        session: AsyncSession,
        dependency_id: uuid.UUID,
        window_seconds: int = 120,
    ) -> list[CheckResult]:
        # FIX 37: exclude results of soft-deleted dependencies.
        since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        query = (
            select(CheckResult)
            .join(Dependency, CheckResult.dependency_id == Dependency.id)
            .where(
                CheckResult.dependency_id == dependency_id,
                CheckResult.executed_at >= since,
                Dependency.is_deleted == False,  # noqa: E712
            )
            .order_by(CheckResult.executed_at.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
    ) -> list[CheckResult]:
        # FIX 37: exclude results of soft-deleted dependencies.
        query = (
            select(CheckResult)
            .join(Dependency, CheckResult.dependency_id == Dependency.id)
            .where(
                CheckResult.org_id == org_id,
                Dependency.is_deleted == False,  # noqa: E712
            )
            .order_by(CheckResult.executed_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def _stats_from_row(row: Any) -> dict[str, Any]:
        if not row or not row.total_checks:
            return {
                "uptime_percentage": 100.0,
                "avg_latency_ms": 0.0,
                "total_checks": 0,
                "total_up": 0,
                "total_down": 0,
            }
        total_checks = int(row.total_checks or 0)
        total_up = int(row.total_up or 0)
        total_down = total_checks - total_up
        uptime_pct = (total_up / total_checks) * 100.0 if total_checks > 0 else 100.0
        avg_latency = float(row.avg_latency or 0.0)
        return {
            "uptime_percentage": round(uptime_pct, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "total_checks": total_checks,
            "total_up": total_up,
            "total_down": total_down,
        }

    @staticmethod
    async def get_aggregated_stats(
        session: AsyncSession,
        dependency_id: uuid.UUID,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        query = (
            select(
                func.count(CheckResult.id).label("total_checks"),
                func.avg(CheckResult.latency_ms).label("avg_latency"),
                func.sum(func.cast(CheckResult.is_up, Integer)).label("total_up"),
            )
            .join(Dependency, CheckResult.dependency_id == Dependency.id)
            .where(
                CheckResult.dependency_id == dependency_id,
                CheckResult.executed_at >= since,
                Dependency.is_deleted == False,  # noqa: E712
            )
        )
        res = await session.execute(query)
        return CheckRepository._stats_from_row(res.one_or_none())

    @staticmethod
    async def get_aggregated_stats_bulk(
        session: AsyncSession,
        dependency_ids: list[uuid.UUID],
        window_hours: int = 24,
    ) -> dict[uuid.UUID, dict[str, Any]]:
        """FIX 22: aggregated stats for many dependencies in ONE query."""
        if not dependency_ids:
            return {}
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        query = (
            select(
                CheckResult.dependency_id.label("dependency_id"),
                func.count(CheckResult.id).label("total_checks"),
                func.avg(CheckResult.latency_ms).label("avg_latency"),
                func.sum(func.cast(CheckResult.is_up, Integer)).label("total_up"),
            )
            .join(Dependency, CheckResult.dependency_id == Dependency.id)
            .where(
                CheckResult.dependency_id.in_(dependency_ids),
                CheckResult.executed_at >= since,
                Dependency.is_deleted == False,  # noqa: E712
            )
            .group_by(CheckResult.dependency_id)
        )
        res = await session.execute(query)
        stats_map: dict[uuid.UUID, dict[str, Any]] = {}
        for row in res:
            stats_map[uuid.UUID(str(row.dependency_id))] = (
                CheckRepository._stats_from_row(row)
            )
        # Dependencies with no rows in the window are implicitly 100% up.
        for dep_id in dependency_ids:
            stats_map.setdefault(
                dep_id,
                {
                    "uptime_percentage": 100.0,
                    "avg_latency_ms": 0.0,
                    "total_checks": 0,
                    "total_up": 0,
                    "total_down": 0,
                },
            )
        return stats_map

    @staticmethod
    async def update_quorum(
        session: AsyncSession,
        check_id: uuid.UUID,
        confirmed: bool = True,
    ) -> None:
        stmt = (
            update(CheckResult)
            .where(CheckResult.id == check_id)
            .values(quorum_confirmed=confirmed)
        )
        await session.execute(stmt)

    @staticmethod
    async def get_vendor_aggregated_stats(
        session: AsyncSession,
        endpoint_url: str,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        """Get aggregated check stats across all dependencies pointing to the same vendor endpoint."""
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        query = select(
            func.count(CheckResult.id).label("total_checks"),
            func.avg(CheckResult.latency_ms).label("avg_latency"),
            func.sum(func.cast(CheckResult.is_up, Integer)).label("total_up"),
        ).join(
            Dependency, CheckResult.dependency_id == Dependency.id
        ).where(
            Dependency.endpoint_url == endpoint_url,
            Dependency.is_deleted == False,  # noqa: E712
            CheckResult.executed_at >= since,
        )
        res = await session.execute(query)
        row = res.one_or_none()
        if not row or not row.total_checks:
            return {
                "uptime_percentage": 100.0,
                "avg_latency_ms": 0.0,
                "total_checks": 0,
                "total_up": 0,
                "total_down": 0,
            }
        total_checks = int(row.total_checks or 0)
        total_up = int(row.total_up or 0)
        total_down = total_checks - total_up
        uptime_pct = (total_up / total_checks) * 100.0 if total_checks > 0 else 100.0
        avg_latency = float(row.avg_latency or 0.0)
        return {
            "uptime_percentage": round(uptime_pct, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "total_checks": total_checks,
            "total_up": total_up,
            "total_down": total_down,
        }

    @staticmethod
    async def get_vendor_recent_status(
        session: AsyncSession,
        endpoint_url: str,
        limit: int = 5,
    ) -> list[CheckResult]:
        """Get the most recent check results for a vendor endpoint across all deps."""
        query = select(CheckResult).join(
            Dependency, CheckResult.dependency_id == Dependency.id
        ).where(
            Dependency.endpoint_url == endpoint_url,
            Dependency.is_deleted == False,  # noqa: E712
        ).order_by(CheckResult.executed_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())
