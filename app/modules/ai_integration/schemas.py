import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AiProviderCreateRequest(BaseModel):
    name: str = Field(max_length=100, min_length=1)
    provider_type: str = Field(
        max_length=50,
        description="openai_compatible | anthropic | google | mistral",
    )
    endpoint_url: str
    api_key: str
    model_name: str
    is_default: bool = False
    max_tokens: int = Field(default=4096, ge=1, le=32768)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    enabled: bool = True


class AiProviderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    provider_type: str | None = Field(default=None, max_length=50)
    endpoint_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    is_default: bool | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=32768)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    enabled: bool | None = None


class AiProviderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    provider_type: str
    endpoint_url: str
    model_name: str
    is_default: bool
    max_tokens: int
    temperature: float
    enabled: bool
    created_at: datetime
    updated_at: datetime
