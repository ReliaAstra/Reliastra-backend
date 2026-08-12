import logging
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException, UnauthorizedException
from app.core.permissions import get_dependency_limit, get_min_check_interval
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import PlanDetailsResponse, StripeWebhookResponse

logger = logging.getLogger(__name__)


_STRIPE_WEBHOOK_SECRET: str = ""  # Set via STRIPE_WEBHOOK_SECRET env var
_STRIPE_INITIALIZED: bool = False


def _init_stripe() -> None:
    """Lazily load Stripe SDK and webhook secret."""
    global _STRIPE_WEBHOOK_SECRET, _STRIPE_INITIALIZED
    if _STRIPE_INITIALIZED:
        return
    from app.config import settings
    _STRIPE_WEBHOOK_SECRET = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    _STRIPE_INITIALIZED = True
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

    async def _process_subscription_event(
        self, session: AsyncSession, event: dict[str, Any]
    ) -> None:
        """Process Stripe subscription webhook events to update plan/billing info."""
        import stripe

        event_type = event.get("type", "")
        data = event.get("data", {})
        obj = data.get("object", {})

        customer_id = obj.get("customer")
        subscription_id = obj.get("id")

        if not customer_id:
            return

        # Look up organization by Stripe customer ID
        org = await self.repository.get_org_by_stripe_customer(
            session, str(customer_id)
        )
        if not org:
            logger.info("No organization found for Stripe customer %s", customer_id)
            return

        if event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            plan_id = obj.get("items", [{}])[0].get("price", {}).get("lookup_key", "")
            status = obj.get("status", "")

            if status == "active" and plan_id:
                from app.core.permissions import Plan
                valid_plans = {p.value for p in Plan}
                if plan_id in valid_plans:
                    await self.repository.update_org_plan(
                        session, org, plan=plan_id,
                        customer_id=str(customer_id),
                        subscription_id=str(subscription_id),
                    )
                    logger.info(
                        "Updated org %s plan to '%s' via Stripe webhook",
                        org.id, plan_id,
                    )

        elif event_type == "customer.subscription.deleted":
            from app.core.permissions import Plan
            await self.repository.update_org_plan(
                session, org, plan=Plan.FREE.value,
                subscription_id=None,
            )
            logger.info("Reset org %s to free plan after subscription cancellation", org.id)

    async def handle_webhook(
        self, session: AsyncSession, payload: dict[str, Any], signature: str | None = None, raw_body: bytes | None = None
    ) -> StripeWebhookResponse:
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

        # Process subscription lifecycle events
        if event_type.startswith("customer.subscription."):
            await self._process_subscription_event(session, event)

        return StripeWebhookResponse(received=True, event_type=event_type)


billing_service = BillingService()
