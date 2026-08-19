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

router = APIRouter(prefix="/v1/ai-providers", tags=["AI Providers"])


def get_ai_service() -> AIService:
    return ai_service


@router.get("", response_model=list[AIProviderResponse])
async def list_ai_providers(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> list[AIProviderResponse]:
    return await service.list_providers(db, current_org.id)


@router.post(
    "",
    response_model=AIProviderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_ai_provider(
    request: AIProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> AIProviderResponse:
    return await service.create_provider(db, current_org.id, request)


@router.patch(
    "/{provider_id}",
    response_model=AIProviderResponse,
    dependencies=[Depends(require_admin)],
)
async def update_ai_provider(
    provider_id: uuid.UUID,
    request: AIProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> AIProviderResponse:
    return await service.update_provider(db, current_org.id, provider_id, request)


@router.post(
    "/{provider_id}/test",
    dependencies=[Depends(require_admin)],
)
async def test_ai_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> dict[str, str]:
    """Validate connectivity and credentials for a stored provider.

    Useful after creation to surface auth/endpoint errors immediately
    instead of waiting for the next incident's evidence generation.
    """
    result = await service.test_provider(db, current_org.id, provider_id)
    # Don't leak raw provider output — just confirm success.
    status_msg = "ok" if result.get("text") is not None else "ok (empty response)"
    return {"status": status_msg}


@router.delete(
    "/{provider_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_ai_provider(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: AIService = Depends(get_ai_service),
) -> None:
    await service.delete_provider(db, current_org.id, provider_id)
