from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org, get_current_user, require_admin, require_member
from app.db.session import get_db
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.modules.webhooks.schemas import (
    WebhookCreateRequest,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookTestRequest,
    WebhookTestResponse,
    WebhookUpdateRequest,
)
from app.modules.webhooks.service import WebhookService, webhook_service

webhooks_router = APIRouter(
    prefix="/v1/webhooks",
    tags=["Webhooks"],
)


def get_webhook_service() -> WebhookService:
    return webhook_service


@webhooks_router.post(
    "",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def create_webhook(
    request: WebhookCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookResponse:
    webhook = await service.create_webhook(db, current_org.id, current_user.id, request)
    return service._to_response(webhook)


@webhooks_router.get(
    "",
    response_model=list[WebhookResponse],
    dependencies=[Depends(require_member)],
)
async def list_webhooks(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: WebhookService = Depends(get_webhook_service),
) -> list[WebhookResponse]:
    return await service.list_webhooks(db, current_org.id)


@webhooks_router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_webhook(
    webhook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    current_user: User = Depends(get_current_user),
    service: WebhookService = Depends(get_webhook_service),
) -> None:
    await service.delete_webhook(db, current_org.id, webhook_id, current_user.id)


@webhooks_router.patch(
    "/{webhook_id}",
    response_model=WebhookResponse,
    dependencies=[Depends(require_member)],
)
async def update_webhook(
    webhook_id: uuid.UUID,
    request: WebhookUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookResponse:
    return await service.update_webhook(db, current_org.id, webhook_id, request)


@webhooks_router.post(
    "/{webhook_id}/test",
    response_model=WebhookTestResponse,
    dependencies=[Depends(require_member)],
)
async def test_webhook(
    webhook_id: uuid.UUID,
    request: WebhookTestRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: WebhookService = Depends(get_webhook_service),
) -> WebhookTestResponse:
    return await service.test_webhook(db, current_org.id, webhook_id, request)


@webhooks_router.get(
    "/{webhook_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
    dependencies=[Depends(require_member)],
)
async def list_deliveries(
    webhook_id: uuid.UUID,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: WebhookService = Depends(get_webhook_service),
) -> list[WebhookDeliveryResponse]:
    return await service.list_deliveries(db, current_org.id, webhook_id, status=status_filter, limit=limit)
