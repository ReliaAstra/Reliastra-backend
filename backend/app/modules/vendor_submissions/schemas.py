from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, HttpUrl


class VendorSubmitEndpoint(BaseModel):
    name: str
    url: HttpUrl
    method: str = "GET"
    expected_status: int = 200


class VendorSubmitRequest(BaseModel):
    vendor_name: str
    display_name: str
    category: str | None = None
    website_url: str | None = None
    submitter_email: EmailStr
    submitter_name: str | None = None
    reason: str | None = None
    endpoints: list[VendorSubmitEndpoint] | None = None


class VendorSubmitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_name: str
    display_name: str
    status: str
    message: str
    estimated_days: int | None = None


class VendorSubmissionListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vendor_name: str
    display_name: str
    category: str | None
    submitter_email: str
    status: str
    created_at: datetime
    reviewed_at: datetime | None


class ApproveVendorRequest(BaseModel):
    vendor_name: str
    display_name: str
    category: str | None = None
    endpoints: list[VendorSubmitEndpoint] | None = None


class RejectVendorRequest(BaseModel):
    reason: str


class AdminActionResponse(BaseModel):
    message: str
    submission_id: uuid.UUID
    status: str
