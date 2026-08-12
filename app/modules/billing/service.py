import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import (
    ResourceNotFoundException,
    UnauthorizedException,
)
from app.core.permissions import Plan, get_dependency_limit, get_min_check_interval
from app.modules.billing.constants import (
    PAYMENT_SUCCESS_EVENTS,
    PLAN_PRICES_KOBO,
    SUBSCRIPTION_EVENTS,
)
from app.modules.billing.provider import (
    PaymentInitResult,
    PaymentProvider,
    PaymentVerifyResult,
    payment_provider_registry,
)
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import (
    InitializePaymentRequest,
    InitializePaymentResponse,
    PlanDetailsResponse,
    SubscriptionResponse,
    VerifyTransactionResponse,
    WebhookResponse,
)

logger = logging.getLogger(__name__)


class BillingService:
    def __init__(
        self,
        repository: BillingRepository = BillingRepository(),
        provider_registry=None,
    ) -> None:
        self.repository = repository
        self.provider_registry = provider_registry or payment_provider_registry

    # -- provider helpers -----------------------------------------------------

    def _get_provider(self) -> PaymentProvider:
        return self.provider_registry.get(settings.PAYMENT_PROVIDER)

    # -- plan / subscription reads ---------------------------------------------

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

    async def get_subscription(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> SubscriptionResponse | None:
        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        sub = await self.repository.get_subscription(session, org_id)
        return SubscriptionResponse.model_validate(sub) if sub else None

    # -- payment lifecycle ------------------------------------------------------

    async def initialize_payment(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: InitializePaymentRequest,
    ) -> InitializePaymentResponse:
        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        provider = self._get_provider()
        amount_kobo = PLAN_PRICES_KOBO.get(request.plan.value, 0)
        email = request.email or f"{org.slug}@reliastra.local"

        result: PaymentInitResult = provider.initialize(
            email=email,
            amount_kobo=amount_kobo,
            plan=request.plan.value,
            callback_url=settings.PAYSTACK_CALLBACK_URL,
            metadata={"org_id": str(org_id), "plan": request.plan.value},
        )

        sub = await self.repository.create_subscription(
            session,
            org_id=org_id,
            provider=provider.name,
            plan=request.plan.value,
            status="initiated",
            provider_reference=result.reference,
        )
        await session.flush()

        return InitializePaymentResponse(
            authorization_url=result.authorization_url,
            reference=result.reference,
            provider=provider.name,
            plan=request.plan.value,
        )

    async def verify_transaction(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        reference: str,
    ) -> VerifyTransactionResponse:
        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        provider = self._get_provider()
        result: PaymentVerifyResult = provider.verify(reference)

        sub = await self.repository.get_subscription_by_reference(
            session, reference
        )
        if result.success:
            plan = result.plan or (sub.plan if sub else Plan.FREE.value)
            await self.repository.update_org_plan(
                session,
                org,
                plan=plan,
                customer_id=result.provider_customer_id,
                subscription_id=result.provider_subscription_id,
            )
            if sub:
                await self.repository.update_subscription(
                    session,
                    sub,
                    status="active",
                    plan=plan,
                    provider_customer_id=result.provider_customer_id
                    or sub.provider_customer_id,
                    provider_subscription_id=result.provider_subscription_id
                    or sub.provider_subscription_id,
                )
            logger.info(
                "Activated %s plan for org %s via reference %s",
                plan, org_id, reference,
            )
        elif sub:
            await self.repository.update_subscription(
                session, sub, status="past_due"
            )

        return VerifyTransactionResponse(
            success=result.success,
            plan=result.plan or (sub.plan if sub else Plan.FREE.value),
            status=result.status or ("success" if result.success else "failed"),
        )

    # -- webhooks ----------------------------------------------------------------

    async def handle_webhook(
        self,
        session: AsyncSession,
        raw_body: bytes,
        signature: str | None,
        provider_name: str | None = None,
    ) -> WebhookResponse:
        provider = self.provider_registry.get(provider_name or settings.PAYMENT_PROVIDER)
        try:
            event = provider.construct_webhook_event(raw_body, signature or "")
        except ValueError as exc:
            raise UnauthorizedException(str(exc)) from exc

        event_type = event.get("event") or event.get("type") or ""
        logger.info("Received verified payment webhook event: %s", event_type)

        data = event.get("data") or {}
        if event_type in SUBSCRIPTION_EVENTS:
            await self._process_subscription_event(session, event_type, data)
        elif event_type in PAYMENT_SUCCESS_EVENTS:
            await self._process_payment_event(session, data)

        return WebhookResponse(received=True, event_type=event_type)

    async def _process_subscription_event(
        self, session: AsyncSession, event_type: str, data: dict[str, Any]
    ) -> None:
        customer_id = data.get("customer", {}).get("customer_code") if isinstance(
            data.get("customer"), dict
        ) else data.get("customer")
        plan_code = data.get("plan", {}).get("plan_code") if isinstance(
            data.get("plan"), dict
        ) else None

        org = await self.repository.get_org_by_provider_customer(
            session, "paystack", str(customer_id)
        ) if customer_id else None
        if not org:
            logger.info("No organization found for provider customer %s", customer_id)
            return

        if event_type == "subscription.disable":
            await self.repository.update_org_plan(
                session, org, plan=Plan.FREE.value, subscription_id=None
            )
            logger.info("Reset org %s to free plan (subscription disabled)", org.id)
        elif plan_code:
            plan = self._plan_from_paystack_code(plan_code)
            await self.repository.update_org_plan(session, org, plan=plan)
            logger.info("Updated org %s plan to '%s' via webhook", org.id, plan)

    async def _process_payment_event(
        self, session: AsyncSession, data: dict[str, Any]
    ) -> None:
        reference = data.get("reference")
        if not reference:
            return
        sub = await self.repository.get_subscription_by_reference(
            session, str(reference)
        )
        if not sub:
            logger.info("No subscription for reference %s", reference)
            return
        org = await self.repository.get_org(session, sub.organization_id)
        if not org:
            return
        await self.repository.update_org_plan(
            session, org, plan=sub.plan,
            customer_id=sub.provider_customer_id,
            subscription_id=sub.provider_subscription_id,
        )
        await self.repository.update_subscription(session, sub, status="active")

    @staticmethod
    def _plan_from_paystack_code(plan_code: str) -> str:
        # Paystack subscription plan codes are user-defined; map the common
        # prefixes to our canonical plan names, defaulting to standard.
        code = plan_code.lower()
        for plan in Plan:
            if plan.value in code:
                return plan.value
        return Plan.STANDARD.value


billing_service = BillingService()
