import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ClientCreateRequest(BaseModel):
    name: str = Field(max_length=150, min_length=1)
    description: str | None = Field(default=None, max_length=2000)


class ClientUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    description: str | None = Field(default=None, max_length=2000)


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationCreateRequest(BaseModel):
    name: str = Field(max_length=150, min_length=1)
    description: str | None = Field(default=None, max_length=2000)
    client_id: uuid.UUID | None = None


class ApplicationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    client_id: uuid.UUID | None = None


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    client_id: uuid.UUID | None
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
