import uuid
from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator
from app.modules.api_keys.constants import DEFAULT_SCOPES, VALID_SCOPES


class ApiKeyCreateRequest(BaseModel):
    name: str
    scopes: list[str] = DEFAULT_SCOPES
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_SCOPES
        if invalid:
            raise ValueError(f"Invalid scope(s): {', '.join(sorted(invalid))}. Allowed: {', '.join(sorted(VALID_SCOPES))}")
        return v

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, v: datetime | None) -> datetime | None:
        if v is not None and v <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        return v


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ApiKeyCreateResponse(ApiKeyResponse):
    full_key: str
