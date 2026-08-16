from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class BadgeStyle(str, Enum):
    flat = "flat"
    for_the_badge = "for-the-badge"
    plastic = "plastic"
    social = "social"


class BadgeEmbedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    html: str
    markdown: str
    url: str
    vendor_name: str
    display_name: str
    status: str
