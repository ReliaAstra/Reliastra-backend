import pytest


@pytest.mark.asyncio
async def test_notifications_endpoints(async_client, auth_data, mocker):
    mocker.patch(
        "app.modules.notifications.service.email_client.send_email",
        return_value=True,
    )
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # POST /v1/orgs/{org_id}/notifications/configs
    create_res = await async_client.post(
        "/v1/notifications/configs",
        headers=headers,
        json={
            "channel_type": "email",
            "config": {"email": "alert@reliastra.com"},
            "is_active": True,
        },
    )
    assert create_res.status_code == 201, create_res.text
    cfg = create_res.json()
    cfg_id = cfg["id"]
    assert cfg["channel_type"] == "email"

    # GET /v1/orgs/{org_id}/notifications/configs
    list_res = await async_client.get(
        "/v1/notifications/configs", headers=headers
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # GET /v1/orgs/{org_id}/notifications/configs/{config_id}
    get_res = await async_client.get(
        f"/v1/notifications/configs/{cfg_id}", headers=headers
    )
    assert get_res.status_code == 200

    # PATCH /v1/orgs/{org_id}/notifications/configs/{config_id}
    patch_res = await async_client.patch(
        f"/v1/notifications/configs/{cfg_id}",
        headers=headers,
        json={"is_active": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False

    # POST /v1/orgs/{org_id}/notifications/test
    test_res = await async_client.post(
        "/v1/notifications/test",
        headers=headers,
        json={"config_id": cfg_id},
    )
    assert test_res.status_code == 200
    assert test_res.json()["success"] is True

    # DELETE /v1/orgs/{org_id}/notifications/configs/{config_id}
    del_res = await async_client.delete(
        f"/v1/notifications/configs/{cfg_id}", headers=headers
    )
    assert del_res.status_code == 204
