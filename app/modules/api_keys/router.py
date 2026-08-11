import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org, require_admin
from app.db.session import get_db
from app.modules.api_keys.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyResponse,
)
from app.modules.api_keys.service import ApiKeyService, api_key_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}/api-keys", tags=["API Keys"])


def get_api_key_service() -> ApiKeyService:
    return api_key_service


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: ApiKeyService = Depends(get_api_key_service),
) -> list[ApiKeyResponse]:
    return await service.list_keys(db, org_id)


@router.post(
    "",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_api_key(
    org_id: uuid.UUID,
    request: ApiKeyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: ApiKeyService = Depends(get_api_key_service),
) -> ApiKeyCreateResponse:
    return await service.create_key(db, org_id, request)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def revoke_api_key(
    org_id: uuid.UUID,
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: ApiKeyService = Depends(get_api_key_service),
) -> None:
    await service.revoke_key(db, org_id, key_id)
