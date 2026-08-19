"""Pydantic schemas for the Partner Referral API (v1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Partner activation / profile ──────────────────────────────────────────


class PartnerApplyRequest(BaseModel):
    agree_terms: bool = False


class PartnerProfileResponse(BaseModel):
    partner_id: uuid.UUID
    referral_code: str
    referral_link: str
    commission_rate: int
    status: str
    created_at: datetime


class PartnerDashboardResponse(BaseModel):
    referral_link: str
    clicks: int
    signups: int
    active_paid_customers: int
    monthly_commission_minor: int
    pending_commission_minor: int
    total_earned_minor: int
    total_paid_minor: int
    currency: str


# ── Referrals ─────────────────────────────────────────────────────────────


class ReferralItem(BaseModel):
    referral_id: uuid.UUID
    status: str
    plan: str | None
    subscription_amount_minor: int
    commission_rate: int
    monthly_commission_minor: int
    masked_email: str | None
    organization_name: str | None
    created_at: datetime
    subscribed_at: datetime | None


class ReferralListResponse(BaseModel):
    items: list[ReferralItem]
    page: int
    page_size: int
    total: int


# ── Commissions ───────────────────────────────────────────────────────────


class CommissionItem(BaseModel):
    id: uuid.UUID
    referral_id: uuid.UUID | None
    period: str
    subscription_amount_minor: int
    commission_rate: int
    commission_amount_minor: int
    currency: str
    status: str
    created_at: datetime
    payable_at: datetime | None
    paid_at: datetime | None


class CommissionListResponse(BaseModel):
    items: list[CommissionItem]
    page: int
    page_size: int
    total: int


# ── Payouts ───────────────────────────────────────────────────────────────


class PayoutItem(BaseModel):
    id: uuid.UUID
    period: str | None
    amount_minor: int
    currency: str
    status: str
    paid_at: datetime | None
    transaction_reference: str | None


class PayoutListResponse(BaseModel):
    items: list[PayoutItem]
    page: int
    page_size: int
    total: int


# ── Public referral resolution ────────────────────────────────────────────


class ReferralResolveResponse(BaseModel):
    valid: bool
    referral_code: str | None
    destination: str
    visitor_id: str | None = None


# ── Admin ─────────────────────────────────────────────────────────────────


class PartnerAdminItem(BaseModel):
    partner_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    referral_code: str
    status: str
    referred_signups: int
    active_paid_customers: int
    monthly_commission_minor: int
    total_earned_minor: int
    total_paid_minor: int
    currency: str
    created_at: datetime


class PartnerAdminListResponse(BaseModel):
    items: list[PartnerAdminItem]
    page: int
    page_size: int
    total: int


class PartnerStatusUpdateRequest(BaseModel):
    status: str = Field(pattern="^(active|suspended|banned)$")
    reason: str | None = None


class CommissionReverseRequest(BaseModel):
    reason: str


class AdminCommissionItem(BaseModel):
    commission_id: uuid.UUID
    partner_id: uuid.UUID
    partner_email: str | None
    referral_id: uuid.UUID | None
    referred_email: str | None
    period: str
    subscription_amount_minor: int
    commission_amount_minor: int
    currency: str
    status: str
    created_at: datetime
    paid_at: datetime | None


class AdminCommissionListResponse(BaseModel):
    items: list[AdminCommissionItem]
    page: int
    page_size: int
    total: int


class PayoutCreateRequest(BaseModel):
    partner_id: uuid.UUID
    amount_minor: int | None = None


class PayoutProcessRequest(BaseModel):
    action: str = Field(pattern="^(mark_paid|mark_failed)$")
    transaction_reference: str | None = None


class AdminPayoutItem(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    partner_email: str | None
    period: str | None
    amount_minor: int
    currency: str
    status: str
    transaction_reference: str | None
    requested_at: datetime
    paid_at: datetime | None


class AdminPayoutListResponse(BaseModel):
    items: list[AdminPayoutItem]
    page: int
    page_size: int
    total: int


class PartnerStatsResponse(BaseModel):
    total_partners: int
    active_partners: int
    total_referred_signups: int
    total_active_paid_customers: int
    monthly_referred_revenue_minor: int
    monthly_commission_minor: int
    total_commission_paid_minor: int
    pending_commission_minor: int
    currency: str
