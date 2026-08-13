import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict
from app.modules.notifications.constants import ChannelType


class AlertPayload(BaseModel):
    org_id: uuid.UUID
    incident_id: uuid.UUID | None = None
    severity: str
    title: str
    body: str
    metadata: dict[str, Any] = {}


class AlertConfigCreateRequest(BaseModel):
    channel_type: ChannelType
    config: dict[str, Any]
    is_active: bool = True


class AlertConfigUpdateRequest(BaseModel):
    channel_type: ChannelType | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class AlertConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    channel_type: str
    config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AlertTestRequest(BaseModel):
    config_id: uuid.UUID


class AlertTestResponse(BaseModel):
    success: bool
    message: str
