import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    source_type: str
    source_id: uuid.UUID | None
    org_id: uuid.UUID | None
    region: str
    endpoint_url: str
    latency_ms: float
    status_code: int | None
    response_time_ms: float | None
    tls_version: str | None
    tls_certificate_issuer: str | None
    tls_certificate_expiry: datetime | None
    error_type: str | None
    error_message: str | None
    metadata: dict[str, Any] | None = Field(
        default=None, validation_alias="observation_metadata"
    )


class ObservationCreateDTO(BaseModel):
    timestamp: datetime | None = None
    source_type: str = Field(min_length=1, max_length=50)
    source_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    region: str = Field(min_length=1, max_length=50)
    endpoint_url: str = Field(min_length=1, max_length=500)
    latency_ms: float = Field(ge=0)
    status_code: int | None = None
    response_time_ms: float | None = Field(default=None, ge=0)
    tls_version: str | None = None
    tls_certificate_issuer: str | None = None
    tls_certificate_expiry: datetime | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None


class ObservationSummaryResponse(BaseModel):
    source_type: str
    source_id: uuid.UUID | None
    endpoint_url: str
    total_observations: int
    uptime_percentage: float
    avg_latency_ms: float
    p95_latency_ms: float | None
    period_hours: int
