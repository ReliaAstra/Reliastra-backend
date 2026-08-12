from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.infrastructure.storage import storage_client
from app.modules.verification.schemas import (
    VerificationEvidenceResponse,
    VerificationHashResponse,
    VerificationResponse,
)
from app.modules.verification.service import VerificationService, verification_service

router = APIRouter(prefix="/v1/verify", tags=["Evidence Verification"])


def get_verification_service() -> VerificationService:
    return verification_service


@router.get("/{verification_id}", response_model=VerificationResponse)
async def verify_evidence(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationResponse:
    return await service.verify(db, verification_id)


@router.get("/{verification_id}/hash", response_model=VerificationHashResponse)
async def verify_evidence_hash(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationHashResponse:
    return await service.get_hash(db, verification_id)


@router.get("/{verification_id}/evidence", response_model=VerificationEvidenceResponse)
async def get_verification_evidence(
    verification_id: str,
    db: AsyncSession = Depends(get_db),
    service: VerificationService = Depends(get_verification_service),
) -> VerificationEvidenceResponse:
    return await service.get_evidence(db, verification_id)
