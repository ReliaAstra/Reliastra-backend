import uuid

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_org, require_member, require_owner
from app.db.session import get_db
from app.modules.billing.schemas import (
    InitializePaymentRequest,
    InitializePaymentResponse,
    PlanDetailsResponse,
    SubscriptionResponse,
    VerifyTransactionRequest,
    VerifyTransactionResponse,
    WebhookResponse,
)
from app.modules.billing.service import BillingService, billing_service
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/v1", tags=["Billing"])


def get_bill_service() -> BillingService:
    return billing_service


@router.get(
    "/orgs/{org_id}/billing/plan",
    response_model=PlanDetailsResponse,
    dependencies=[Depends(require_member)],
)
async def get_organization_plan(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> PlanDetailsResponse:
    return await service.get_plan_details(db, org_id)


@router.get(
    "/orgs/{org_id}/billing/subscription",
    response_model=SubscriptionResponse | None,
    dependencies=[Depends(require_member)],
)
async def get_organization_subscription(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> SubscriptionResponse | None:
    return await service.get_subscription(db, org_id)


@router.post(
    "/orgs/{org_id}/billing/initialize-payment",
    response_model=InitializePaymentResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_owner)],
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
    "/orgs/{org_id}/billing/verify-transaction",
    response_model=VerifyTransactionResponse,
    dependencies=[Depends(require_owner)],
)
async def verify_transaction(
    org_id: uuid.UUID,
    request: VerifyTransactionRequest,
    db: AsyncSession = Depends(get_db),
    current_org: Organization = Depends(get_current_org),
    service: BillingService = Depends(get_bill_service),
) -> VerifyTransactionResponse:
    return await service.verify_transaction(db, org_id, request.reference)


@router.post("/billing/webhook", response_model=WebhookResponse)
async def payment_webhook(
    request: Request,
    paystack_signature: str | None = Header(default=None, alias="X-Paystack-Signature"),
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
    service: BillingService = Depends(get_bill_service),
) -> WebhookResponse:
    raw_body: bytes = await request.body()
    # Paystack is the active provider; Stripe-Signature is honoured for legacy
    # clients but routed through the same provider-agnostic handler.
    signature = paystack_signature or stripe_signature
    return await service.handle_webhook(db, raw_body, signature)
