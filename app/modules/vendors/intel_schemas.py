import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class VendorMetricsPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime
    uptime_percentage: float
    avg_latency_ms: float
    total_checks: int
    total_up: int
    total_down: int


class VendorMetricsResponse(BaseModel):
    vendor_id: uuid.UUID
    vendor_slug: str
    days: int
    metrics: list[VendorMetricsPoint]


class VendorIncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_id: uuid.UUID
    title: str
    description: str | None
    status: str
    started_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
