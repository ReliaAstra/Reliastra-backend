import pytest


@pytest.mark.asyncio
async def test_dashboard_endpoints(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # GET /v1/orgs/{org_id}/dashboard/summary
    sum_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/summary", headers=headers
    )
    assert sum_res.status_code == 200, sum_res.text
    summary = sum_res.json()
    assert "active_dependencies_count" in summary

    # GET /v1/orgs/{org_id}/dashboard/dependency-health
    health_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/dependency-health", headers=headers
    )
    assert health_res.status_code == 200
    assert isinstance(health_res.json(), list)

    # GET /v1/orgs/{org_id}/dashboard/incident-timeline (FIX 17: paginated)
    timeline_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/incident-timeline", headers=headers
    )
    assert timeline_res.status_code == 200
    timeline_payload = timeline_res.json()
    assert isinstance(timeline_payload, dict)
    assert isinstance(timeline_payload["items"], list)

    # GET /v1/orgs/{org_id}/dashboard/vendor-status
    vendor_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/vendor-status", headers=headers
    )
    assert vendor_res.status_code == 200
    assert isinstance(vendor_res.json(), list)
