import uuid
from typing import Any
from pydantic import BaseModel


class PlanDetailsResponse(BaseModel):
    org_id: uuid.UUID
    plan: str
    max_dependencies: int
    min_check_interval_seconds: int


class PlanInternalDetailsResponse(PlanDetailsResponse):
    """Internal-only response that includes Stripe billing identifiers."""
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None


class StripeWebhookPayload(BaseModel):
    id: str
    type: str
    data: dict[str, Any]
