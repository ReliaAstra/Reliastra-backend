import hashlib
import hmac

import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_billing_endpoints(async_client, auth_data, monkeypatch):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    plan_res = await async_client.get(
        "/v1/billing/plan", headers=headers
    )
    assert plan_res.status_code == 200, plan_res.text
    plan_data = plan_res.json()
    assert plan_data["plan"] == "free"
    assert plan_data["max_dependencies"] == 3
    assert plan_data["subscription_status"] is None

    secret = "integration-paystack-secret"
    monkeypatch.setattr(settings, "PAYSTACK_SECRET_KEY", secret)
    body = b'{"event":"integration.test","data":{}}'
    signature = hmac.new(
        secret.encode(), body, hashlib.sha512
    ).hexdigest()
    webhook_res = await async_client.post(
        "/v1/billing/webhook",
        content=body,
        headers={
            "content-type": "application/json",
            "x-paystack-signature": signature,
        },
    )
    assert webhook_res.status_code == 200, webhook_res.text
    assert webhook_res.json()["received"] is True
