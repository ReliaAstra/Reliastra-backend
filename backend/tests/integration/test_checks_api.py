import pytest


@pytest.mark.asyncio
async def test_checks_endpoints(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    res = await async_client.get(
        "/v1/checks/recent", headers=headers
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)
