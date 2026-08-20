from __future__ import annotations

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

    @classmethod
    def _redact_config(cls, config: dict[str, Any], channel_type: ChannelType) -> dict[str, Any]:
        """Validate config contains expected fields for the channel type."""
        ct = channel_type.value.lower() if isinstance(channel_type, ChannelType) else str(channel_type).lower()
        if ct == "slack" and not config.get("webhook_url"):
            raise ValueError("Slack channel config requires 'webhook_url'")
        if ct == "pagerduty" and not config.get("routing_key"):
            raise ValueError("PagerDuty channel config requires 'routing_key'")
        if ct == "webhook" and not config.get("url"):
            raise ValueError("Webhook channel config requires 'url'")
        if ct == "email" and not config.get("email") and not config.get("recipient"):
            raise ValueError("Email channel config requires 'email' or 'recipient'")
        return config

    @classmethod
    def model_validate(cls, *args: Any, **kwargs: Any) -> AlertConfigCreateRequest:
        """Override to add config validation on create."""
        instance = super().model_validate(*args, **kwargs)
        instance.config = instance._redact_config(instance.config, instance.channel_type)
        return instance


class AlertConfigUpdateRequest(BaseModel):
    channel_type: ChannelType | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class AlertConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    channel_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AlertTestRequest(BaseModel):
    config_id: uuid.UUID


class AlertTestResponse(BaseModel):
    success: bool
    message: str
