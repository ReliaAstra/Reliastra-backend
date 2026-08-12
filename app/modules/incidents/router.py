import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org, require_member
from app.db.session import get_db
from app.modules.incidents.constants import IncidentSeverity, IncidentStatus
from app.modules.incidents.schemas import (
    IncidentCorrelateRequest,
    IncidentCorrelationResponse,
    IncidentDetailResponse,
    IncidentResponse,
    IncidentUpdateRequest,
)
from app.modules.incidents.service import IncidentService, incident_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}/incidents", tags=["Incidents"])


def get_inc_service() -> IncidentService:
    return incident_service


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    org_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    status: IncidentStatus | None = Query(default=None),
    severity: IncidentSeverity | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> list[IncidentResponse]:
    return await service.list_incidents(
        db, org_id, limit=limit, status=status.value if status else None, severity=severity.value if severity else None
    )


@router.get("/{inc_id}", response_model=IncidentDetailResponse)
async def get_incident(
    org_id: uuid.UUID,
    inc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> IncidentDetailResponse:
    return await service.get_incident_detail(db, org_id, inc_id)


@router.patch(
    "/{inc_id}",
    response_model=IncidentResponse,
    dependencies=[Depends(require_member)],
)
async def update_incident(
    org_id: uuid.UUID,
    inc_id: uuid.UUID,
    request: IncidentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> IncidentResponse:
    return await service.update_incident(db, org_id, inc_id, request)


@router.post(
    "/{inc_id}/correlate",
    response_model=IncidentCorrelationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def correlate_incident(
    org_id: uuid.UUID,
    inc_id: uuid.UUID,
    request: IncidentCorrelateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> IncidentCorrelationResponse:
    return await service.manually_correlate(db, org_id, inc_id, request)


@router.get("/{inc_id}/evidence", response_model=dict[str, Any])
async def get_incident_evidence(
    org_id: uuid.UUID,
    inc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> dict[str, Any]:
    return await service.get_or_trigger_evidence(db, org_id, inc_id)
