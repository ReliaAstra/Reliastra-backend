"""Incident API and correlation contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.incidents.constants import (
    CorrelationMethod,
    IncidentSeverity,
    IncidentStatus,
    RootCause,
)


class IncidentUpdateRequest(BaseModel):
    status: IncidentStatus | None = None
    severity: IncidentSeverity | None = None
    root_cause: RootCause | None = None
    description: str | None = Field(default=None, max_length=10000)


class ManualCorrelationRequest(BaseModel):
    correlated_dependency_id: UUID
    confidence: float = Field(default=1.0, ge=0, le=1)


class CorrelationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    correlated_dependency_id: UUID
    correlation_confidence: float
    time_window_seconds: int
    correlation_method: CorrelationMethod
    created_at: datetime


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    dependency_id: UUID
    started_at: datetime
    resolved_at: datetime | None
    severity: IncidentSeverity
    status: IncidentStatus
    root_cause: RootCause
    description: str | None
    evidence_report_id: UUID | None
    created_at: datetime
    updated_at: datetime


class IncidentDetailResponse(IncidentResponse):
    correlations: list[CorrelationResponse] = []
