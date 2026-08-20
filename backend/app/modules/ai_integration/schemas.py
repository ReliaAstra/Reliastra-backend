import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ProviderType = Literal["openai_compatible", "anthropic", "google"]


class AIProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider_type: ProviderType
    endpoint_url: str = Field(min_length=1, max_length=500)
    api_key: SecretStr | None = None
    model_name: str = Field(min_length=1, max_length=100)
    is_default: bool = False
    max_tokens: int = Field(default=4096, ge=1, le=100000)
    temperature: float = Field(default=0.3, ge=0, le=2)
    enabled: bool = True

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("endpoint_url must be an HTTP(S) URL")
        return value


class AIProviderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider_type: ProviderType | None = None
    endpoint_url: str | None = Field(default=None, max_length=500)
    api_key: SecretStr | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=100)
    is_default: bool | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=100000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    enabled: bool | None = None

    @field_validator("endpoint_url")
    @classmethod
    def validate_endpoint(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("endpoint_url must be an HTTP(S) URL")
        return value


class AIProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    provider_type: str
    endpoint_url: str
    model_name: str
    is_default: bool
    max_tokens: int
    temperature: float
    enabled: bool
    has_api_key: bool = False
    created_at: datetime
    updated_at: datetime
