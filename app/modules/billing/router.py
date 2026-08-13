import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ResourceNotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.permissions import (
    FOUNDING_DISCOUNT_PCT,
    FOUNDING_MAX_SPOTS,
    PLAN_AMOUNTS,
    PLAN_DEPENDENCY_LIMITS,
    PLAN_PRICES_USD,
    Plan,
    get_dependency_limit,
    get_discounted_price_usd,
    get_min_check_interval,
    get_plan_price_usd,
)
from app.db.session import get_db
from app.dependencies import get_current_org, require_admin
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


class FoundingSpotsResponse(BaseModel):
    total_spots: int
    spots_taken: int
    spots_remaining: int
    founding_discount_pct: int
    standard_price_usd: int
    professional_price_usd: int
    founding_standard_price_usd: int
    founding_professional_price_usd: int


@router.get("/public/founding-spots", response_model=FoundingSpotsResponse)
async def get_founding_spots(
    db: AsyncSession = Depends(get_db),
) -> FoundingSpotsResponse:
    """Public endpoint for the landing page showing founding customer spots remaining.
    Returns pricing, discount information, and how many founding spots are left.
    """
    try:
        result = await db.execute(
            select(func.count()).select_from(Organization).where(
                Organization.is_founding_customer.is_(True)
            )
        )
        spots_taken = result.scalar() or 0
    except Exception:
        spots_taken = 0

    return FoundingSpotsResponse(
        total_spots=FOUNDING_MAX_SPOTS,
        spots_taken=spots_taken,
        spots_remaining=max(0, FOUNDING_MAX_SPOTS - spots_taken),
        founding_discount_pct=FOUNDING_DISCOUNT_PCT,
        standard_price_usd=PLAN_PRICES_USD.get(Plan.STANDARD.value, 0),
        professional_price_usd=PLAN_PRICES_USD.get(Plan.PROFESSIONAL.value, 0),
        founding_standard_price_usd=get_discounted_price_usd(Plan.STANDARD.value),
        founding_professional_price_usd=get_discounted_price_usd(Plan.PROFESSIONAL.value),
    )


class PricingPlansResponse(BaseModel):
    plans: list[dict]


@router.get("/public/pricing", response_model=PricingPlansResponse)
async def get_pricing_plans() -> PricingPlansResponse:
    """Public endpoint returning all plan details for the pricing page."""
    plans = []
    for plan_enum in Plan:
        p = plan_enum.value
        base_price = PLAN_PRICES_USD.get(p, 0)
        plans.append({
            "plan": p,
            "max_dependencies": PLAN_DEPENDENCY_LIMITS.get(p, 0),
            "min_check_interval_seconds": {
                k: v for k, v in {
                    Plan.FREE.value: 60,
                    Plan.STANDARD.value: 15,
                    Plan.PROFESSIONAL.value: 5,
                    Plan.AGENCY.value: 5,
                }.items() if k == p
            }.get(p, 60),
            "price_usd": base_price,
            "founding_price_usd": get_discounted_price_usd(p) if base_price > 0 else 0,
        })
    return PricingPlansResponse(plans=plans)


# ── Authenticated Endpoints ──────────────────────────────────────────────────────


@router.get("/orgs/{org_id}/billing/plan", response_model=PlanDetailsResponse)
async def get_organization_plan(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> PlanDetailsResponse:
    return await service.get_plan_details(db, org_id)


@router.post(
    "/orgs/{org_id}/billing/initialize",
    response_model=InitializePaymentResponse,
    dependencies=[Depends(require_admin)],
)
async def initialize_payment(
    org_id: uuid.UUID,
    request: InitializePaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> InitializePaymentResponse:
    return await service.initialize_payment(db, org_id, request)


@router.post("/billing/verify", response_model=VerifyTransactionResponse)
async def verify_transaction(
    reference: str = Query(min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
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
    x_paystack_signature: str | None = Header(
        default=None, alias="x-paystack-signature"
    ),
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
