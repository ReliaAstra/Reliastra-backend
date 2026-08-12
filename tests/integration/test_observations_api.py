import pytest


@pytest.mark.asyncio
async def test_observations_flow(async_client, auth_data, db_session):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # Create a dependency so we have a source_id to attach observations to
    dep_res = await async_client.post(
        f"/v1/orgs/{org_id}/dependencies",
        headers=headers,
        json={
            "name": "Stripe API",
            "endpoint_url": "https://status.stripe.com",
            "method": "GET",
            "check_interval_seconds": 300,
        },
    )
    assert dep_res.status_code == 201, dep_res.text
    dep_id = dep_res.json()["id"]

    # Record an observation directly via the service (no external network).
    from app.modules.observations.constants import ObservationSourceType
    from app.modules.observations.schemas import ObservationCreate
    from app.modules.observations.service import observation_service

    await observation_service.record(
        db_session,
        ObservationCreate(
            source_type=ObservationSourceType.CUSTOMER_CHECK,
            source_id=dep_id,
            org_id=org_id,
            region="us-east",
            endpoint_url="https://status.stripe.com",
            latency_ms=120.5,
            status_code=200,
            response_time_ms=110.2,
        ),
    )
    await db_session.commit()

    # List observations for the dependency
    obs_res = await async_client.get(
        f"/v1/orgs/{org_id}/dependencies/{dep_id}/observations?limit=10",
        headers=headers,
    )
    assert obs_res.status_code == 200, obs_res.text
    data = obs_res.json()
    assert len(data) == 1
    assert data[0]["endpoint_url"] == "https://status.stripe.com"
    assert data[0]["is_up"] is True
