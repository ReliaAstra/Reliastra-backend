import hashlib
import hmac
import json

import pytest


@pytest.mark.asyncio
async def test_billing_endpoints(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # GET /v1/orgs/{org_id}/billing/plan
    plan_res = await async_client.get(
        f"/v1/orgs/{org_id}/billing/plan", headers=headers
    )
    assert plan_res.status_code == 200, plan_res.text
    plan_data = plan_res.json()
    assert plan_data["plan"] == "free"
    assert plan_data["max_dependencies"] == 5

    # POST /v1/orgs/{org_id}/billing/initialize-payment (manual provider in tests)
    init_res = await async_client.post(
        f"/v1/orgs/{org_id}/billing/initialize-payment",
        headers=headers,
        json={"plan": "standard"},
    )
    assert init_res.status_code == 200, init_res.text
    init_data = init_res.json()
    assert init_data["reference"]
    assert init_data["plan"] == "standard"

    # POST /v1/orgs/{org_id}/billing/verify-transaction
    verify_res = await async_client.post(
        f"/v1/orgs/{org_id}/billing/verify-transaction",
        headers=headers,
        json={"reference": init_data["reference"]},
    )
    assert verify_res.status_code == 200, verify_res.text
    assert verify_res.json()["success"] is True

    # GET /v1/orgs/{org_id}/billing/subscription
    sub_res = await async_client.get(
        f"/v1/orgs/{org_id}/billing/subscription", headers=headers
    )
    assert sub_res.status_code == 200, sub_res.text
    assert sub_res.json()["status"] == "active"

    # POST /v1/billing/webhook (manual provider accepts payload with signature header)
    body = json.dumps(
        {"event": "charge.success", "data": {"reference": init_data["reference"]}}
    ).encode("utf-8")
    webhook_res = await async_client.post(
        "/v1/billing/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Paystack-Signature": "any-signature",
        },
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["received"] is True
