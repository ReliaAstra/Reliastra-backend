"""Read-only dashboard analytics routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.permissions import Role
from app.dependencies import OrgContext, get_dashboard_service, org_context
from app.modules.dashboard.schemas import (
    DashboardSummary,
    DependencyHealth,
    IncidentTimeline,
    VendorStatusResponse,
)
from app.modules.dashboard.service import DashboardService

router = APIRouter(prefix="/v1/orgs/{org_id}/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardSummary:
    return await service.summary(org_id)


@router.get("/dependency-health", response_model=list[DependencyHealth])
async def dependency_health(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[DependencyHealth]:
    return await service.dependency_health(org_id)


@router.get("/incident-timeline", response_model=IncidentTimeline)
async def incident_timeline(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: DashboardService = Depends(get_dashboard_service),
) -> IncidentTimeline:
    return await service.incident_timeline(org_id)


@router.get("/vendor-status", response_model=VendorStatusResponse)
async def vendor_status(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: DashboardService = Depends(get_dashboard_service),
) -> VendorStatusResponse:
    return await service.vendor_status(org_id)
