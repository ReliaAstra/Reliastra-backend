from __future__ import annotations

import uuid

from pydantic import BaseModel


class GrowthFunnelResponse(BaseModel):
    period: str
    badge_impressions: int
    badge_clicks: int
    vendor_page_views: int
    vendor_submissions: int
    evidence_gated_views: int
    evidence_downloads: int
    evidence_conversions: int
    referral_signups: int
    total_new_users: int
    total_new_orgs: int
    conversion_rates: dict[str, float]


class TopVendorStat(BaseModel):
    vendor_name: str
    views: int
    badge_embeds: int
    submissions: int
    evidence_downloads: int


class ReferralStatItem(BaseModel):
    user_id: uuid.UUID
    display_name: str
    total_referrals: int
    active_referrals: int
    conversion_rate: float
