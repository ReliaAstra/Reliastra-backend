import pytest


@pytest.mark.asyncio
async def test_agency_clients_and_applications(async_client, auth_data):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # Create a client
    create_client = await async_client.post(
        f"/v1/orgs/{org_id}/clients",
        headers=headers,
        json={"name": "Acme Retail", "description": "E-commerce client"},
    )
    assert create_client.status_code == 201, create_client.text
    client = create_client.json()
    client_id = client["id"]

    # List clients
    list_clients = await async_client.get(
        f"/v1/orgs/{org_id}/clients", headers=headers
    )
    assert list_clients.status_code == 200
    assert len(list_clients.json()) == 1

    # Create application under client
    create_app = await async_client.post(
        f"/v1/orgs/{org_id}/clients/{client_id}/applications",
        headers=headers,
        json={"name": "Checkout Service"},
    )
    assert create_app.status_code == 201, create_app.text
    app = create_app.json()
    assert app["client_id"] == client_id

    # List applications for client
    list_apps = await async_client.get(
        f"/v1/orgs/{org_id}/clients/{client_id}/applications", headers=headers
    )
    assert list_apps.status_code == 200
    assert len(list_apps.json()) == 1

    # Patch application
    patch_app = await async_client.patch(
        f"/v1/orgs/{org_id}/applications/{app['id']}",
        headers=headers,
        json={"name": "Checkout Service v2"},
    )
    assert patch_app.status_code == 200
    assert patch_app.json()["name"] == "Checkout Service v2"

    # Delete application
    del_app = await async_client.delete(
        f"/v1/orgs/{org_id}/applications/{app['id']}", headers=headers
    )
    assert del_app.status_code == 204

    # Delete client
    del_client = await async_client.delete(
        f"/v1/orgs/{org_id}/clients/{client_id}", headers=headers
    )
    assert del_client.status_code == 204
