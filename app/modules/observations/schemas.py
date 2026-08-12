import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict

from app.modules.observations.constants import ErrorType, ObservationSourceType


class ObservationCreate(BaseModel):
    source_type: ObservationSourceType
    source_id: uuid.UUID | None = None
    org_id: uuid.UUID | None = None
    region: str = "us-east"
    endpoint_url: str
    latency_ms: float
    status_code: int | None = None
    response_time_ms: float | None = None
    tls_version: str | None = None
    tls_certificate_issuer: str | None = None
    tls_certificate_expiry: datetime | None = None
    error_type: ErrorType = ErrorType.NONE
    error_message: str | None = None
    extra_data: dict[str, Any] | None = None


class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    source_id: uuid.UUID | None
    org_id: uuid.UUID | None
    timestamp: datetime
    region: str
    endpoint_url: str
    latency_ms: float
    status_code: int | None
    response_time_ms: float | None
    tls_version: str | None
    tls_certificate_issuer: str | None
    error_type: str | None
    error_message: str | None
    is_up: bool
    extra_data: dict[str, Any] | None = None
