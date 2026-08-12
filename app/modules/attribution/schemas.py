import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class AttributionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    org_id: uuid.UUID
    dependency_id: uuid.UUID
    confidence_score: float
    methodology_version: str
    signals: dict[str, Any]
    evidence_chain: dict[str, Any]
    summary: str | None = None
    created_at: datetime
