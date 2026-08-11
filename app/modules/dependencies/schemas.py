import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict
from app.modules.dependencies.constants import (
    DEFAULT_EXPECTED_STATUS_CODES,
    DEFAULT_REGIONS,
    DEFAULT_TIMEOUT_SECONDS,
    HttpMethod,
)


class DependencyCreateRequest(BaseModel):
    name: str
    endpoint_url: str
    method: HttpMethod = HttpMethod.GET
    headers: dict[str, Any] | None = None
    expected_status_codes: list[int] = DEFAULT_EXPECTED_STATUS_CODES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    check_interval_seconds: int = 300
    regions: list[str] = DEFAULT_REGIONS
    alert_threshold_ms: int | None = None
    is_active: bool = True


class DependencyUpdateRequest(BaseModel):
    name: str | None = None
    endpoint_url: str | None = None
    method: HttpMethod | None = None
    headers: dict[str, Any] | None = None
    expected_status_codes: list[int] | None = None
    timeout_seconds: int | None = None
    check_interval_seconds: int | None = None
    regions: list[str] | None = None
    alert_threshold_ms: int | None = None
    is_active: bool | None = None


class DependencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    endpoint_url: str
    method: str
    headers: dict[str, Any] | None = None
    expected_status_codes: list[int]
    timeout_seconds: int
    check_interval_seconds: int
    next_check_at: datetime | None = None
    regions: list[str]
    alert_threshold_ms: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DependencyHistoryResponse(BaseModel):
    dependency_id: uuid.UUID
    uptime_percentage: float
    avg_latency_ms: float
    total_checks: int
    total_up: int
    total_down: int


class DependencyInternalDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    endpoint_url: str
    method: str
    headers: dict[str, Any] | None = None
    expected_status_codes: list[int]
    timeout_seconds: int
    check_interval_seconds: int
    regions: list[str]
    alert_threshold_ms: int | None = None
    is_active: bool
