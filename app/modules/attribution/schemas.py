import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AttributionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    org_id: uuid.UUID
    suspected_dependency_id: uuid.UUID
    classification: str
    confidence_score: float
    signal_breakdown: dict[str, Any]
    supporting_evidence: list[dict[str, Any]]
    contradicting_evidence: list[dict[str, Any]]
    methodology_version: str
    created_at: datetime
