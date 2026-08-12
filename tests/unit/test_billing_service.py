import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.modules.billing.service import BillingService
from app.modules.billing.provider import (
    ManualProvider,
    PaystackProvider,
    PaymentProviderRegistry,
    PaymentInitResult,
    PaymentVerifyResult,
)
from app.core.permissions import Plan


@pytest.mark.asyncio
async def test_get_plan_details():
    repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock(id=org_id, plan=Plan.STANDARD.value)
    repo.get_org = AsyncMock(return_value=fake_org)

    service = BillingService(repository=repo)
    session = AsyncMock()
    res = await service.get_plan_details(session, org_id)

    assert res.plan == Plan.STANDARD.value
    assert res.max_dependencies == 25
    assert res.min_check_interval_seconds == 60


@pytest.mark.asyncio
async def test_initialize_payment_with_manual_provider():
    repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock(id=org_id, plan="free", slug="acme")
    repo.get_org = AsyncMock(return_value=fake_org)
    repo.create_subscription = AsyncMock()

    registry = PaymentProviderRegistry()
    registry.register(
        ManualProvider(callback_url="http://localhost/cb"), default=True
    )

    service = BillingService(repository=repo, provider_registry=registry)
    session = AsyncMock()

    from app.modules.billing.schemas import InitializePaymentRequest

    res = await service.initialize_payment(
        session, org_id, InitializePaymentRequest(plan=Plan.STANDARD)
    )

    assert res.provider == "manual"
    assert res.plan == Plan.STANDARD.value
    assert res.reference.startswith("manual-")
    assert res.authorization_url == "http://localhost/cb"


@pytest.mark.asyncio
async def test_verify_transaction_success():
    repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock(id=org_id, plan="free")
    repo.get_org = AsyncMock(return_value=fake_org)
    sub = MagicMock(
        id=uuid.uuid4(), plan=Plan.STANDARD.value, provider_reference="manual-abc"
    )
    repo.get_subscription_by_reference = AsyncMock(return_value=sub)
    repo.update_org_plan = AsyncMock()
    repo.update_subscription = AsyncMock()

    registry = PaymentProviderRegistry()
    registry.register(
        ManualProvider(callback_url="http://localhost/cb"), default=True
    )

    service = BillingService(repository=repo, provider_registry=registry)
    session = AsyncMock()
    res = await service.verify_transaction(session, org_id, "manual-abc")

    assert res.success is True
    assert res.status == "success"
    repo.update_org_plan.assert_awaited()


def test_paystack_webhook_signature_verification():
    provider = PaystackProvider(
        secret_key="sk_test", webhook_secret="paystack-secret"
    )
    body = b'{"event": "charge.success", "data": {}}'
    import hashlib
    import hmac

    good_sig = hmac.new(
        b"paystack-secret", body, hashlib.sha512
    ).hexdigest()

    event = provider.construct_webhook_event(body, good_sig)
    assert event["event"] == "charge.success"

    with pytest.raises(ValueError):
        provider.construct_webhook_event(body, "tampered-signature")
