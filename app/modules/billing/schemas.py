import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.core.permissions import Plan


class PlanDetailsResponse(BaseModel):
    org_id: uuid.UUID
    plan: str
    max_dependencies: int
    min_check_interval_seconds: int


class PlanInternalDetailsResponse(PlanDetailsResponse):
    """Internal-only response that includes billing identifiers."""

    provider_customer_id: str | None = None
    provider_subscription_id: str | None = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    provider: str
    plan: str
    status: str
    provider_reference: str | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InitializePaymentRequest(BaseModel):
    plan: Plan
    # Optional; Paystack supports subscription plans via plan codes.
    email: str | None = Field(default=None, max_length=255)


class InitializePaymentResponse(BaseModel):
    authorization_url: str
    reference: str
    provider: str
    plan: str


class VerifyTransactionRequest(BaseModel):
    reference: str = Field(min_length=1, max_length=200)


class VerifyTransactionResponse(BaseModel):
    success: bool
    plan: str
    status: str


class WebhookPayload(BaseModel):
    event: str
    data: dict[str, Any] = {}


class WebhookResponse(BaseModel):
    received: bool
    event_type: str
