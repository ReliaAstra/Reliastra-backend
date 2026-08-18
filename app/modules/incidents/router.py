import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query, status
from app.modules.evidence.schemas import EvidenceReportResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org, require_admin
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

router = APIRouter(prefix="/v1/incidents", tags=["Incidents"])


def get_inc_service() -> IncidentService:
    return incident_service


@router.get("", response_model=PaginatedResponse[IncidentResponse])
async def list_incidents(
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    status: IncidentStatus | None = Query(default=None),
    severity: IncidentSeverity | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> PaginatedResponse[IncidentResponse]:
    rows = await service.list_incidents(
        db,
        current_org.id,
        limit=limit + 1,
        status=status.value if status else None,
        severity=severity.value if severity else None,
    )
    return slice_page(rows, limit)


@router.get("/{inc_id}", response_model=IncidentDetailResponse)
async def get_incident(
    inc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> IncidentDetailResponse:
    return await service.get_incident_detail(db, current_org.id, inc_id)


@router.patch(
    "/{inc_id}",
    response_model=IncidentResponse,
    dependencies=[Depends(require_admin)],
)
async def update_incident(
    inc_id: uuid.UUID,
    request: IncidentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> IncidentResponse:
    return await service.update_incident(db, current_org.id, inc_id, request)


@router.post(
    "/{inc_id}/correlate",
    response_model=IncidentCorrelationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def correlate_incident(
    inc_id: uuid.UUID,
    request: IncidentCorrelateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> IncidentCorrelationResponse:
    return await service.manually_correlate(db, current_org.id, inc_id, request)


@router.get("/{inc_id}/evidence", response_model=EvidenceReportResponse)
async def get_incident_evidence(
    inc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: IncidentService = Depends(get_inc_service),
) -> EvidenceReportResponse:
    return await service.get_or_trigger_evidence(db, current_org.id, inc_id)
