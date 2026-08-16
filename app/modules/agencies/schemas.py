import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClientCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    client_id: uuid.UUID | None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
