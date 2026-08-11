import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.modules.billing.service import BillingService
from app.core.permissions import Plan


@pytest.mark.asyncio
async def test_get_plan_details():
    repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock(
        id=org_id,
        plan=Plan.STANDARD.value,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
    )
    repo.get_org = AsyncMock(return_value=fake_org)

    service = BillingService(repository=repo)
    session = AsyncMock()
    res = await service.get_plan_details(session, org_id)

    assert res.plan == Plan.STANDARD.value
    assert res.stripe_customer_id == "cus_123"
    assert res.min_check_interval_seconds == 60


@pytest.mark.asyncio
async def test_handle_webhook():
    service = BillingService()
    session = AsyncMock()
    res = await service.handle_webhook(session, {"type": "invoice.paid", "data": {}})
    assert res["received"] is True
