import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.checks.repository import CheckRepository
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import (
    DashboardSummaryResponse,
    DependencyHealthResponse,
)
from app.modules.incidents.schemas import IncidentDetailResponse
from app.modules.incidents.service import incident_service
from app.modules.vendors.schemas import VendorDetailResponse
from app.modules.vendors.service import vendor_service


class DashboardService:
    def __init__(
        self, repository: DashboardRepository = DashboardRepository()
    ) -> None:
        self.repository = repository

    async def get_summary(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> DashboardSummaryResponse:
        stats = await self.repository.get_summary_stats(session, org_id)
        return DashboardSummaryResponse.model_validate(stats)

    async def get_dependency_health(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[DependencyHealthResponse]:
        deps = await self.repository.list_active_dependencies(session, org_id)
        result: list[DependencyHealthResponse] = []
        for dep in deps:
            stats = await CheckRepository.get_aggregated_stats(
                session, dep.id, window_hours=24
            )
            up_pct = stats.get("uptime_percentage", 100.0)
            status = "operational" if up_pct >= 99.0 else "degraded"
            if not dep.is_active:
                status = "paused"
            result.append(
                DependencyHealthResponse(
                    dependency_id=dep.id,
                    name=dep.name,
                    endpoint_url=dep.endpoint_url,
                    current_status=status,
                    uptime_percentage_24h=up_pct,
                    avg_latency_ms_24h=stats.get("avg_latency_ms", 0.0),
                )
            )
        return result

    async def get_incident_timeline(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[IncidentDetailResponse]:
        incidents = await incident_service.list_incidents(
            session, org_id, limit=20
        )
        detailed_list: list[IncidentDetailResponse] = []
        for inc in incidents:
            detail = await incident_service.get_incident_detail(
                session, org_id, inc.id
            )
            detailed_list.append(detail)
        return detailed_list

    async def get_vendor_status(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[VendorDetailResponse]:
        vendors = await vendor_service.list_public_vendors(session)
        result: list[VendorDetailResponse] = []
        for v in vendors:
            detail = await vendor_service.get_vendor_detail(
                session, v.vendor_name
            )
            result.append(detail)
        return result


dashboard_service = DashboardService()
