from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class PublicIncidentResponse(BaseModel):
    incident_id: uuid.UUID
    vendor_name: str
    title: str
    started_at: datetime
    resolved_at: datetime | None
    duration_minutes: float | None
    severity: str
    status: str
    max_latency_ms: float | None
    downtime_percentage: float | None
    has_evidence_report: bool
    download_token: str | None


class EvidenceGateRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None
    incident_id: uuid.UUID
    vendor_name: str
    org_name: str | None = None
    ref_code: str | None = None


class EvidenceGateResponse(BaseModel):
    download_url: str
    report_id: uuid.UUID
    expires_at: datetime
    account_created: bool
    login_url: str | None
    message: str


class PublicizeEvidenceRequest(BaseModel):
    incident_id: uuid.UUID
    make_public: bool = True
    custom_title: str | None = None
    custom_summary: str | None = None


class PublicizeResponse(BaseModel):
    message: str
    report_id: uuid.UUID


class EvidenceGateStats(BaseModel):
    total_gated_downloads: int
    total_accounts_created: int
    conversion_rate: float
    top_vendors: list[dict]
    recent_conversions: list[dict]
