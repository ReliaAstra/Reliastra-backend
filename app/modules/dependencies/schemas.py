"""Dependency request, response, and execution DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from app.modules.dependencies.constants import DEFAULT_REGIONS, HttpMethod


class DependencyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    endpoint_url: AnyHttpUrl
    method: HttpMethod = HttpMethod.GET
    headers: dict[str, str] | None = None
    expected_status_codes: list[int] = Field(default_factory=lambda: [200], min_length=1)
    timeout_seconds: int = Field(default=10, ge=1, le=60)
    check_interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    regions: list[str] = Field(
        default_factory=lambda: DEFAULT_REGIONS.copy(), min_length=1, max_length=10
    )
    alert_threshold_ms: int | None = Field(default=None, ge=1)
    is_active: bool = True
    dependency_type: str = Field(default="vendor", pattern="^(vendor|internal)$")

    @field_validator("expected_status_codes")
    @classmethod
    def valid_status_codes(cls, values: list[int]) -> list[int]:
        if any(value < 100 or value > 599 for value in values):
            raise ValueError("Status codes must be between 100 and 599")
        return sorted(set(values))


class DependencyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    endpoint_url: AnyHttpUrl | None = None
    method: HttpMethod | None = None
    headers: dict[str, str] | None = None
    expected_status_codes: list[int] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    check_interval_seconds: int | None = Field(default=None, ge=10, le=86400)
    regions: list[str] | None = Field(default=None, min_length=1, max_length=10)
    alert_threshold_ms: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    dependency_type: str | None = Field(default=None, pattern="^(vendor|internal)$")


class DependencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    endpoint_url: str
    method: HttpMethod
    expected_status_codes: list[int]
    timeout_seconds: int
    check_interval_seconds: int
    regions: list[str]
    alert_threshold_ms: int | None
    is_active: bool
    dependency_type: str
    next_check_at: datetime
    created_at: datetime
    updated_at: datetime


class DependencyExecutionDTO(BaseModel):
    id: UUID
    org_id: UUID
    endpoint_url: str
    method: HttpMethod
    headers: dict[str, Any]
    expected_status_codes: list[int]
    timeout_seconds: int
    regions: list[str]
    alert_threshold_ms: int | None


class DependencyScheduleDTO(BaseModel):
    id: UUID
    regions: list[str]
