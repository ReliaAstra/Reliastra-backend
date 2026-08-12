import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from app.modules.dependencies.constants import (
    DEFAULT_EXPECTED_STATUS_CODES,
    DEFAULT_REGIONS,
    DEFAULT_TIMEOUT_SECONDS,
    HttpMethod,
)


class DependencyCreateRequest(BaseModel):
    name: str = Field(max_length=150, min_length=1)
    endpoint_url: str
    method: HttpMethod = HttpMethod.GET
    headers: dict[str, Any] | None = None
    expected_status_codes: list[int] = DEFAULT_EXPECTED_STATUS_CODES
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=1, le=300)
    check_interval_seconds: int = Field(default=300, ge=10, le=86400)
    regions: list[str] = Field(default=DEFAULT_REGIONS, min_length=1)
    alert_threshold_ms: int | None = Field(default=None, ge=1)
    is_active: bool = True

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("endpoint_url must start with http:// or https://")
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # 'authorization' is permitted (and stored encrypted at rest) because
        # authenticated dependency health checks require bearer tokens. Hop-by-hop
        # headers that would conflict with the outbound request are forbidden.
        if v is not None:
            forbidden = {"cookie", "host", "content-length", "transfer-encoding"}
            lower_keys = {k.lower() for k in v.keys()}
            if forbidden & lower_keys:
                raise ValueError(f"Headers cannot contain: {', '.join(sorted(forbidden))}")
        return v


class DependencyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=150, min_length=1)
    endpoint_url: str | None = None
    method: HttpMethod | None = None
    headers: dict[str, Any] | None = None
    expected_status_codes: list[int] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    check_interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    regions: list[str] | None = None
    alert_threshold_ms: int | None = Field(default=None, ge=1)
    is_active: bool | None = None

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("endpoint_url must start with http:// or https://")
        return v

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        # 'authorization' is permitted (and stored encrypted at rest) because
        # authenticated dependency health checks require bearer tokens.
        if v is not None:
            forbidden = {"cookie", "host", "content-length", "transfer-encoding"}
            lower_keys = {k.lower() for k in v.keys()}
            if forbidden & lower_keys:
                raise ValueError(f"Headers cannot contain: {', '.join(sorted(forbidden))}")
        return v


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
