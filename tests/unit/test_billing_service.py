import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.core.permissions import Plan
from app.modules.billing.schemas import InitializePaymentRequest
from app.modules.billing.service import BillingService


@pytest.mark.asyncio
async def test_get_plan_details():
    repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock(id=org_id, plan=Plan.STANDARD.value)
    fake_subscription = MagicMock(
        status="active", current_period_end=datetime.now(timezone.utc)
    )
    repo.get_org = AsyncMock(return_value=fake_org)
    repo.get_subscription = AsyncMock(return_value=fake_subscription)

    service = BillingService(repository=repo)
    res = await service.get_plan_details(AsyncMock(), org_id)

    assert res.plan == Plan.STANDARD.value
    assert res.subscription_status == "active"
    assert res.min_check_interval_seconds == 15


@pytest.mark.asyncio
async def test_initialize_payment():
    org_id = uuid.uuid4()
    repository = MagicMock()
    repository.get_org = AsyncMock(
        return_value=MagicMock(id=org_id, plan=Plan.FREE.value)
    )
    client = MagicMock()
    client.initialize_transaction = AsyncMock(
        return_value={
            "status": True,
            "data": {
                "authorization_url": "https://checkout.paystack.com/test",
                "reference": "ref_test",
                "access_code": "access_test",
            },
        }
    )
    service = BillingService(repository=repository, client=client)
    response = await service.initialize_payment(
        AsyncMock(),
        org_id,
        InitializePaymentRequest(
            plan="standard", email="owner@example.com"
        ),
    )
    assert response.reference == "ref_test"
    client.initialize_transaction.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook(monkeypatch):
    secret = "paystack-unit-secret"
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", secret)
    payload = {"event": "unit.test", "data": {}}
    raw_body = b'{"event":"unit.test","data":{}}'
    signature = hmac.new(
        secret.encode(), raw_body, hashlib.sha512
    ).hexdigest()

    service = BillingService()
    response = await service.handle_webhook(
        AsyncMock(), payload, signature=signature, raw_body=raw_body
    )
    assert response.received is True
    assert response.event_type == "unit.test"
