import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.modules.incidents.constants import (
    CorrelationMethod,
    IncidentSeverity,
    IncidentStatus,
    RootCause,
)


class IncidentCorrelationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    correlated_dependency_id: uuid.UUID
    correlation_confidence: float
    time_window_seconds: int
    correlation_method: str
    created_at: datetime


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    dependency_id: uuid.UUID
    started_at: datetime
    resolved_at: datetime | None = None
    severity: str
    status: str
    root_cause: str
    description: str | None = None
    evidence_report_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class IncidentDetailResponse(IncidentResponse):
    correlations: list[IncidentCorrelationResponse] = []


class IncidentUpdateRequest(BaseModel):
    status: IncidentStatus | None = None
    severity: IncidentSeverity | None = None
    root_cause: RootCause | None = None
    description: str | None = None


class IncidentCorrelateRequest(BaseModel):
    correlated_dependency_id: uuid.UUID
    correlation_confidence: float = 1.0
    correlation_method: CorrelationMethod = CorrelationMethod.MANUAL
    time_window_seconds: int = 300
