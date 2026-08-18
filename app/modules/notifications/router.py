import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org, require_admin, require_member
from app.db.session import get_db
from app.modules.notifications.schemas import (
    AlertConfigCreateRequest,
    AlertConfigResponse,
    AlertConfigUpdateRequest,
    AlertTestRequest,
    AlertTestResponse,
)
from app.modules.notifications.service import (
    NotificationService,
    notification_service,
)
from app.modules.organizations.models import Organization

router = APIRouter(
    prefix="/v1/notifications", tags=["Notifications"]
)


def get_notif_service() -> NotificationService:
    return notification_service


@router.get("/configs", response_model=list[AlertConfigResponse])
async def list_alert_configs(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> list[AlertConfigResponse]:
    return await service.list_configs(db, current_org.id)


@router.post(
    "/configs",
    response_model=AlertConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def create_alert_config(
    request: AlertConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertConfigResponse:
    return await service.create_config(db, current_org.id, request)


@router.get("/configs/{config_id}", response_model=AlertConfigResponse)
async def get_alert_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertConfigResponse:
    return await service.get_config(db, current_org.id, config_id)


@router.patch(
    "/configs/{config_id}",
    response_model=AlertConfigResponse,
    dependencies=[Depends(require_member)],
)
async def update_alert_config(
    config_id: uuid.UUID,
    request: AlertConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertConfigResponse:
    return await service.update_config(db, current_org.id, config_id, request)


@router.delete(
    "/configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_member)],
)
async def delete_alert_config(
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> None:
    await service.delete_config(db, current_org.id, config_id)


@router.post(
    "/test",
    response_model=AlertTestResponse,
    dependencies=[Depends(require_member)],
)
async def send_test_notification(
    request: AlertTestRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertTestResponse:
    return await service.send_test_alert(db, current_org.id, request.config_id)
