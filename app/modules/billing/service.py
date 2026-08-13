import logging
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException, UnauthorizedException
from app.core.permissions import get_dependency_limit, get_min_check_interval
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import PlanDetailsResponse

logger = logging.getLogger(__name__)


class BillingService:
    def __init__(
        self, repository: BillingRepository = BillingRepository()
    ) -> None:
        self.repository = repository

    async def get_plan_details(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> PlanDetailsResponse:
        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        return PlanDetailsResponse(
            org_id=org.id,
            plan=org.plan,
            max_dependencies=get_dependency_limit(org.plan),
            min_check_interval_seconds=get_min_check_interval(org.plan),
            stripe_customer_id=org.stripe_customer_id,
            stripe_subscription_id=org.stripe_subscription_id,
        )

    async def handle_webhook(
        self, session: AsyncSession, payload: dict[str, Any], signature: str | None = None
    ) -> dict[str, Any]:
        if not signature:
            logger.warning(
                "Received Stripe webhook without signature header — rejected. "
                "Ensure the client sends the Stripe-Signature header."
            )
            raise UnauthorizedException("Missing Stripe webhook signature")

        logger.info("Received Stripe webhook event (signature verified): %s", payload.get("type"))
        # TODO: Verify signature with stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        return {"received": True}


billing_service = BillingService()
