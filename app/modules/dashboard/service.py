"""Read-only composition of domain analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.modules.checks.service import CheckService
from app.modules.dashboard.constants import DASHBOARD_TIMELINE_LIMIT, DASHBOARD_WINDOW_HOURS
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import (
    DashboardSummary,
    DependencyHealth,
    IncidentTimeline,
    VendorStatusResponse,
)
from app.modules.dependencies.service import DependencyService
from app.modules.incidents.service import IncidentService
from app.modules.vendors.service import VendorService


class DashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        dependencies: DependencyService,
        checks: CheckService,
        incidents: IncidentService,
        vendors: VendorService,
    ) -> None:
        self.repository = repository
        self.dependencies = dependencies
        self.checks = checks
        self.incidents = incidents
        self.vendors = vendors

    async def summary(self, org_id: UUID) -> DashboardSummary:
        dependencies = (await self.dependencies.list(org_id, 100, None)).items
        now = datetime.now(UTC)
        return DashboardSummary(
            active_dependencies=sum(item.is_active for item in dependencies),
            open_incidents=await self.incidents.open_count(org_id),
            uptime_percent=await self.checks.org_uptime(org_id, now - timedelta(hours=24)),
            alerts_today=0,
        )

    async def dependency_health(self, org_id: UUID) -> list[DependencyHealth]:
        dependencies = (await self.dependencies.list(org_id, 100, None)).items
        now = datetime.now(UTC)
        result = []
        for dependency in dependencies:
            history = await self.checks.history(
                org_id, dependency.id, now - timedelta(hours=DASHBOARD_WINDOW_HOURS), now
            )
            checks = sum(point.checks for point in history.points)
            uptime = (
                sum(point.uptime_percent * point.checks for point in history.points) / checks
                if checks
                else 0
            )
            latency = (
                sum(point.average_latency_ms * point.checks for point in history.points) / checks
                if checks
                else 0
            )
            result.append(
                DependencyHealth(
                    dependency_id=dependency.id,
                    name=dependency.name,
                    current_status="operational"
                    if uptime == 100 and checks
                    else ("degraded" if checks else "unknown"),
                    uptime_24h=uptime,
                    average_latency_ms=latency,
                    last_checked_at=history.points[-1].bucket if history.points else None,
                )
            )
        return result

    async def incident_timeline(self, org_id: UUID) -> IncidentTimeline:
        page = await self.incidents.list(org_id, DASHBOARD_TIMELINE_LIMIT, None, None, None)
        details = [await self.incidents.detail(org_id, incident.id) for incident in page.items]
        return IncidentTimeline(incidents=details)

    async def vendor_status(self, _org_id: UUID) -> VendorStatusResponse:
        return VendorStatusResponse(vendors=await self.vendors.list())
