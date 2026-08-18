import pytest


@pytest.mark.asyncio
async def test_orgs_endpoints(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # GET /v1/orgs
    list_res = await async_client.get("/v1/orgs", headers=headers)
    assert list_res.status_code == 200
    orgs = list_res.json()
    assert len(orgs) >= 1

    # POST /v1/orgs
    create_res = await async_client.post(
        "/v1/orgs",
        headers=headers,
        json={"name": "Second Org", "slug": "second-org"},
    )
    assert create_res.status_code == 201, create_res.text
    new_org = create_res.json()
    assert new_org["name"] == "Second Org"

    # GET /v1/orgs/{org_id}
    get_res = await async_client.get(f"/v1/orgs/{org_id}", headers=headers)
    assert get_res.status_code == 200

    # PATCH /v1/orgs/{org_id}
    patch_res = await async_client.patch(
        f"/v1/orgs/{org_id}",
        headers=headers,
        json={"name": "Renamed Org"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Renamed Org"

    # Invite a member
    # First create another user so email exists
    await async_client.post(
        "/v1/auth/register",
        json={
            "email": "invitee@reliastra.com",
            "password": "Password123!",
            "full_name": "Invited User",
        },
    )

    invite_res = await async_client.post(
        f"/v1/orgs/{org_id}/members",
        headers=headers,
        json={"email": "invitee@reliastra.com", "role": "member"},
    )
    assert invite_res.status_code == 201, invite_res.text
    member_data = invite_res.json()

    # GET /v1/orgs/{org_id}/members
    members_res = await async_client.get(
        f"/v1/orgs/{org_id}/members", headers=headers
    )
    assert members_res.status_code == 200
    members_payload = members_res.json()
    members = members_payload["items"]
    assert members_payload["has_more"] is False
    assert len(members) == 2

    # PATCH /v1/orgs/{org_id}/members/{member_id}
    role_res = await async_client.patch(
        f"/v1/orgs/{org_id}/members/{member_data['id']}",
        headers=headers,
        json={"role": "admin"},
    )
    assert role_res.status_code == 200
    assert role_res.json()["role"] == "admin"

    # DELETE /v1/orgs/{org_id}/members/{member_id}
    del_res = await async_client.delete(
        f"/v1/orgs/{org_id}/members/{member_data['id']}",
        headers=headers,
    )
    assert del_res.status_code == 204

    after_del = await async_client.get(
        f"/v1/orgs/{org_id}/members", headers=headers
    )
    assert after_del.status_code == 200
    remaining_ids = {m["id"] for m in after_del.json()["items"]}
    assert member_data["id"] not in remaining_ids

    # Re-invite restores the soft-deleted membership
    reinvite = await async_client.post(
        f"/v1/orgs/{org_id}/members",
        headers=headers,
        json={"email": "invitee@reliastra.com", "role": "member"},
    )
    assert reinvite.status_code == 201, reinvite.text
