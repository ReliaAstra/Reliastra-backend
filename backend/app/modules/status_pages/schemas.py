from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StatusComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    display_name: str
    status: str
    description: str | None = None
    uptime_30d: float


class StatusIncidentUpdate(BaseModel):
    status: str
    message: str
    timestamp: datetime


class StatusIncidentItem(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    started_at: datetime
    updates: list[StatusIncidentUpdate]


class PublicStatusResponse(BaseModel):
    overall_status: str
    components: list[StatusComponentResponse]
    active_incidents: list[StatusIncidentItem]
    last_updated: datetime
    refresh_interval_seconds: int = 60


class StatusPageConfigRequest(BaseModel):
    slug: str
    title: str
    show_uptime_graph: bool = True
    show_incident_history: bool = True
    branding: dict | None = None
    allowed_domains: list[str] | None = None


class StatusPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    show_uptime_graph: bool
    show_incident_history: bool
    branding: dict | None = None
    allowed_domains: list[str] | None = None
    is_active: bool
