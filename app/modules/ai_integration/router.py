import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_org, require_admin
from app.modules.ai_integration.schemas import (
    AIProviderCreateRequest,
    AIProviderResponse,
    AIProviderUpdateRequest,
)
from app.modules.ai_integration.service import AIService, ai_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1/orgs/{org_id}/ai-providers", tags=["AI Providers"])


def get_ai_service() -> AIService:
    return ai_service


@router.get("", response_model=list[AIProviderResponse])
async def list_ai_providers(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> list[AIProviderResponse]:
    return await service.list_providers(db, org_id)


@router.post(
    "",
    response_model=AIProviderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_ai_provider(
    org_id: uuid.UUID,
    request: AIProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> AIProviderResponse:
    return await service.create_provider(db, org_id, request)


@router.patch(
    "/{provider_id}",
    response_model=AIProviderResponse,
    dependencies=[Depends(require_admin)],
)
async def update_ai_provider(
    org_id: uuid.UUID,
    provider_id: uuid.UUID,
    request: AIProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> AIProviderResponse:
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
    service: AIService = Depends(get_ai_service),
) -> None:
    await service.delete_provider(db, org_id, provider_id)
