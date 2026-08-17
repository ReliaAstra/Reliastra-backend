import pytest


@pytest.mark.asyncio
async def test_evidence_endpoints(async_client, auth_data, db_session, mocker):
    headers = auth_data["headers"]
    org_id = auth_data["org_id"]

    # FIX 35: the storage client now raises on S3 failures (no local
    # fallback), so tests stub the uploads instead of relying on /tmp.
    mocker.patch(
        "app.modules.evidence.service.storage_client.upload_bytes",
        return_value="evidence/x.pdf",
    )
    mocker.patch(
        "app.modules.evidence.service.storage_client.get_presigned_url",
        return_value="http://storage.test/evidence/x.pdf",
    )

    # Create dep + incident + evidence
    dep_res = await async_client.post(
        f"/v1/orgs/{org_id}/dependencies",
        headers=headers,
        json={"name": "Dep Evid", "endpoint_url": "https://dep.com"},
    )
    dep_id = dep_res.json()["id"]

    from app.modules.incidents.service import incident_service

    inc = await incident_service.check_and_create_incident(
        db_session,
        org_id=auth_data["org_id"],
        dependency_id=dep_id,
        error_message="500 Internal Server Error",
    )
    await db_session.commit()

    evid_trigger = await async_client.get(
        f"/v1/orgs/{org_id}/incidents/{inc.id}/evidence", headers=headers
    )
    assert evid_trigger.status_code == 200
    report_id = evid_trigger.json()["id"]

    # GET /v1/orgs/{org_id}/evidence
    list_res = await async_client.get(
        f"/v1/orgs/{org_id}/evidence", headers=headers
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # GET /v1/orgs/{org_id}/evidence/{report_id}
    get_res = await async_client.get(
        f"/v1/orgs/{org_id}/evidence/{report_id}", headers=headers
    )
    assert get_res.status_code == 200
    assert "download_url" in get_res.json()

    # POST /v1/orgs/{org_id}/evidence/{report_id}/regenerate
    regen_res = await async_client.post(
        f"/v1/orgs/{org_id}/evidence/{report_id}/regenerate", headers=headers
    )
    assert regen_res.status_code == 201
    assert "checksum" in regen_res.json()
