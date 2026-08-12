import logging
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException, UnauthorizedException
from app.core.permissions import get_dependency_limit, get_min_check_interval
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import PlanDetailsResponse

logger = logging.getLogger(__name__)


_STRIPE_WEBHOOK_SECRET: str = ""  # Set via STRIPE_WEBHOOK_SECRET env var


def _init_stripe() -> None:
    """Lazily load Stripe SDK and webhook secret."""
    global _STRIPE_WEBHOOK_SECRET
    if _STRIPE_WEBHOOK_SECRET:
        return
    from app.config import settings
    _STRIPE_WEBHOOK_SECRET = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not _STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured — webhooks will be rejected")


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
        )

    async def handle_webhook(
        self, session: AsyncSession, payload: dict[str, Any], signature: str | None = None, raw_body: bytes | None = None
    ) -> dict[str, Any]:
        if not signature:
            raise UnauthorizedException("Missing Stripe webhook signature")

        if not raw_body:
            raise UnauthorizedException("Missing raw request body for signature verification")

        _init_stripe()
        if not _STRIPE_WEBHOOK_SECRET:
            raise UnauthorizedException("Stripe webhook secret not configured")

        try:
            import stripe
            event = stripe.Webhook.construct_event(
                raw_body, signature, _STRIPE_WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError as exc:
            raise UnauthorizedException(f"Invalid Stripe webhook signature: {exc}") from exc
        except Exception as exc:
            raise UnauthorizedException(f"Stripe webhook verification failed: {exc}") from exc

        event_type = event.get("type", "")
        logger.info("Received and verified Stripe webhook event: %s", event_type)

        # TODO: Process event types (customer.subscription.created, etc.)
        return {"received": True, "event_type": event_type}


billing_service = BillingService()
