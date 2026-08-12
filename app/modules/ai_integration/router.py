import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org, require_admin
from app.db.session import get_db
from app.modules.ai_integration.schemas import (
    AiProviderCreateRequest,
    AiProviderResponse,
    AiProviderUpdateRequest,
)
from app.modules.ai_integration.service import AiService, ai_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}/ai-providers", tags=["AI Integration"])


def get_ai_service() -> AiService:
    return ai_service


@router.get(
    "",
    response_model=list[AiProviderResponse],
    dependencies=[Depends(require_admin)],
)
async def list_ai_providers(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AiService = Depends(get_ai_service),
) -> list[AiProviderResponse]:
    return await service.list_providers(db, org_id)


@router.post(
    "",
    response_model=AiProviderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_ai_provider(
    org_id: uuid.UUID,
    request: AiProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AiService = Depends(get_ai_service),
) -> AiProviderResponse:
    return await service.create_provider(db, org_id, request)


@router.patch(
    "/{provider_id}",
    response_model=AiProviderResponse,
    dependencies=[Depends(require_admin)],
)
async def update_ai_provider(
    org_id: uuid.UUID,
    provider_id: uuid.UUID,
    request: AiProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AiService = Depends(get_ai_service),
) -> AiProviderResponse:
    return await service.update_provider(db, org_id, provider_id, request)


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_ai_provider(
    org_id: uuid.UUID,
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AiService = Depends(get_ai_service),
) -> None:
    await service.delete_provider(db, org_id, provider_id)
