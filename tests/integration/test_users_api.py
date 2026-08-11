import pytest


@pytest.mark.asyncio
async def test_users_endpoints(async_client, auth_data):
    headers = auth_data["headers"]

    # GET /v1/users/me
    get_res = await async_client.get("/v1/users/me", headers=headers)
    assert get_res.status_code == 200, get_res.text
    data = get_res.json()
    assert data["email"] == auth_data["email"]

    # PATCH /v1/users/me
    patch_res = await async_client.patch(
        "/v1/users/me",
        headers=headers,
        json={"full_name": "Updated Name"},
    )
    assert patch_res.status_code == 200, patch_res.text
    updated = patch_res.json()
    assert updated["full_name"] == "Updated Name"
