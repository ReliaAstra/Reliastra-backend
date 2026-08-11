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

    # POST /v1/billing/webhook
    webhook_res = await async_client.post(
        "/v1/billing/webhook",
        json={
            "id": "evt_12345",
            "type": "invoice.payment_succeeded",
            "data": {"customer": "cus_123"},
        },
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["received"] is True
