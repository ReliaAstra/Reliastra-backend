import pytest


@pytest.mark.asyncio
async def test_api_keys_endpoints_and_programmatic_auth(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # POST /v1/orgs/{org_id}/api-keys
    create_res = await async_client.post(
        "/v1/api-keys",
        headers=headers,
        json={"name": "Programmatic CI Key", "scopes": ["read:checks", "write:dependencies"]},
    )
    assert create_res.status_code == 201, create_res.text
    key_data = create_res.json()
    full_key = key_data["full_key"]
    key_id = key_data["id"]
    assert full_key.startswith("rel_")

    # GET /v1/orgs/{org_id}/api-keys
    list_res = await async_client.get(
        "/v1/api-keys", headers=headers
    )
    assert list_res.status_code == 200
    keys = list_res.json()
    assert len(keys) == 1
    # Ensure full_key is NEVER returned in list
    assert "full_key" not in keys[0]

    # Test programmatic API Key authentication on an endpoint
    api_key_headers = {"Authorization": f"ApiKey {full_key}"}
    dep_list_res = await async_client.get(
        "/v1/dependencies", headers=api_key_headers
    )
    assert dep_list_res.status_code == 200, dep_list_res.text

    # DELETE /v1/orgs/{org_id}/api-keys/{key_id}
    del_res = await async_client.delete(
        f"/v1/api-keys/{key_id}", headers=headers
    )
    assert del_res.status_code == 204

    # Verify key is revoked and fails auth
    revoked_res = await async_client.get(
        "/v1/dependencies", headers=api_key_headers
    )
    assert revoked_res.status_code == 401
