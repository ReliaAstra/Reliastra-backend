import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org
from app.db.session import get_db
from app.modules.dashboard.schemas import (
    DashboardSummaryResponse,
    DependencyHealthResponse,
    LatencyPointResponse,
    SLADegradationResponse,
)
from app.modules.dashboard.service import DashboardService, dashboard_service
from app.modules.incidents.schemas import IncidentDetailResponse
from app.modules.organizations.models import Organization
from app.modules.vendors.schemas import VendorDetailResponse

router = APIRouter(prefix="/v1/orgs/{org_id}/dashboard", tags=["Dashboard"])


def get_dash_service() -> DashboardService:
    return dashboard_service


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DashboardService = Depends(get_dash_service),
) -> DashboardSummaryResponse:
    return await service.get_summary(db, org_id)


@router.get("/latency", response_model=list[LatencyPointResponse])
async def get_latency_timeseries(
    org_id: uuid.UUID,
    hours: int = Query(default=24, ge=1, le=2160),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
) -> list[LatencyPointResponse]:
    """Return organization-scoped latency observations for charting."""
    from app.modules.observations.repository import ObservationRepository

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    observations = await ObservationRepository.list_for_org(
        db, org_id, since=since, limit=500
    )
    return [
        LatencyPointResponse(
            timestamp=item.timestamp,
            region=item.region,
            latency_ms=item.latency_ms,
            dependency_id=item.source_id,
        )
        for item in reversed(observations)
        if item.source_type == "customer_check"
    ]


@router.get("/sla-degradation", response_model=SLADegradationResponse)
async def get_sla_degradation(
    org_id: uuid.UUID,
    period_days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
) -> SLADegradationResponse:
    """Aggregate observed degradation per dependency for the requested period."""
    from app.modules.observations.repository import ObservationRepository

    stats = await ObservationRepository.get_sla_degradation(
        db, org_id, period_days
    )
    return SLADegradationResponse(
        total_degradation_pct=stats["total_degradation_pct"],
        affected_services=stats["affected_services"],
        period=f"{period_days}d",
    )


@router.get("/dependency-health", response_model=list[DependencyHealthResponse])
async def get_dependency_health(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DashboardService = Depends(get_dash_service),
) -> list[DependencyHealthResponse]:
    return await service.get_dependency_health(db, org_id)


@router.get("/incident-timeline", response_model=list[IncidentDetailResponse])
async def get_incident_timeline(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DashboardService = Depends(get_dash_service),
) -> list[IncidentDetailResponse]:
    return await service.get_incident_timeline(db, org_id)


@router.get("/vendor-status", response_model=list[VendorDetailResponse])
async def get_vendor_status(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DashboardService = Depends(get_dash_service),
) -> list[VendorDetailResponse]:
    return await service.get_vendor_status(db, org_id)
