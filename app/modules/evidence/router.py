"""Evidence report listing, download, and regeneration routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.permissions import Role
from app.dependencies import OrgContext, get_evidence_service, org_context
from app.modules.evidence.schemas import EvidenceQueuedResponse, EvidenceReportResponse
from app.modules.evidence.service import EvidenceService

router = APIRouter(tags=["evidence"])


@router.get("/v1/orgs/{org_id}/evidence/", response_model=list[EvidenceReportResponse])
async def list_evidence(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: EvidenceService = Depends(get_evidence_service),
) -> list[EvidenceReportResponse]:
    return await service.list(org_id)


@router.get("/v1/orgs/{org_id}/evidence/{report_id}", response_model=EvidenceReportResponse)
async def get_evidence(
    org_id: UUID,
    report_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceReportResponse:
    return await service.get(org_id, report_id)


@router.post(
    "/v1/orgs/{org_id}/evidence/{report_id}/regenerate",
    response_model=EvidenceQueuedResponse,
    status_code=202,
)
async def regenerate_evidence(
    org_id: UUID,
    report_id: UUID,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceQueuedResponse:
    return await service.regenerate(org_id, report_id)


@router.get(
    "/v1/orgs/{org_id}/incidents/{inc_id}/evidence",
    response_model=EvidenceReportResponse | EvidenceQueuedResponse,
    status_code=202,
)
async def incident_evidence(
    org_id: UUID,
    inc_id: UUID,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceReportResponse | EvidenceQueuedResponse:
    return await service.get_or_trigger(org_id, inc_id)
