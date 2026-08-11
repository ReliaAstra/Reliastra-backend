import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org, require_member
from app.db.session import get_db
from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
    DependencyHistoryResponse,
    DependencyResponse,
    DependencyUpdateRequest,
)
from app.modules.dependencies.service import DependencyService, dependency_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}/dependencies", tags=["Dependencies"])


def get_dep_service() -> DependencyService:
    return dependency_service


@router.get("", response_model=list[DependencyResponse])
async def list_dependencies(
    org_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> list[DependencyResponse]:
    return await service.list_dependencies(db, org_id, limit=limit)


@router.post(
    "",
    response_model=DependencyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def create_dependency(
    org_id: uuid.UUID,
    request: DependencyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyResponse:
    return await service.create_dependency(db, org_id, request)


@router.get("/{dep_id}", response_model=DependencyResponse)
async def get_dependency(
    org_id: uuid.UUID,
    dep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyResponse:
    return await service.get_dependency(db, org_id, dep_id)


@router.patch(
    "/{dep_id}",
    response_model=DependencyResponse,
    dependencies=[Depends(require_member)],
)
async def update_dependency(
    org_id: uuid.UUID,
    dep_id: uuid.UUID,
    request: DependencyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyResponse:
    return await service.update_dependency(db, org_id, dep_id, request)


@router.delete(
    "/{dep_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_member)],
)
async def delete_dependency(
    org_id: uuid.UUID,
    dep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> None:
    await service.delete_dependency(db, org_id, dep_id)


@router.get("/{dep_id}/results", response_model=list[Any])
async def get_dependency_check_results(
    org_id: uuid.UUID,
    dep_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> list[Any]:
    # First verify dependency belongs to org
    await service.get_dependency(db, org_id, dep_id)
    from app.modules.checks.service import check_service
    return await check_service.list_results_for_dependency(db, dep_id, limit=limit)


@router.get("/{dep_id}/history", response_model=DependencyHistoryResponse)
async def get_dependency_history(
    org_id: uuid.UUID,
    dep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyHistoryResponse:
    return await service.get_dependency_history(db, org_id, dep_id)
