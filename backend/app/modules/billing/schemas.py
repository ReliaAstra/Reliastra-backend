import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class PlanDetailsResponse(BaseModel):
    org_id: uuid.UUID
    plan: str
    max_dependencies: int
    min_check_interval_seconds: int
    subscription_status: str | None = None
    current_period_end: datetime | None = None
    price_usd: int = 0


class PaystackWebhookPayload(BaseModel):
    event: str
    data: dict[str, Any]


class PaystackWebhookResponse(BaseModel):
    received: bool
    event_type: str


class InitializePaymentRequest(BaseModel):
    plan: str = Field(min_length=1, max_length=50)
    email: EmailStr | None = None


class InitializePaymentResponse(BaseModel):
    authorization_url: str
    reference: str
    access_code: str


class VerifyTransactionResponse(BaseModel):
    verified: bool
    plan: str
    reference: str
