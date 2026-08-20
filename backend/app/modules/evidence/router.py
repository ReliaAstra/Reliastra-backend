import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org, require_member
from app.db.session import get_db
from app.modules.evidence.schemas import (
    EvidenceReportDownloadResponse,
    EvidenceReportResponse,
)
from app.modules.evidence.service import EvidenceService, evidence_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/evidence", tags=["Evidence"])


def get_evid_service() -> EvidenceService:
    return evidence_service


@router.get("", response_model=list[EvidenceReportResponse])
async def list_evidence_reports(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: EvidenceService = Depends(get_evid_service),
) -> list[EvidenceReportResponse]:
    return await service.list_reports(db, current_org.id, limit=limit)


@router.get("/{report_id}", response_model=EvidenceReportDownloadResponse)
async def get_evidence_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: EvidenceService = Depends(get_evid_service),
) -> EvidenceReportDownloadResponse:
    return await service.get_report_download(db, current_org.id, report_id)


@router.post(
    "/{report_id}/regenerate",
    response_model=EvidenceReportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def regenerate_evidence_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: EvidenceService = Depends(get_evid_service),
) -> EvidenceReportResponse:
    return await service.regenerate_report(db, current_org.id, report_id)
