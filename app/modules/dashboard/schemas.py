"""Aggregated dashboard response contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.incidents.schemas import IncidentDetailResponse
from app.modules.vendors.schemas import VendorResponse


class DashboardSummary(BaseModel):
    active_dependencies: int
    open_incidents: int
    uptime_percent: float = Field(ge=0, le=100)
    alerts_today: int


class DependencyHealth(BaseModel):
    dependency_id: UUID
    name: str
    current_status: str
    uptime_24h: float
    average_latency_ms: float
    last_checked_at: datetime | None


class IncidentTimeline(BaseModel):
    incidents: list[IncidentDetailResponse]


class VendorStatusResponse(BaseModel):
    vendors: list[VendorResponse]
