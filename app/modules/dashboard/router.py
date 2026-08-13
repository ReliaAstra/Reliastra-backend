import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org
from app.db.session import get_db
from app.modules.dashboard.schemas import (
    DashboardSummaryResponse,
    DependencyHealthResponse,
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
