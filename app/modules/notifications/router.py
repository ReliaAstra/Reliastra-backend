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
    prefix="/v1/orgs/{org_id}/notifications", tags=["Notifications"]
)


def get_notif_service() -> NotificationService:
    return notification_service


@router.get("/configs", response_model=list[AlertConfigResponse])
async def list_alert_configs(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> list[AlertConfigResponse]:
    return await service.list_configs(db, org_id)


@router.post(
    "/configs",
    response_model=AlertConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_member)],
)
async def create_alert_config(
    org_id: uuid.UUID,
    request: AlertConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertConfigResponse:
    return await service.create_config(db, org_id, request)


@router.get("/configs/{config_id}", response_model=AlertConfigResponse)
async def get_alert_config(
    org_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertConfigResponse:
    return await service.get_config(db, org_id, config_id)


@router.patch(
    "/configs/{config_id}",
    response_model=AlertConfigResponse,
    dependencies=[Depends(require_member)],
)
async def update_alert_config(
    org_id: uuid.UUID,
    config_id: uuid.UUID,
    request: AlertConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertConfigResponse:
    return await service.update_config(db, org_id, config_id, request)


@router.delete(
    "/configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_member)],
)
async def delete_alert_config(
    org_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> None:
    await service.delete_config(db, org_id, config_id)


@router.post(
    "/test",
    response_model=AlertTestResponse,
    dependencies=[Depends(require_member)],
)
async def send_test_notification(
    org_id: uuid.UUID,
    request: AlertTestRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: NotificationService = Depends(get_notif_service),
) -> AlertTestResponse:
    return await service.send_test_alert(db, org_id, request.config_id)
