from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import SlidingWindowRateLimiter, enforce_rate_limit
from app.db.session import get_db
from app.dependencies import get_current_org, get_current_user, require_admin
from app.modules.evidence_gate.schemas import (
    EvidenceGateRequest,
    EvidenceGateResponse,
    EvidenceGateStats,
    PublicIncidentResponse,
    PublicizeEvidenceRequest,
    PublicizeResponse,
)
from app.modules.evidence_gate.service import EvidenceGateService, evidence_gate_service
from app.modules.organizations.models import Organization
from app.modules.users.models import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Evidence Gate"])

# Rate limiters for the public gate endpoint
_gate_ip_limiter = SlidingWindowRateLimiter(
    limit=5, window_seconds=60, key_prefix="rl_gate_ip"
)
_gate_email_limiter = SlidingWindowRateLimiter(
    limit=3, window_seconds=60, key_prefix="rl_gate_email"
)


def get_evidence_gate_service() -> EvidenceGateService:
    return evidence_gate_service


# ------------------------------------------------------------------
# Public endpoints (no auth required)
# ------------------------------------------------------------------


@router.get(
    "/v1/vendors/{vendor_name}/incidents/public",
    response_model=list[PublicIncidentResponse],
)
async def list_public_incidents(
    vendor_name: str,
    db: AsyncSession = Depends(get_db),
    service: EvidenceGateService = Depends(get_evidence_gate_service),
) -> list[PublicIncidentResponse]:
    """List public incidents with evidence reports for a vendor."""
    return await service.list_public_incidents(db, vendor_name)


@router.post(
    "/v1/evidence/gate",
    response_model=EvidenceGateResponse,
    status_code=status.HTTP_200_OK,
)
async def process_evidence_gate(
    request: Request,
    body: EvidenceGateRequest,
    db: AsyncSession = Depends(get_db),
    service: EvidenceGateService = Depends(get_evidence_gate_service),
) -> EvidenceGateResponse:
    """Process evidence gate: gate a download behind email capture (lead magnet)."""
    # Rate limit by IP (5/min)
    await enforce_rate_limit(request, _gate_ip_limiter)
    # Rate limit by email (3/min)
    await enforce_rate_limit(request, _gate_email_limiter, identifier=str(body.email).lower())

    client = request.client
    client_ip = client.host if client else None
    user_agent = request.headers.get("user-agent")

    return await service.process_gate(db, body, client_ip, user_agent)


@router.get(
    "/v1/evidence/{report_token}/download",
    status_code=status.HTTP_200_OK,
)
async def download_public_evidence(
    report_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    service: EvidenceGateService = Depends(get_evidence_gate_service),
) -> Response:
    """Download a gated evidence report using a signed token."""
    client = request.client
    client_ip = client.host if client else None
    user_agent = request.headers.get("user-agent")

    file_bytes, filename = await service.download_evidence(
        db, report_token, client_ip, user_agent
    )

    return StreamingResponse(
        iter([file_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(file_bytes)),
        },
    )


# ------------------------------------------------------------------
# Authenticated endpoints (Owner/Admin)
# ------------------------------------------------------------------


@router.post(
    "/v1/evidence/publicize",
    response_model=PublicizeResponse,
    dependencies=[Depends(require_admin)],
)
async def publicize_evidence(
    body: PublicizeEvidenceRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    service: EvidenceGateService = Depends(get_evidence_gate_service),
) -> PublicizeResponse:
    """Make an evidence report public (or private)."""
    return await service.publicize_evidence(
        db, current_org.id, current_user.id, body
    )


@router.get(
    "/v1/evidence/stats",
    response_model=EvidenceGateStats,
    dependencies=[Depends(require_admin)],
)
async def get_evidence_gate_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: EvidenceGateService = Depends(get_evidence_gate_service),
) -> EvidenceGateStats:
    """Get evidence gate conversion statistics."""
    # Stats are global for now; in future, could filter by org
    return await service.get_stats(db, current_user.id)
