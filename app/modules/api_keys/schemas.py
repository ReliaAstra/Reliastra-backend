"""API credential request, one-time secret, and metadata contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.api_keys.constants import ALLOWED_SCOPES


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, values: list[str]) -> list[str]:
        unknown = set(values) - ALLOWED_SCOPES
        if unknown:
            raise ValueError(f"Unknown API key scopes: {sorted(unknown)}")
        return sorted(set(values))


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    key: str


class ApiKeyIdentityDTO(BaseModel):
    id: UUID
    org_id: UUID
    scopes: list[str]
