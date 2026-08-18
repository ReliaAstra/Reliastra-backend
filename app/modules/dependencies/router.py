import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.pagination import PaginatedResponse, DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, slice_page
from app.dependencies import get_current_org, require_admin
from app.db.session import get_db
from app.modules.checks.schemas import CheckResultResponse
from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
    DependencyHistoryResponse,
    DependencyResponse,
    DependencyUpdateRequest,
)
from app.modules.dependencies.service import DependencyService, dependency_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/dependencies", tags=["Dependencies"])


def get_dep_service() -> DependencyService:
    return dependency_service


@router.get("", response_model=PaginatedResponse[DependencyResponse])
async def list_dependencies(
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> PaginatedResponse[DependencyResponse]:
    cursor_uuid = uuid.UUID(cursor) if cursor else None
    rows = await service.list_dependencies(
        db, current_org.id, limit=limit + 1, cursor=cursor_uuid
    )
    return slice_page(rows, limit)


@router.post(
    "",
    response_model=DependencyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_dependency(
    request: DependencyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyResponse:
    return await service.create_dependency(db, current_org.id, request)


@router.get("/{dep_id}", response_model=DependencyResponse)
async def get_dependency(
    dep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyResponse:
    return await service.get_dependency(db, current_org.id, dep_id)


@router.patch(
    "/{dep_id}",
    response_model=DependencyResponse,
    dependencies=[Depends(require_admin)],
)
async def update_dependency(
    dep_id: uuid.UUID,
    request: DependencyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyResponse:
    return await service.update_dependency(db, current_org.id, dep_id, request)


@router.delete(
    "/{dep_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_dependency(
    dep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> None:
    await service.delete_dependency(db, current_org.id, dep_id)


@router.get("/{dep_id}/results", response_model=PaginatedResponse[CheckResultResponse])
async def get_dependency_check_results(
    dep_id: uuid.UUID,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    cursor: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> PaginatedResponse[CheckResultResponse]:
    await service.get_dependency(db, current_org.id, dep_id)
    from app.modules.checks.service import check_service
    rows = await check_service.list_results_for_dependency(db, dep_id, limit=limit + 1)
    return slice_page(rows, limit)


@router.get("/{dep_id}/history", response_model=DependencyHistoryResponse)
async def get_dependency_history(
    dep_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: DependencyService = Depends(get_dep_service),
) -> DependencyHistoryResponse:
    return await service.get_dependency_history(db, current_org.id, dep_id)
