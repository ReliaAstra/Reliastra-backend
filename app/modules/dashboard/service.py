import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.checks.repository import CheckRepository
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import (
    DashboardSummaryResponse,
    DependencyHealthResponse,
    LatencyPointResponse,
    SLADegradationResponse,
)
from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.schemas import (
    IncidentCorrelationResponse,
    IncidentDetailResponse,
    IncidentResponse,
)
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

    async def get_latency(
        self, session: AsyncSession, org_id: uuid.UUID, hours: int = 24
    ) -> list[LatencyPointResponse]:
        rows = await self.repository.get_latency_series(session, org_id, hours=hours)
        return [LatencyPointResponse(**r) for r in rows]

    async def get_sla_degradation(
        self, session: AsyncSession, org_id: uuid.UUID, days: int = 30
    ) -> SLADegradationResponse:
        data = await self.repository.get_sla_degradation(
            session, org_id, period_days=days
        )
        return SLADegradationResponse(**data)

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
        # Batched query: fetch incidents + correlations in 2 queries instead of N+1
        rows = await IncidentRepository.list_with_correlations_for_org(
            session, org_id, limit=20
        )
        detailed_list: list[IncidentDetailResponse] = []
        for row in rows:
            inc = row["incident"]
            correlations = row["correlations"]
            data = IncidentResponse.model_validate(inc).model_dump()
            data["correlations"] = [
                IncidentCorrelationResponse.model_validate(c) for c in correlations
            ]
            detailed_list.append(IncidentDetailResponse.model_validate(data))
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
