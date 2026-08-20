from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, ConfigDict, HttpUrl


class WebhookEvent(str, Enum):
    incident_opened = "incident.opened"
    incident_updated = "incident.updated"
    incident_resolved = "incident.resolved"
    vendor_degraded = "vendor.degraded"
    vendor_down = "vendor.down"
    vendor_recovered = "vendor.recovered"
    evidence_ready = "evidence.ready"
    sla_breach = "sla.breach"
    check_failed = "check.failed"


class WebhookCreateRequest(BaseModel):
    name: str
    url: HttpUrl
    events: list[WebhookEvent]
    headers: dict[str, str] | None = None
    secret: str | None = None
    is_active: bool = True


class WebhookUpdateRequest(BaseModel):
    name: str | None = None
    url: HttpUrl | None = None
    events: list[WebhookEvent] | None = None
    headers: dict[str, str] | None = None
    secret: str | None = None
    is_active: bool | None = None


class WebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url_masked: str
    events: list[str]
    is_active: bool
    secret_preview: str | None
    failure_count: int
    last_delivery_at: datetime | None
    created_at: datetime


class WebhookTestRequest(BaseModel):
    event: str = "incident.opened"


class WebhookTestResponse(BaseModel):
    success: bool
    status_code: int | None
    response_body: str | None
    latency_ms: float


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    status: str
    response_status_code: int | None
    attempt_count: int
    created_at: datetime
    delivered_at: datetime | None
