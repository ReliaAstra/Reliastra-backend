"""Tests for FIX 17: cursor pagination on list endpoints."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_vendors_list_is_cursor_paginated(async_client, db_session):
    from app.modules.vendors.service import vendor_service

    await vendor_service.seed_vendors(db_session)
    await db_session.commit()

    res = await async_client.get("/v1/public/vendors", params={"limit": 3})
    assert res.status_code == 200
    payload = res.json()
    assert set(payload.keys()) >= {"items", "next_cursor", "has_more"}
    assert len(payload["items"]) == 3
    assert payload["has_more"] is True
    assert payload["next_cursor"] is not None

    # Follow the cursor — the next page must not repeat items.
    page2 = await async_client.get(
        "/v1/public/vendors",
        params={"limit": 3, "cursor": payload["next_cursor"]},
    )
    assert page2.status_code == 200
    page2_payload = page2.json()
    first_ids = {item["id"] for item in payload["items"]}
    second_ids = {item["id"] for item in page2_payload["items"]}
    assert first_ids.isdisjoint(second_ids)


@pytest.mark.asyncio
async def test_vendors_list_respects_limit_bound(async_client):
    res = await async_client.get("/v1/public/vendors", params={"limit": 10_000})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_incident_timeline_is_cursor_paginated(async_client, auth_data, db_session):
    from app.modules.dependencies.repository import DependencyRepository
    from app.modules.incidents.repository import IncidentRepository

    org_id = uuid.UUID(auth_data["org_id"])
    for i in range(3):
        dep = await DependencyRepository.create(
            db_session,
            org_id=org_id,
            application_id=None,
            name=f"dep-{i}",
            endpoint_url=f"https://example.com/{i}",
            method="GET",
            headers=None,
            expected_status_codes=[200],
            timeout_seconds=10,
            check_interval_seconds=300,
            regions=["us-east"],
        )
        await IncidentRepository.create(
            db_session,
            org_id=org_id,
            dependency_id=dep.id,
            severity="major",
            description=f"incident {i}",
        )
    await db_session.commit()

    res = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/incident-timeline",
        headers=auth_data["headers"],
        params={"limit": 2},
    )
    assert res.status_code == 200
    payload = res.json()
    assert set(payload.keys()) >= {"items", "next_cursor", "has_more"}
    assert len(payload["items"]) == 2
    assert payload["has_more"] is True

    page2 = await async_client.get(
        f"/v1/orgs/{org_id}/dashboard/incident-timeline",
        headers=auth_data["headers"],
        params={"limit": 2, "cursor": payload["next_cursor"]},
    )
    assert page2.status_code == 200
    first_ids = {item["id"] for item in payload["items"]}
    second_ids = {item["id"] for item in page2.json()["items"]}
    assert first_ids.isdisjoint(second_ids)
