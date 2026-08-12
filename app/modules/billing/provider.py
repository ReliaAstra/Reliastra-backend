"""Payment provider abstraction layer (Phase 9).

The billing domain communicates exclusively through the ``PaymentProvider``
protocol so the core subscription logic is never coupled to a specific vendor.
``PaystackProvider`` is the mandated default; ``ManualProvider`` is a fallback
for development, staging, and manual plan activation (the rollback path called
out in the mandate's risk register).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PaymentInitResult:
    """Outcome of a payment-initialization request."""

    authorization_url: str
    reference: str
    access_code: str | None = None


@dataclass
class PaymentVerifyResult:
    """Outcome of verifying a payment transaction reference."""

    success: bool
    status: str = ""
    plan: str | None = None
    provider_customer_id: str | None = None
    provider_subscription_id: str | None = None
    amount_kobo: int = 0
    raw: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    """Interface every payment provider must implement."""

    name: str = "generic"

    @abstractmethod
    def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        plan: str,
        callback_url: str,
        metadata: dict | None = None,
    ) -> PaymentInitResult:
        """Create a payment session and return a redirect URL + reference."""

    @abstractmethod
    def verify(self, reference: str) -> PaymentVerifyResult:
        """Verify a transaction reference with the provider."""

    @abstractmethod
    def construct_webhook_event(self, raw_body: bytes, signature: str) -> dict:
        """Validate a webhook signature and return the decoded JSON event.

        Raises ``ValueError`` when the signature is missing or invalid.
        """


class PaystackProvider(PaymentProvider):
    """Paystack integration backed by the official REST API (https://api.paystack.co)."""

    name = "paystack"
    BASE_URL = "https://api.paystack.co"

    def __init__(self, secret_key: str, webhook_secret: str = "") -> None:
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self._client = httpx.Client(base_url=self.BASE_URL, timeout=10.0)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        plan: str,
        callback_url: str,
        metadata: dict | None = None,
    ) -> PaymentInitResult:
        if not self.secret_key:
            raise ValueError("Paystack secret key is not configured")
        metadata = metadata or {}
        metadata.setdefault("plan", plan)
        payload = {
            "email": email,
            "amount": amount_kobo,
            "callback_url": callback_url,
            "metadata": metadata,
        }
        resp = self._client.post(
            "/transaction/initialize", json=payload, headers=self._headers()
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("status") or not body.get("data"):
            raise ValueError(f"Paystack initialize failed: {body}")
        data = body["data"]
        return PaymentInitResult(
            authorization_url=data.get("authorization_url", ""),
            reference=data.get("reference", ""),
            access_code=data.get("access_code"),
        )

    def verify(self, reference: str) -> PaymentVerifyResult:
        if not self.secret_key:
            raise ValueError("Paystack secret key is not configured")
        resp = self._client.get(
            f"/transaction/verify/{reference}", headers=self._headers()
        )
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data") or {}
        status = data.get("status", "")
        success = bool(data.get("status") == "success")
        plan = None
        if data.get("metadata") and isinstance(data["metadata"], dict):
            plan = data["metadata"].get("plan")
        return PaymentVerifyResult(
            success=success,
            status=status,
            plan=plan,
            provider_customer_id=(
                str(data["customer"]["customer_code"])
                if isinstance(data.get("customer"), dict)
                else None
            ),
            provider_subscription_id=(
                str(data.get("subscription", {}).get("subscription_code"))
                if isinstance(data.get("subscription"), dict)
                else None
            ),
            amount_kobo=int(data.get("amount") or 0),
            raw=data,
        )

    def construct_webhook_event(self, raw_body: bytes, signature: str) -> dict:
        if not self.webhook_secret:
            raise ValueError("Paystack webhook secret is not configured")
        if not signature:
            raise ValueError("Missing Paystack webhook signature")
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha512
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ValueError("Invalid Paystack webhook signature")
        import json

        return json.loads(raw_body.decode("utf-8"))


class ManualProvider(PaymentProvider):
    """Development / rollback provider that activates plans without a gateway."""

    name = "manual"

    def __init__(self, callback_url: str = "") -> None:
        self.callback_url = callback_url

    def initialize(
        self,
        *,
        email: str,
        amount_kobo: int,
        plan: str,
        callback_url: str,
        metadata: dict | None = None,
    ) -> PaymentInitResult:
        return PaymentInitResult(
            authorization_url=self.callback_url or callback_url,
            reference="manual-" + hashlib.sha256(f"{email}:{plan}".encode()).hexdigest()[:16],
        )

    def verify(self, reference: str) -> PaymentVerifyResult:
        if not reference.startswith("manual-"):
            return PaymentVerifyResult(success=False, status="unknown")
        return PaymentVerifyResult(
            success=True,
            status="success",
            plan=reference.split("manual-", 1)[1][:16],
        )

    def construct_webhook_event(self, raw_body: bytes, signature: str) -> dict:
        import json

        return json.loads(raw_body.decode("utf-8"))


class PaymentProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, PaymentProvider] = {}
        self._default = "manual"

    def register(self, provider: PaymentProvider, *, default: bool = False) -> None:
        self._providers[provider.name] = provider
        if default:
            self._default = provider.name

    def get(self, name: str | None = None) -> PaymentProvider:
        key = name or self._default
        provider = self._providers.get(key)
        if not provider:
            raise ValueError(f"No payment provider registered for '{key}'")
        return provider

    def active_name(self) -> str:
        return self._default


def build_registry() -> PaymentProviderRegistry:
    """Build the provider registry from configuration."""
    from app.config import settings

    registry = PaymentProviderRegistry()
    registry.register(
        ManualProvider(callback_url=settings.PAYSTACK_CALLBACK_URL),
        default=settings.PAYMENT_PROVIDER == "manual",
    )
    registry.register(
        PaystackProvider(
            secret_key=settings.PAYSTACK_SECRET_KEY,
            webhook_secret=settings.PAYSTACK_WEBHOOK_SECRET,
        ),
        default=settings.PAYMENT_PROVIDER == "paystack",
    )
    return registry


payment_provider_registry = build_registry()
