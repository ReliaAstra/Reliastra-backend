"""Evidence metadata and generation contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvidenceReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    incident_id: UUID
    file_path: str
    file_size_bytes: int
    checksum: str
    generated_at: datetime
    expires_at: datetime | None
    download_url: str | None = None


class EvidenceQueuedResponse(BaseModel):
    status: Literal["queued"] = "queued"
    incident_id: UUID


class EvidenceGenerationDTO(BaseModel):
    incident_id: UUID
    org_id: UUID
    generated_at: datetime
    measured_uptime: float
    sla_impact: float
    payload_checksum: str
