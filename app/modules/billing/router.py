import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ForbiddenException,
    ResourceNotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.permissions import (
    FOUNDING_DISCOUNT_PCT,
    FOUNDING_MAX_SPOTS,
    PLAN_DEPENDENCY_LIMITS,
    PLAN_DESCRIPTIONS,
    PLAN_FEATURES,
    PLAN_PRICES_USD,
    PLAN_RETENTION_DAYS,
    PLAN_TAGS,
    Plan,
    get_discounted_price_usd,
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


@router.get("/public/pricing", response_model=PricingPlansResponse)
async def get_pricing_plans() -> PricingPlansResponse:
    """Public endpoint returning all plan details for the pricing page.

    Does NOT include founding discount pricing — the founding program is private.
    """
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


# ── Founding Program (PRIVATE — auth required) ──────────────────────────────────


class FoundingSpotsResponse(BaseModel):
    total_spots: int
    spots_taken: int
    spots_remaining: int
    founding_discount_pct: int
    eligible_plans: list[str]
    plan_discounts: dict[str, dict]


@router.get(
    "/orgs/{org_id}/billing/founding-spots",
    response_model=FoundingSpotsResponse,
)
async def get_founding_spots(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
) -> FoundingSpotsResponse:
    """PRIVATE endpoint: founding customer program status.

    Requires authentication. Returns founding spots remaining and
    the discounted prices for all eligible paid tiers.

    The founding program is invite-only and not advertised publicly.
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

    # Calculate discounts for all eligible paid plans
    plan_discounts = {}
    for plan_value in {Plan.STARTER.value, Plan.STANDARD.value,
                       Plan.PROFESSIONAL.value, Plan.AGENCY.value}:
        base = PLAN_PRICES_USD.get(plan_value, 0)
        if base > 0:
            discounted = get_discounted_price_usd(plan_value)
            plan_discounts[plan_value] = {
                "base_price_usd": base,
                "discounted_price_usd": discounted,
                "savings_usd": base - discounted,
            }

    return FoundingSpotsResponse(
        total_spots=FOUNDING_MAX_SPOTS,
        spots_taken=spots_taken,
        spots_remaining=max(0, FOUNDING_MAX_SPOTS - spots_taken),
        founding_discount_pct=FOUNDING_DISCOUNT_PCT,
        eligible_plans=[Plan.STARTER.value, Plan.STANDARD.value,
                       Plan.PROFESSIONAL.value, Plan.AGENCY.value],
        plan_discounts=plan_discounts,
    )


class ClaimFoundingSpotRequest(BaseModel):
    """Request body for claiming a founding customer spot."""
    email: str | None = None


class ClaimFoundingSpotResponse(BaseModel):
    success: bool
    message: str
    is_founding_customer: bool
    founding_discount_pct: int


@router.post(
    "/orgs/{org_id}/billing/founding-spot/claim",
    response_model=ClaimFoundingSpotResponse,
    dependencies=[Depends(require_admin)],
)
async def claim_founding_spot(
    org_id: uuid.UUID,
    body: ClaimFoundingSpotRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
) -> ClaimFoundingSpotResponse:
    """PRIVATE endpoint: claim a founding customer spot for an organization.

    Only org owners/admins can claim. Enforces the 25-spot hard cap.
    Once all 25 spots are taken, no more organizations can join.

    The founding discount (40% off any paid tier) is applied automatically
    at payment initialization for founding organizations.
    """
    # Check if org is already a founding customer
    if current_org.is_founding_customer:
        return ClaimFoundingSpotResponse(
            success=False,
            message="This organization is already a founding customer. The 40% discount is already applied.",
            is_founding_customer=True,
            founding_discount_pct=FOUNDING_DISCOUNT_PCT,
        )

    # Lock the current org row to serialize concurrent claim attempts
    await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )

    # Re-check spots remaining inside the lock — this prevents the
    # TOCTOU race where two concurrent requests both read 24 and both
    # try to claim spot 25.
    try:
        result = await db.execute(
            select(func.count()).select_from(Organization).where(
                Organization.is_founding_customer.is_(True)
            )
        )
        spots_taken = result.scalar() or 0
    except Exception:
        spots_taken = 0

    if spots_taken >= FOUNDING_MAX_SPOTS:
        raise ValidationException(
            f"All {FOUNDING_MAX_SPOTS} founding customer spots have been claimed. "
            f"The founding program is now closed.",
            details={
                "code": "FOUNDING_PROGRAM_FULL",
                "total_spots": FOUNDING_MAX_SPOTS,
                "spots_taken": spots_taken,
            },
        )

    # Claim the spot — still inside the lock, so no other request can
    # read a stale count.
    from app.modules.organizations.repository import OrganizationRepository

    await OrganizationRepository.update(
        db,
        current_org,
        is_founding_customer=True,
        founding_discount_pct=FOUNDING_DISCOUNT_PCT,
    )

    spots_remaining = FOUNDING_MAX_SPOTS - spots_taken - 1

    return ClaimFoundingSpotResponse(
        success=True,
        message=(
            f"Founding customer spot claimed! Your organization now has a lifetime "
            f"40% discount on all paid tiers. {spots_remaining} founding spots remaining."
        ),
        is_founding_customer=True,
        founding_discount_pct=FOUNDING_DISCOUNT_PCT,
    )


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


@router.post(
    "/orgs/{org_id}/billing/verify",
    response_model=VerifyTransactionResponse,
    dependencies=[Depends(require_member)],
)
async def verify_transaction(
    org_id: uuid.UUID,
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
