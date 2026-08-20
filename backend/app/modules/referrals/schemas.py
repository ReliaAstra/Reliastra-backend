from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReferralInfoResponse(BaseModel):
    referral_code: str
    referral_link: str
    total_referrals: int
    active_referrals: int
    pending_rewards: list[dict]
    earned_rewards: list[dict]
    referral_tier: str
    is_founding_referrer: bool


class ReferralRewardResponse(BaseModel):
    id: uuid.UUID
    type: str
    value: int
    status: str
    activated_at: datetime | None
    expires_at: datetime | None
    referred_email: str
    referred_user_id: uuid.UUID | None


class ClaimRewardRequest(BaseModel):
    reward_id: uuid.UUID


class ClaimRewardResponse(BaseModel):
    message: str
    expires_at: datetime | None


class ReferralLeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    display_name: str
    referral_code: str | None
    total_referrals: int
    active_referrals: int
    is_self: bool


class LeaderboardResponse(BaseModel):
    entries: list[ReferralLeaderboardEntry]
    total: int
    page: int
    page_size: int
