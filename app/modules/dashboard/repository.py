import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.checks.models import CheckResult
from app.modules.dependencies.models import Dependency
from app.modules.incidents.models import Incident


def _bucket_expression() -> Any:
    """Return a SQL date-truncation expression bucketing to 15-minute intervals."""
    from sqlalchemy.dialects.postgresql import TIMESTAMP
    from sqlalchemy import text

    return func.date_trunc("hour", CheckResult.executed_at).label("bucket")


class DashboardRepository:
    @staticmethod
    async def get_summary_stats(
        session: AsyncSession, org_id: uuid.UUID
    ) -> dict[str, Any]:
        dep_query = select(func.count(Dependency.id)).where(
            Dependency.org_id == org_id,
            Dependency.is_active == True,  # noqa: E712
            Dependency.is_deleted == False,  # noqa: E712
        )
        dep_res = await session.execute(dep_query)
        active_deps = int(dep_res.scalar() or 0)

        inc_query = select(func.count(Incident.id)).where(
            Incident.org_id == org_id,
            Incident.status == "open",
        )
        inc_res = await session.execute(inc_query)
        open_incs = int(inc_res.scalar() or 0)

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        inc_today_query = select(func.count(Incident.id)).where(
            Incident.org_id == org_id,
            Incident.started_at >= today_start,
        )
        today_res = await session.execute(inc_today_query)
        alerts_today = int(today_res.scalar() or 0)

        # Compute actual uptime from check results in the last 24 hours
        uptime_window = datetime.now(timezone.utc) - timedelta(hours=24)
        uptime_query = select(
            func.count(CheckResult.id).label("total"),
            func.sum(func.cast(CheckResult.is_up, Integer)).label("up_count"),
        ).where(
            CheckResult.org_id == org_id,
            CheckResult.executed_at >= uptime_window,
        )
        uptime_res = await session.execute(uptime_query)
        uptime_row = uptime_res.one_or_none()
        if uptime_row and uptime_row.total and uptime_row.total > 0:
            total = int(uptime_row.total)
            up_count = int(uptime_row.up_count or 0)
            overall_uptime = round((up_count / total) * 100, 2)
        else:
            overall_uptime = 100.0

        return {
            "active_dependencies_count": active_deps,
            "open_incidents_count": open_incs,
            "overall_uptime_percentage": overall_uptime,
            "alerts_today_count": alerts_today,
        }

    @staticmethod
    async def get_latency_series(
        session: AsyncSession, org_id: uuid.UUID, hours: int = 24
    ) -> list[dict[str, Any]]:
        """Return time-bucketed average latency per region (Phase 11)."""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(
                _bucket_expression(),
                CheckResult.region,
                func.avg(CheckResult.latency_ms).label("avg_latency"),
            )
            .where(
                CheckResult.org_id == org_id,
                CheckResult.executed_at >= since,
            )
            .group_by("bucket", CheckResult.region)
            .order_by("bucket", CheckResult.region)
        )
        result = await session.execute(stmt)
        rows = []
        for bucket, region, avg_latency in result.all():
            rows.append(
                {
                    "timestamp": bucket.isoformat() if bucket else None,
                    "region": region,
                    "latency_ms": round(float(avg_latency or 0.0), 2),
                }
            )
        return rows

    @staticmethod
    async def get_sla_degradation(
        session: AsyncSession, org_id: uuid.UUID, period_days: int = 30
    ) -> dict[str, Any]:
        """Aggregate SLA degradation across dependencies over the period."""
        since = datetime.now(timezone.utc) - timedelta(days=period_days)
        stmt = (
            select(
                CheckResult.dependency_id,
                func.count(CheckResult.id).label("total"),
                func.sum(func.cast(CheckResult.is_up, Integer)).label("up_count"),
            )
            .where(
                CheckResult.org_id == org_id,
                CheckResult.executed_at >= since,
            )
            .group_by(CheckResult.dependency_id)
        )
        result = await session.execute(stmt)

        affected_services = 0
        total_degradation_pct = 0.0
        per_service_degradation: list[float] = []
        for row in result.all():
            total = int(row.total or 0)
            up = int(row.up_count or 0)
            if total > 0:
                uptime_pct = (up / total) * 100.0
                degradation = max(0.0, 100.0 - uptime_pct)
                if degradation > 0.0:
                    affected_services += 1
                per_service_degradation.append(degradation)

        if per_service_degradation:
            total_degradation_pct = round(sum(per_service_degradation) / len(per_service_degradation), 2)

        return {
            "total_degradation_pct": total_degradation_pct,
            "affected_services": affected_services,
            "period": f"{period_days}d",
        }

    @staticmethod
    async def list_active_dependencies(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[Dependency]:
        query = (
            select(Dependency)
            .where(
                Dependency.org_id == org_id,
                Dependency.is_active == True,  # noqa: E712
                Dependency.is_deleted == False,  # noqa: E712
            )
            .order_by(Dependency.name.asc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())
