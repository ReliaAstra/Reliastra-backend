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

    # GET /v1/orgs/{org_id}/dashboard/incident-timeline
    timeline_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/incident-timeline", headers=headers
    )
    assert timeline_res.status_code == 200
    assert isinstance(timeline_res.json(), list)

    # GET /v1/orgs/{org_id}/dashboard/vendor-status
    vendor_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/vendor-status", headers=headers
    )
    assert vendor_res.status_code == 200
    assert isinstance(vendor_res.json(), list)

    # GET /v1/orgs/{org_id}/dashboard/latency (previously documented-but-missing)
    latency_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/latency?hours=24", headers=headers
    )
    assert latency_res.status_code == 200, latency_res.text
    assert isinstance(latency_res.json(), list)

    # GET /v1/orgs/{org_id}/dashboard/sla-degradation
    sla_res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/sla-degradation", headers=headers
    )
    assert sla_res.status_code == 200, sla_res.text
    assert sla_res.json()["period"] == "30d"
    assert sla_res.json()["affected_services"] == 0
