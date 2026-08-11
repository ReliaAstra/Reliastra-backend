"""Notification configuration and alert payload contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.notifications.constants import ChannelType


class AlertPayload(BaseModel):
    org_id: UUID
    incident_id: UUID | None = None
    severity: str
    title: str
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AlertConfigCreateRequest(BaseModel):
    channel_type: ChannelType
    config: dict[str, Any]
    is_active: bool = True


class AlertConfigUpdateRequest(BaseModel):
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class AlertConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    channel_type: ChannelType
    config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TestAlertRequest(BaseModel):
    config_id: UUID


class NotificationResult(BaseModel):
    config_id: UUID
    delivered: bool
