import pytest


@pytest.mark.asyncio
async def test_ai_provider_config(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    create = await async_client.post(
        f"/v1/orgs/{org_id}/ai-providers",
        headers=headers,
        json={
            "name": "GPT-4 Production",
            "provider_type": "openai_compatible",
            "endpoint_url": "https://api.openai.com/v1",
            "api_key": "sk-test-abc",
            "model_name": "gpt-4",
            "is_default": True,
            "max_tokens": 4096,
            "temperature": 0.3,
            "enabled": True,
        },
    )
    assert create.status_code == 201, create.text
    provider = create.json()
    pid = provider["id"]
    assert provider["provider_type"] == "openai_compatible"
    assert "api_key" not in provider  # never expose the raw key

    # List
    lst = await async_client.get(
        f"/v1/orgs/{org_id}/ai-providers", headers=headers
    )
    assert lst.status_code == 200
    assert len(lst.json()) == 1

    # Patch
    patch = await async_client.patch(
        f"/v1/orgs/{org_id}/ai-providers/{pid}",
        headers=headers,
        json={"enabled": False},
    )
    assert patch.status_code == 200
    assert patch.json()["enabled"] is False

    # Delete
    delete = await async_client.delete(
        f"/v1/orgs/{org_id}/ai-providers/{pid}", headers=headers
    )
    assert delete.status_code == 204
