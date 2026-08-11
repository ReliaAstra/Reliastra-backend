"""Monitored dependency CRUD routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.pagination import Page
from app.core.permissions import Role
from app.dependencies import OrgContext, get_dependency_service, org_context
from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
    DependencyResponse,
    DependencyUpdateRequest,
)
from app.modules.dependencies.service import DependencyService

router = APIRouter(prefix="/v1/orgs/{org_id}/dependencies", tags=["dependencies"])


@router.get("/", response_model=Page[DependencyResponse])
async def list_dependencies(
    org_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    cursor: UUID | None = None,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: DependencyService = Depends(get_dependency_service),
) -> Page[DependencyResponse]:
    return await service.list(org_id, limit, cursor)


@router.post("/", response_model=DependencyResponse, status_code=201)
async def create_dependency(
    org_id: UUID,
    payload: DependencyCreateRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: DependencyService = Depends(get_dependency_service),
) -> DependencyResponse:
    return await service.create(org_id, payload)


@router.get("/{dep_id}", response_model=DependencyResponse)
async def get_dependency(
    org_id: UUID,
    dep_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: DependencyService = Depends(get_dependency_service),
) -> DependencyResponse:
    return await service.get(org_id, dep_id)


@router.patch("/{dep_id}", response_model=DependencyResponse)
async def update_dependency(
    org_id: UUID,
    dep_id: UUID,
    payload: DependencyUpdateRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: DependencyService = Depends(get_dependency_service),
) -> DependencyResponse:
    return await service.update(org_id, dep_id, payload)


@router.delete("/{dep_id}", status_code=204)
async def delete_dependency(
    org_id: UUID,
    dep_id: UUID,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: DependencyService = Depends(get_dependency_service),
) -> Response:
    await service.delete(org_id, dep_id)
    return Response(status_code=204)
