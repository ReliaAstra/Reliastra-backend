import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ForbiddenException,
    ResourceNotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.permissions import (
    PLAN_DEPENDENCY_LIMITS,
    PLAN_DESCRIPTIONS,
    PLAN_FEATURES,
    PLAN_PRICES_USD,
    PLAN_RETENTION_DAYS,
    PLAN_TAGS,
    Plan,
    get_min_check_interval,
    get_plan_price_usd,
)
from app.dependencies import get_current_org, require_admin, require_member
from app.db.session import get_db
from app.modules.billing.schemas import (
    InitializePaymentRequest,
    InitializePaymentResponse,
    PaystackWebhookPayload,
    PaystackWebhookResponse,
    PlanDetailsResponse,
    VerifyTransactionResponse,
)
from app.modules.billing.service import BillingService, billing_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1", tags=["Billing"])


def get_bill_service() -> BillingService:
    return billing_service


# ── Public Endpoints (no auth required) ──────────────────────────────────────────


class PricingPlanResponse(BaseModel):
    plan: str
    display_name: str
    description: str
    tag: str | None = None
    price_usd: int
    max_dependencies: int
    min_check_interval_seconds: int
    data_retention_days: int
    features: dict


class PricingPlansResponse(BaseModel):
    plans: list[PricingPlanResponse]


@router.get("/pricing", response_model=PricingPlansResponse)
async def get_pricing_plans() -> PricingPlansResponse:
    """Public endpoint returning all plan details for the pricing page."""
    plans = []
    for plan_enum in Plan:
        p = plan_enum.value
        plans.append(PricingPlanResponse(
            plan=p,
            display_name=p.capitalize(),
            description=PLAN_DESCRIPTIONS.get(p, ""),
            tag=PLAN_TAGS.get(p),
            price_usd=PLAN_PRICES_USD.get(p, 0),
            max_dependencies=PLAN_DEPENDENCY_LIMITS.get(p, 0),
            min_check_interval_seconds=get_min_check_interval(p),
            data_retention_days=PLAN_RETENTION_DAYS.get(p, 1),
            features=PLAN_FEATURES.get(p, {}),
        ))
    return PricingPlansResponse(plans=plans)


# ── Authenticated Endpoints ──────────────────────────────────────────────────────


@router.get("/billing/plan", response_model=PlanDetailsResponse)
async def get_organization_plan(
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> PlanDetailsResponse:
    return await service.get_plan_details(db, current_org.id)


@router.post(
    "/billing/initialize",
    response_model=InitializePaymentResponse,
    dependencies=[Depends(require_admin)],
)
async def initialize_payment(
    request: InitializePaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> InitializePaymentResponse:
    return await service.initialize_payment(db, current_org.id, request)


@router.post(
    "/billing/verify",
    response_model=VerifyTransactionResponse,
    dependencies=[Depends(require_member)],
)
async def verify_transaction(
    reference: str = Query(min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> VerifyTransactionResponse:
    try:
        return await service.verify_transaction(db, reference)
    except Exception as exc:
        raise ValidationException(
            f"Transaction verification failed: {exc}"
        ) from exc


@router.post("/billing/webhook", response_model=PaystackWebhookResponse)
async def paystack_webhook(
    request: Request,
    # FIX 10: the Paystack signature header is mandatory (OpenAPI
    # `required: true`). Requests without it are rejected by FastAPI with a
    # 422 before reaching the handler; the service re-checks for defense in
    # depth and verifies the HMAC-SHA512.
    x_paystack_signature: str = Header(alias="x-paystack-signature"),
    db: AsyncSession = Depends(get_db),
    service: BillingService = Depends(get_bill_service),
) -> PaystackWebhookResponse:
    raw_body = await request.body()
    try:
        payload = PaystackWebhookPayload.model_validate(json.loads(raw_body))
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
        raise ValidationException("Invalid Paystack webhook body") from exc
    return await service.handle_webhook(
        db,
        payload.model_dump(),
        signature=x_paystack_signature,
        raw_body=raw_body,
    )
