"""Notification configuration routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.core.permissions import Role
from app.dependencies import OrgContext, get_notification_service, org_context
from app.modules.notifications.schemas import (
    AlertConfigCreateRequest,
    AlertConfigResponse,
    AlertConfigUpdateRequest,
    NotificationResult,
    TestAlertRequest,
)
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/v1/orgs/{org_id}/notifications", tags=["notifications"])


@router.get("/configs", response_model=list[AlertConfigResponse])
async def list_configs(
    org_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: NotificationService = Depends(get_notification_service),
) -> list[AlertConfigResponse]:
    return await service.list(org_id)


@router.post("/configs", response_model=AlertConfigResponse, status_code=201)
async def create_config(
    org_id: UUID,
    payload: AlertConfigCreateRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: NotificationService = Depends(get_notification_service),
) -> AlertConfigResponse:
    return await service.create(org_id, payload)


@router.get("/configs/{config_id}", response_model=AlertConfigResponse)
async def get_config(
    org_id: UUID,
    config_id: UUID,
    _context: OrgContext = Depends(org_context(Role.VIEWER)),
    service: NotificationService = Depends(get_notification_service),
) -> AlertConfigResponse:
    return await service.get(org_id, config_id)


@router.patch("/configs/{config_id}", response_model=AlertConfigResponse)
async def update_config(
    org_id: UUID,
    config_id: UUID,
    payload: AlertConfigUpdateRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: NotificationService = Depends(get_notification_service),
) -> AlertConfigResponse:
    return await service.update(org_id, config_id, payload)


@router.delete("/configs/{config_id}", status_code=204)
async def delete_config(
    org_id: UUID,
    config_id: UUID,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: NotificationService = Depends(get_notification_service),
) -> Response:
    await service.delete(org_id, config_id)
    return Response(status_code=204)


@router.post("/test", response_model=NotificationResult)
async def test_config(
    org_id: UUID,
    payload: TestAlertRequest,
    _context: OrgContext = Depends(org_context(Role.MEMBER)),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResult:
    return await service.test(org_id, payload.config_id)
