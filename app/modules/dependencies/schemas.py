import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.modules.dependencies.constants import (
    DEFAULT_EXPECTED_STATUS_CODES,
    DEFAULT_REGIONS,
    DEFAULT_TIMEOUT_SECONDS,
    HttpMethod,
)

# FIX 15: headers that could smuggle requests / corrupt HTTP semantics are
# rejected outright, as are proxy-injection prefixes.
_FORBIDDEN_HEADERS = {
    "cookie",
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
}
_FORBIDDEN_HEADER_PREFIXES = ("proxy-", "x-forwarded-")

# FIX 16: only these monitored regions are valid.
ALLOWED_REGIONS = {"us-east", "eu-west", "ap-south", "sa-east"}


def _validate_header_dict(v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is None:
        return None
    lower_keys = {str(k).lower() for k in v.keys()}
    forbidden = lower_keys & _FORBIDDEN_HEADERS
    if forbidden:
        raise ValueError(
            f"Headers cannot contain: {', '.join(sorted(forbidden))}"
        )
    for key in lower_keys:
        if key.startswith(_FORBIDDEN_HEADER_PREFIXES):
            raise ValueError(
                f"Header '{key}' is not allowed (proxy-injection risk)"
            )
        if any(ch in key for ch in ("\r", "\n", ":")):
            raise ValueError(f"Header name '{key}' is malformed")
    return v


def _validate_regions(v: list[str]) -> list[str]:
    """Validate region names and de-duplicate preserving order (FIX 16)."""
    if not v:
        raise ValueError("regions must contain at least one region")
    deduped: list[str] = []
    for region in v:
        if region not in ALLOWED_REGIONS:
            raise ValueError(
                f"Unknown region '{region}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_REGIONS))}"
            )
        if region not in deduped:
            deduped.append(region)
    return deduped


class DependencyCreateRequest(BaseModel):
    name: str = Field(max_length=150, min_length=1)
    application_id: uuid.UUID | None = None
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
        # Authorization values are encrypted at rest by DependencyService.
        return _validate_header_dict(v)

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: list[str]) -> list[str]:
        return _validate_regions(v)


class DependencyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=150, min_length=1)
    application_id: uuid.UUID | None = None
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
        # Authorization values are encrypted at rest by DependencyService.
        return _validate_header_dict(v)

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: list[str] | None) -> list[str] | None:
        return _validate_regions(v) if v is not None else None


class DependencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    application_id: uuid.UUID | None = None
    name: str
    endpoint_url: str
    method: str
    # FIX 23: decrypted headers are NEVER returned by the API. `headers` is
    # kept for backward compatibility but is always None; callers should use
    # `has_headers`.
    headers: dict[str, Any] | None = None
    has_headers: bool = False
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
    application_id: uuid.UUID | None = None
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
