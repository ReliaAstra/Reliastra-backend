import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import Any

import httpx
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
    Plan,
    get_dependency_limit,
    get_discounted_price_usd,
    get_min_check_interval,
    get_plan_price_usd,
)
from app.modules.billing.repository import BillingRepository
from app.modules.billing.schemas import (
    InitializePaymentRequest,
    InitializePaymentResponse,
    PaystackWebhookResponse,
    PlanDetailsResponse,
    VerifyTransactionResponse,
)

logger = logging.getLogger(__name__)


class PaystackClient:
    """Small async Paystack client built on the project's existing HTTP stack."""

    def __init__(self) -> None:
        self.base_url = settings.PAYSTACK_BASE_URL.rstrip("/")
        self.secret_key = settings.PAYSTACK_SECRET_KEY

    def _headers(self) -> dict[str, str]:
        if not self.secret_key:
            raise ValidationException("Paystack is not configured")
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def initialize_transaction(
        self,
        email: str,
        amount: int,
        plan: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.base_url}/transaction/initialize",
                headers=self._headers(),
                json={
                    "email": email,
                    "amount": amount,
                    "plan": plan,
                    "metadata": metadata or {},
                },
            )
            response.raise_for_status()
            return response.json()

    async def verify_transaction(self, reference: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/transaction/verify/{reference}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    async def fetch_plan(self, plan_code_or_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.base_url}/plan/{plan_code_or_id}",
                headers=self._headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()


paystack_client = PaystackClient()

# Amounts are in kobo (1 USD = 100 kobo).  Prices match the pricing page:
#   Standard:   $49/mo  ->  4,900 kobo
#   Professional: $99/mo  ->  9,900 kobo
# Agency plans use custom pricing and are not self-serve.
# Founding customers receive 40% off (applied at initialization).
PLAN_AMOUNTS: dict[str, int] = {
    Plan.STANDARD.value: 4900,
    Plan.PROFESSIONAL.value: 9900,
    Plan.AGENCY.value: 0,
}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _normalized_plan(data: dict[str, Any]) -> str:
    metadata = data.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    candidate: Any = metadata.get("plan")
    if not candidate:
        plan_data = data.get("plan")
        if isinstance(plan_data, dict):
            candidate = plan_data.get("name") or plan_data.get("plan_code")
        elif isinstance(plan_data, str):
            candidate = plan_data
    candidate = str(candidate or Plan.STANDARD.value).strip().lower()
    valid_plans = {plan.value for plan in Plan}
    return candidate if candidate in valid_plans else Plan.STANDARD.value


class BillingService:
    def __init__(
        self,
        repository: BillingRepository = BillingRepository(),
        client: PaystackClient = paystack_client,
    ) -> None:
        self.repository = repository
        self.client = client

    async def get_plan_details(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> PlanDetailsResponse:
        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")
        subscription = await self.repository.get_subscription(session, org_id)
        is_founding = getattr(org, "is_founding_customer", False)
        discount_pct = getattr(org, "founding_discount_pct", 0)
        base_price = get_plan_price_usd(org.plan)
        discounted_price = None
        if is_founding and base_price > 0:
            discounted_price = get_discounted_price_usd(org.plan)
        return PlanDetailsResponse(
            org_id=org.id,
            plan=org.plan,
            max_dependencies=get_dependency_limit(org.plan),
            min_check_interval_seconds=get_min_check_interval(org.plan),
            subscription_status=subscription.status if subscription else None,
            current_period_end=(
                subscription.current_period_end if subscription else None
            ),
            is_founding_customer=is_founding,
            founding_discount_pct=discount_pct,
            price_usd=base_price,
            discounted_price_usd=discounted_price,
        )

    async def initialize_payment(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: InitializePaymentRequest,
    ) -> InitializePaymentResponse:
        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        plan = request.plan.lower()
        if plan not in PLAN_AMOUNTS:
            raise ValidationException(f"Invalid paid plan: {plan}")
        if plan == Plan.AGENCY.value:
            raise ValidationException(
                "Agency plans require custom pricing. Please contact sales."
            )

        base_amount = PLAN_AMOUNTS[plan]
        is_founding = getattr(org, "is_founding_customer", False)
        discount_pct = 0

        if is_founding and plan in (Plan.STANDARD.value, Plan.PROFESSIONAL.value):
            discount_pct = FOUNDING_DISCOUNT_PCT
            discounted_kobo = base_amount - (base_amount * discount_pct // 100)
            logger.info(
                "Founding customer discount applied: org=%s plan=%s "
                "base=%dkobo discounted=%dkobo (%d%% off)",
                org_id,
                plan,
                base_amount,
                discounted_kobo,
                discount_pct,
            )
            base_amount = discounted_kobo

        email = str(request.email) if request.email else None
        if not email:
            from app.modules.organizations.repository import OrganizationRepository
            from app.modules.users.repository import UserRepository

            members = await OrganizationRepository.list_members(session, org_id)
            owner = next((member for member in members if member.role == "owner"), None)
            if owner:
                user = await UserRepository.get_by_id(session, owner.user_id)
                email = user.email if user else None
        if not email:
            raise ValidationException(
                "No email is available for payment initialization"
            )

        try:
            result = await self.client.initialize_transaction(
                email=email,
                amount=base_amount,
                plan=plan,
                metadata={
                    "org_id": str(org_id),
                    "plan": plan,
                    "is_founding": str(is_founding).lower(),
                    "discount_pct": str(discount_pct),
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Paystack initialization failed: %s", exc)
            raise ValidationException("Paystack transaction initialization failed") from exc

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if not result.get("status") or not data:
            raise ValidationException("Paystack transaction initialization failed")
        try:
            return InitializePaymentResponse(
                authorization_url=data["authorization_url"],
                reference=data["reference"],
                access_code=data["access_code"],
            )
        except KeyError as exc:
            raise ValidationException("Paystack returned an incomplete response") from exc

    async def verify_transaction(
        self, session: AsyncSession, reference: str
    ) -> VerifyTransactionResponse:
        try:
            result = await self.client.verify_transaction(reference)
        except httpx.HTTPError as exc:
            logger.warning("Paystack verification failed for %s: %s", reference, exc)
            raise ValidationException("Unable to verify Paystack transaction") from exc

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if not result.get("status") or data.get("status") != "success":
            return VerifyTransactionResponse(
                verified=False, plan=Plan.FREE.value, reference=reference
            )

        metadata = data.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        org_id_raw = metadata.get("org_id")
        if not org_id_raw:
            logger.warning("Verified transaction %s has no organization metadata", reference)
            return VerifyTransactionResponse(
                verified=False, plan=Plan.FREE.value, reference=reference
            )
        try:
            org_id = uuid.UUID(str(org_id_raw))
        except ValueError as exc:
            raise ValidationException("Invalid organization metadata from Paystack") from exc

        org = await self.repository.get_org(session, org_id)
        if not org:
            raise ResourceNotFoundException("Organization not found")

        plan = _normalized_plan(data)
        customer = data.get("customer")
        customer = customer if isinstance(customer, dict) else {}
        customer_code = customer.get("customer_code")
        subscription = await self.repository.get_subscription(session, org_id)
        values = {
            "plan": plan,
            "status": "active",
            "provider_customer_id": customer_code,
            "provider_subscription_id": str(
                data.get("subscription_code") or reference
            ),
            "current_period_start": _parse_datetime(data.get("paid_at")),
            "current_period_end": _parse_datetime(data.get("next_payment_date")),
        }
        if subscription:
            await self.repository.update_subscription(
                session, subscription, **values
            )
        else:
            await self.repository.create_subscription(
                session, org_id, **values
            )

        from app.modules.organizations.repository import OrganizationRepository

        await OrganizationRepository.update(session, org, plan=plan)
        return VerifyTransactionResponse(
            verified=True, plan=plan, reference=reference
        )

    async def handle_webhook(
        self,
        session: AsyncSession,
        payload: dict[str, Any],
        signature: str | None = None,
        raw_body: bytes | None = None,
    ) -> PaystackWebhookResponse:
        if not signature:
            raise UnauthorizedException("Missing Paystack webhook signature")
        if not raw_body:
            raise UnauthorizedException("Missing raw request body")
        if not settings.PAYSTACK_SECRET_KEY:
            raise UnauthorizedException("Paystack webhook secret is not configured")

        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise UnauthorizedException("Invalid Paystack webhook signature")

        event_type = str(payload.get("event", ""))
        data = payload.get("data")
        data = data if isinstance(data, dict) else {}
        logger.info("Received verified Paystack webhook: %s", event_type)

        if event_type == "charge.success" and data.get("reference"):
            await self.verify_transaction(session, str(data["reference"]))
        elif event_type == "subscription.create":
            await self._upsert_webhook_subscription(session, data)
        elif event_type in {"subscription.disable", "subscription.not_renew"}:
            await self._disable_webhook_subscription(session, data)

        return PaystackWebhookResponse(received=True, event_type=event_type)

    async def _upsert_webhook_subscription(
        self, session: AsyncSession, data: dict[str, Any]
    ) -> None:
        metadata = data.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        org_id_raw = metadata.get("org_id")
        if not org_id_raw:
            logger.info("Ignoring subscription event without org_id metadata")
            return
        try:
            org_id = uuid.UUID(str(org_id_raw))
        except ValueError:
            logger.warning("Ignoring subscription event with invalid org_id")
            return
        org = await self.repository.get_org(session, org_id)
        if not org:
            logger.info("Ignoring subscription event for unknown org %s", org_id)
            return

        customer = data.get("customer")
        customer = customer if isinstance(customer, dict) else {}
        values = {
            "plan": _normalized_plan(data),
            "status": str(data.get("status") or "active"),
            "provider_customer_id": customer.get("customer_code"),
            "provider_subscription_id": data.get("subscription_code"),
            "current_period_start": _parse_datetime(data.get("createdAt")),
            "current_period_end": _parse_datetime(data.get("next_payment_date")),
        }
        subscription = await self.repository.get_subscription(session, org_id)
        if subscription:
            await self.repository.update_subscription(
                session, subscription, **values
            )
        else:
            await self.repository.create_subscription(
                session, org_id, **values
            )

        from app.modules.organizations.repository import OrganizationRepository

        await OrganizationRepository.update(session, org, plan=values["plan"])

    async def _disable_webhook_subscription(
        self, session: AsyncSession, data: dict[str, Any]
    ) -> None:
        customer = data.get("customer")
        customer = customer if isinstance(customer, dict) else {}
        customer_code = customer.get("customer_code")
        if not customer_code:
            return
        org = await self.repository.get_org_by_provider_customer(
            session, str(customer_code)
        )
        if not org:
            return
        subscription = await self.repository.get_subscription(session, org.id)
        if subscription:
            await self.repository.update_subscription(
                session, subscription, status="inactive"
            )

        from app.modules.organizations.repository import OrganizationRepository

        await OrganizationRepository.update(
            session, org, plan=Plan.FREE.value
        )


billing_service = BillingService()
