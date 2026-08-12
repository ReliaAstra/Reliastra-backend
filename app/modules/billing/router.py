import json
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

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
    return await service.verify_transaction(db, reference)


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
        from app.core.exceptions import ValidationException

        raise ValidationException("Invalid Paystack webhook body") from exc
    return await service.handle_webhook(
        db,
        payload.model_dump(),
        signature=x_paystack_signature,
        raw_body=raw_body,
    )
