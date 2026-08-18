import pytest


@pytest.mark.asyncio
async def test_auth_endpoints(async_client):
    # Test register
    reg_res = await async_client.post(
        "/v1/auth/register",
        json={
            "email": "user@reliastra.com",
            "password": "Secret123!",
            "full_name": "Test Human",
            "org_name": "Reliastra MVP Org",
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    reg_data = reg_res.json()
    assert "tokens" in reg_data
    assert "user" in reg_data
    assert "organization" in reg_data
    assert "access_token" in reg_data["tokens"]
    assert "refresh_token" in reg_data["tokens"]

    # Test duplicate register -> 409
    dup_res = await async_client.post(
        "/v1/auth/register",
        json={
            "email": "user@reliastra.com",
            "password": "Secret123!",
            "full_name": "Test Human",
        },
    )
    assert dup_res.status_code == 409

    # Test login
    login_res = await async_client.post(
        "/v1/auth/login",
        json={
            "email": "user@reliastra.com",
            "password": "Secret123!",
        },
    )
    assert login_res.status_code == 200, login_res.text
    login_data = login_res.json()

    # Test refresh
    refresh_res = await async_client.post(
        "/v1/auth/refresh",
        json={"refresh_token": login_data["refresh_token"]},
    )
    assert refresh_res.status_code == 200, refresh_res.text
    ref_data = refresh_res.json()

    # Test logout
    logout_res = await async_client.post(
        "/v1/auth/logout",
        json={"refresh_token": ref_data["refresh_token"]},
    )
    assert logout_res.status_code == 204

    # Test health endpoint
    health_res = await async_client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"
