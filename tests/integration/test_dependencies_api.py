import pytest


@pytest.mark.asyncio
async def test_dependencies_endpoints(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # POST /v1/orgs/{org_id}/dependencies
    create_res = await async_client.post(
        f"/v1/orgs/{org_id}/dependencies",
        headers=headers,
        json={
            "name": "Stripe API",
            "endpoint_url": "https://status.stripe.com",
            "method": "GET",
            "check_interval_seconds": 300,
            "headers": {"Authorization": "Bearer sk_test_123"},
        },
    )
    assert create_res.status_code == 201, create_res.text
    dep = create_res.json()
    dep_id = dep["id"]
    assert dep["name"] == "Stripe API"
    # FIX 23: decrypted headers are never returned; only the presence flag.
    assert dep["headers"] is None
    assert dep["has_headers"] is True

    # GET /v1/orgs/{org_id}/dependencies
    list_res = await async_client.get(
        f"/v1/orgs/{org_id}/dependencies", headers=headers
    )
    assert list_res.status_code == 200
    deps = list_res.json()
    assert len(deps) == 1

    # GET /v1/orgs/{org_id}/dependencies/{dep_id}
    get_res = await async_client.get(
        f"/v1/orgs/{org_id}/dependencies/{dep_id}", headers=headers
    )
    assert get_res.status_code == 200

    # PATCH /v1/orgs/{org_id}/dependencies/{dep_id}
    patch_res = await async_client.patch(
        f"/v1/orgs/{org_id}/dependencies/{dep_id}",
        headers=headers,
        json={"name": "Stripe Payment API"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Stripe Payment API"

    # GET /v1/orgs/{org_id}/dependencies/{dep_id}/results
    res_res = await async_client.get(
        f"/v1/orgs/{org_id}/dependencies/{dep_id}/results", headers=headers
    )
    assert res_res.status_code == 200

    # GET /v1/orgs/{org_id}/dependencies/{dep_id}/history
    hist_res = await async_client.get(
        f"/v1/orgs/{org_id}/dependencies/{dep_id}/history", headers=headers
    )
    assert hist_res.status_code == 200
    assert "uptime_percentage" in hist_res.json()

    # DELETE /v1/orgs/{org_id}/dependencies/{dep_id}
    del_res = await async_client.delete(
        f"/v1/orgs/{org_id}/dependencies/{dep_id}", headers=headers
    )
    assert del_res.status_code == 204
