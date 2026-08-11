"""Public vendor status contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VendorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_name: str
    display_name: str
    endpoint_url: str
    category: str
    last_check_at: datetime | None
    status: Literal["operational", "degraded", "unknown"] = "unknown"


class VendorHistoryPoint(BaseModel):
    timestamp: datetime
    latency_ms: float
    is_up: bool


class VendorHistoryResponse(BaseModel):
    vendor_name: str
    from_time: datetime
    to_time: datetime
    uptime_percent: float
    points: list[VendorHistoryPoint]
