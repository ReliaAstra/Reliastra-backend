import pytest


@pytest.mark.asyncio
async def test_incidents_endpoints(async_client, auth_data, db_session):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # Create two dependencies
    dep1_res = await async_client.post(
        f"/v1/orgs/{org_id}/dependencies",
        headers=headers,
        json={
            "name": "Dep 1",
            "endpoint_url": "https://dep1.com",
            "check_interval_seconds": 300,
        },
    )
    dep1_id = dep1_res.json()["id"]

    dep2_res = await async_client.post(
        f"/v1/orgs/{org_id}/dependencies",
        headers=headers,
        json={
            "name": "Dep 2",
            "endpoint_url": "https://dep2.com",
            "check_interval_seconds": 300,
        },
    )
    dep2_id = dep2_res.json()["id"]

    # Directly trigger check_and_create_incident via service to simulate quorum failure
    from app.modules.incidents.service import incident_service

    inc1 = await incident_service.check_and_create_incident(
        db_session,
        org_id=auth_data["org_id"],
        dependency_id=dep1_id,
        error_message="500 Internal Error",
    )
    await db_session.commit()

    # GET /v1/orgs/{org_id}/incidents
    list_res = await async_client.get(
        f"/v1/orgs/{org_id}/incidents", headers=headers
    )
    assert list_res.status_code == 200
    inc_list = list_res.json()
    assert len(inc_list) == 1
    inc_id = inc_list[0]["id"]

    # GET /v1/orgs/{org_id}/incidents/{inc_id}
    get_res = await async_client.get(
        f"/v1/orgs/{org_id}/incidents/{inc_id}", headers=headers
    )
    assert get_res.status_code == 200
    assert "correlations" in get_res.json()

    # PATCH /v1/orgs/{org_id}/incidents/{inc_id}
    patch_res = await async_client.patch(
        f"/v1/orgs/{org_id}/incidents/{inc_id}",
        headers=headers,
        json={"description": "Updated incident text"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["description"] == "Updated incident text"

    # POST /v1/orgs/{org_id}/incidents/{inc_id}/correlate
    corr_res = await async_client.post(
        f"/v1/orgs/{org_id}/incidents/{inc_id}/correlate",
        headers=headers,
        json={
            "correlated_dependency_id": dep2_id,
            "correlation_confidence": 0.95,
            "correlation_method": "manual",
        },
    )
    assert corr_res.status_code == 201, corr_res.text
    assert corr_res.json()["correlation_confidence"] == 0.95

    # GET /v1/orgs/{org_id}/incidents/{inc_id}/evidence
    evid_res = await async_client.get(
        f"/v1/orgs/{org_id}/incidents/{inc_id}/evidence", headers=headers
    )
    assert evid_res.status_code == 200, evid_res.text
    assert "checksum" in evid_res.json()
