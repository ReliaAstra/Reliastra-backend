"""Incident lifecycle and correlation routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.pagination import Page
from app.core.permissions import Role
from app.dependencies import OrgContext, get_incident_service, org_context
from app.modules.incidents.constants import IncidentSeverity, IncidentStatus
from app.modules.incidents.schemas import (
    CorrelationResponse,
    IncidentDetailResponse,
    IncidentResponse,
    IncidentUpdateRequest,
    ManualCorrelationRequest,
)
from app.modules.incidents.service import IncidentService

router = APIRouter(prefix="/v1/orgs/{org_id}/incidents", tags=["incidents"])


@router.get("/", response_model=Page[IncidentResponse])
async def list_incidents(
    org_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    cursor: UUID | None = None,
    status: IncidentStatus | None = None,
    severity: IncidentSeverity | None = None,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: IncidentService = Depends(get_incident_service),
) -> Page[IncidentResponse]:
    return await service.list(org_id, limit, cursor, status, severity)


@router.get("/{inc_id}", response_model=IncidentDetailResponse)
async def get_incident(
    org_id: UUID,
    inc_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: IncidentService = Depends(get_incident_service),
) -> IncidentDetailResponse:
    return await service.detail(org_id, inc_id)


@router.patch("/{inc_id}", response_model=IncidentDetailResponse)
async def update_incident(
    org_id: UUID,
    inc_id: UUID,
    payload: IncidentUpdateRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: IncidentService = Depends(get_incident_service),
) -> IncidentDetailResponse:
    return await service.update(org_id, inc_id, payload)


@router.post("/{inc_id}/correlate", response_model=CorrelationResponse, status_code=201)
async def correlate(
    org_id: UUID,
    inc_id: UUID,
    payload: ManualCorrelationRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: IncidentService = Depends(get_incident_service),
) -> CorrelationResponse:
    return await service.manual_correlate(org_id, inc_id, payload)
