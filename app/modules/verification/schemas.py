import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel


class VerificationResponse(BaseModel):
    verification_id: str
    incident_id: uuid.UUID
    dependency_id: uuid.UUID
    org_id: uuid.UUID
    time_window_start: datetime
    time_window_end: datetime
    methodology_version: str
    data_hash: str
    report_checksum: str
    created_at: datetime
    hashes_match: bool


class VerificationHashResponse(BaseModel):
    verification_id: str
    data_hash: str
    report_checksum: str


class VerificationEvidenceResponse(BaseModel):
    verification_id: str
    incident_id: uuid.UUID
    dependency_id: uuid.UUID
    time_window_start: datetime
    time_window_end: datetime
    methodology_version: str
    data_hash: str
    observations: list[Any]
    attribution_result: dict[str, Any]
    created_at: datetime
