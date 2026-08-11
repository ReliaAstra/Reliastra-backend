import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class EvidenceReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    incident_id: uuid.UUID
    file_path: str
    file_size_bytes: int
    checksum: str
    generated_at: datetime
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EvidenceReportDownloadResponse(EvidenceReportResponse):
    download_url: str
