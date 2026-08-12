import uuid
from typing import Any
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_current_org
from app.db.session import get_db
from app.modules.billing.schemas import PlanDetailsResponse, StripeWebhookPayload
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


@router.post("/billing/webhook", response_model=dict[str, Any])
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
    service: BillingService = Depends(get_bill_service),
) -> dict[str, Any]:
    raw_body = await request.body()
    payload = StripeWebhookPayload.model_validate(await request.json())
    return await service.handle_webhook(
        db, payload.model_dump(), signature=stripe_signature, raw_body=raw_body
    )
