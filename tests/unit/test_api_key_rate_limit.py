"""API-key authentication is throttled via api_key_limiter."""

import pytest

from app.core.rate_limit import api_key_limiter


@pytest.mark.asyncio
async def test_api_key_auth_is_rate_limited(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    create_res = await async_client.post(
        f"/v1/orgs/{org_id}/api-keys",
        headers=headers,
        json={"name": "rate-limit-key", "scopes": ["read:checks", "read:dependencies"]},
    )
    assert create_res.status_code == 201, create_res.text
    full_key = create_res.json()["full_key"]
    api_headers = {"Authorization": f"ApiKey {full_key}"}

    original_limit = api_key_limiter.limit
    api_key_limiter.limit = 2
    try:
        first = await async_client.get(
            f"/v1/orgs/{org_id}/dependencies", headers=api_headers
        )
        second = await async_client.get(
            f"/v1/orgs/{org_id}/dependencies", headers=api_headers
        )
        third = await async_client.get(
            f"/v1/orgs/{org_id}/dependencies", headers=api_headers
        )
    finally:
        api_key_limiter.limit = original_limit

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
