import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from app.modules.api_keys.constants import DEFAULT_SCOPES


class ApiKeyCreateRequest(BaseModel):
    name: str
    scopes: list[str] = DEFAULT_SCOPES
    expires_at: datetime | None = None


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
