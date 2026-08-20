from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TimelineShareCreateRequest(BaseModel):
    """Request body for creating a new timeline share link."""

    window: str = Field(default="24h", description="Time window for the timeline (e.g. '24h', '7d')")
    region: str = Field(default="us-east", description="Region for the timeline data")
    note: str | None = Field(default=None, description="Optional note attached to the share")


class TimelineShareResponse(BaseModel):
    """Response returned after creating a timeline share link."""

    model_config = ConfigDict(from_attributes=True)

    share_url: str
    expires_at: datetime
    share_token: str
    vendor_name: str
