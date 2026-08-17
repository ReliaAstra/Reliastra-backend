import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.checks.repository import CheckRepository
from app.modules.dashboard.repository import DashboardRepository
from app.modules.dashboard.schemas import (
    DashboardSummaryResponse,
    DependencyHealthResponse,
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

    async def get_dependency_health(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[DependencyHealthResponse]:
        # FIX 22: fetch all dependencies and their 24h stats with exactly TWO
        # queries (dependency list + bulk aggregation) instead of one stats
        # query per dependency.
        deps = await self.repository.list_active_dependencies(session, org_id)
        if not deps:
            return []
        stats_map = await CheckRepository.get_aggregated_stats_bulk(
            session, [d.id for d in deps], window_hours=24
        )
        result: list[DependencyHealthResponse] = []
        for dep in deps:
            stats = stats_map.get(dep.id, {})
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
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 20,
        cursor: uuid.UUID | None = None,
    ) -> list[IncidentDetailResponse]:
        # Batched query: fetch incidents + correlations in 2 queries instead of N+1
        rows = await IncidentRepository.list_with_correlations_for_org(
            session, org_id, limit=limit, cursor=cursor
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
        # FIX 22: bulk vendor details — a single observation query across all
        # vendor endpoints instead of per-vendor detail calls.
        return await vendor_service.get_vendor_details_bulk(session)


dashboard_service = DashboardService()