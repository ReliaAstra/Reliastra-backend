"""Nested check result and history routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.pagination import Page
from app.core.permissions import Role
from app.dependencies import OrgContext, get_check_service, org_context
from app.modules.checks.schemas import CheckResultResponse, DependencyHistoryResponse
from app.modules.checks.service import CheckService

router = APIRouter(prefix="/v1/orgs/{org_id}/dependencies/{dep_id}", tags=["checks"])


@router.get("/results", response_model=Page[CheckResultResponse])
async def list_results(
    org_id: UUID,
    dep_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: UUID | None = None,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: CheckService = Depends(get_check_service),
) -> Page[CheckResultResponse]:
    end = end or datetime.now(UTC)
    return await service.list_results(
        org_id, dep_id, start or end - timedelta(days=1), end, limit, cursor
    )


@router.get("/history", response_model=DependencyHistoryResponse)
async def history(
    org_id: UUID,
    dep_id: UUID,
    start: datetime | None = None,
    end: datetime | None = None,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: CheckService = Depends(get_check_service),
) -> DependencyHistoryResponse:
    end = end or datetime.now(UTC)
    return await service.history(org_id, dep_id, start or end - timedelta(days=1), end)
