import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class CheckResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dependency_id: uuid.UUID
    org_id: uuid.UUID
    region: str
    executed_at: datetime
    latency_ms: float
    status_code: int | None = None
    is_up: bool
    error_message: str | None = None
    quorum_confirmed: bool


class CheckResultCreateDTO(BaseModel):
    dependency_id: uuid.UUID
    org_id: uuid.UUID
    region: str
    latency_ms: float
    status_code: int | None = None
    is_up: bool
    error_message: str | None = None
    quorum_confirmed: bool = False
