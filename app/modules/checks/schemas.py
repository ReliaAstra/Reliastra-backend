"""Check result and history contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CheckResultCreateDTO(BaseModel):
    dependency_id: UUID
    org_id: UUID
    region: str
    executed_at: datetime
    latency_ms: float
    status_code: int | None = None
    is_up: bool
    error_message: str | None = None
    quorum_confirmed: bool = False


class CheckResultResponse(CheckResultCreateDTO):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class HistoryPoint(BaseModel):
    bucket: datetime
    uptime_percent: float = Field(ge=0, le=100)
    average_latency_ms: float
    checks: int


class DependencyHistoryResponse(BaseModel):
    dependency_id: UUID
    from_time: datetime
    to_time: datetime
    points: list[HistoryPoint]
