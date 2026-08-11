"""Billing feature and webhook contracts."""

from __future__ import annotations

from pydantic import BaseModel

from app.modules.organizations.constants import Plan


class PlanEntitlements(BaseModel):
    plan: Plan
    features: list[str]


class StripeWebhookResponse(BaseModel):
    accepted: bool
