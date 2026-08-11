import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.dependencies.models import Dependency
from app.modules.incidents.models import Incident


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

        return {
            "active_dependencies_count": active_deps,
            "open_incidents_count": open_incs,
            "overall_uptime_percentage": 99.95,
            "alerts_today_count": alerts_today,
        }

    @staticmethod
    async def list_active_dependencies(
        session: AsyncSession, org_id: uuid.UUID
    ) -> list[Dependency]:
        query = (
            select(Dependency)
            .where(
                Dependency.org_id == org_id,
                Dependency.is_deleted == False,  # noqa: E712
            )
            .order_by(Dependency.name.asc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())
