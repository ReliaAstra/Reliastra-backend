import http.server
import threading
import uuid
import httpx
import pytest
from app.modules.checks.service import check_service


from app.infrastructure.email import email_client

class Handler500(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"500 Internal Server Error - Simulated Vendor Outage")

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def test_http_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler500)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


@pytest.mark.asyncio
async def test_full_e2e_flow(async_client, db_session, test_http_server, mocker):
    # This test intentionally uses a loopback HTTP fixture. Bypass URL
    # validation only in the test; production SSRF protection remains enabled.
    # FIX 26: the check service pins connections via a resolved target; the
    # test supplies a pinned target for the loopback server and a real
    # transport so requests actually reach the fixture.
    from app.core.ssrf_protection import PinnedTarget

    loopback_url = test_http_server
    mocker.patch(
        "app.modules.checks.service.resolve_pinned_target",
        return_value=PinnedTarget(
            url=loopback_url,
            hostname="127.0.0.1",
            port=int(loopback_url.rsplit(":", 1)[1]),
            ips=["127.0.0.1"],
        ),
    )
    mocker.patch(
        "app.modules.checks.service.pinned_transport_for",
        return_value=httpx.AsyncHTTPTransport(),
    )
    # FIX 35: storage failures raise — stub uploads in the test harness.
    mocker.patch(
        "app.modules.evidence.service.storage_client.upload_bytes",
        return_value="evidence/x.pdf",
    )
    mocker.patch(
        "app.modules.evidence.service.storage_client.get_presigned_url",
        return_value="http://storage.test/evidence/x.pdf",
    )
    mocker.patch(
        "app.modules.evidence.tasks.generate_evidence_report.apply_async"
    )
    # Spy on notification sending
    send_email_spy = mocker.spy(email_client, "send_email")

    # 1. Create org + user
    reg_res = await async_client.post(
        "/v1/auth/register",
        json={
            "email": "e2e-owner@reliastra.com",
            "password": "SuperSecret123!",
            "full_name": "E2E Owner",
            "org_name": "E2E Test Organization",
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    body = reg_res.json()
    token_data = body["tokens"]
    org_id = body["organization"]["id"]
    headers = {
        "Authorization": f"Bearer {token_data['access_token']}",
        "X-Organization-ID": org_id,
    }

    # 2. Configure notification channel
    notif_res = await async_client.post(
        "/v1/notifications/configs",
        headers=headers,
        json={
            "channel_type": "email",
            "config": {"email": "alert@reliastra.com"},
            "is_active": True,
        },
    )
    assert notif_res.status_code == 201

    # 3. Create two dependencies pointing to the 500 test server
    dep1_res = await async_client.post(
        "/v1/dependencies",
        headers=headers,
        json={
            "name": "Vendor Stripe API",
            "endpoint_url": f"{test_http_server}/stripe",
            "method": "GET",
            "check_interval_seconds": 300,
            "expected_status_codes": [200],
        },
    )
    assert dep1_res.status_code == 201
    dep1_id = dep1_res.json()["id"]

    dep2_res = await async_client.post(
        "/v1/dependencies",
        headers=headers,
        json={
            "name": "Internal Customer Service",
            "endpoint_url": f"{test_http_server}/internal",
            "method": "GET",
            "check_interval_seconds": 300,
            "expected_status_codes": [200],
        },
    )
    assert dep2_res.status_code == 201
    dep2_id = dep2_res.json()["id"]

    # 4. Trigger check execution for Dep 1 (2 regions to confirm quorum failure)
    res1 = await check_service.execute_check(
        db_session, uuid.UUID(dep1_id), "us-east"
    )
    assert res1 is not None
    assert res1.is_up is False
    assert res1.status_code == 500
    assert res1.quorum_confirmed is False

    res2 = await check_service.execute_check(
        db_session, uuid.UUID(dep1_id), "eu-west"
    )
    assert res2 is not None
    assert res2.is_up is False
    assert res2.quorum_confirmed is True

    # Also trigger failing check for Dep 2 to trigger correlation
    await check_service.execute_check(
        db_session, uuid.UUID(dep2_id), "us-east"
    )
    await check_service.execute_check(
        db_session, uuid.UUID(dep2_id), "eu-west"
    )

    await db_session.commit()

    # 5. Verify incidents created
    inc_list_res = await async_client.get(
        "/v1/incidents", headers=headers
    )
    assert inc_list_res.status_code == 200
    incidents = inc_list_res.json()["data"]
    assert len(incidents) >= 1
    target_incident = next(
        inc for inc in incidents if inc["dependency_id"] == dep1_id
    )
    inc_id = target_incident["id"]
    assert target_incident["status"] == "open"

    # 6. Verify correlation created between Dep 1 and Dep 2
    inc_detail_res = await async_client.get(
        f"/v1/incidents/{inc_id}", headers=headers
    )
    assert inc_detail_res.status_code == 200
    detail_data = inc_detail_res.json()
    correlations = detail_data["correlations"]
    assert len(correlations) >= 1
    assert any(
        c["correlated_dependency_id"] == dep2_id for c in correlations
    )

    # 7. Resolve incident and verify evidence report generated
    resolve_res = await async_client.patch(
        f"/v1/incidents/{inc_id}",
        headers=headers,
        json={"status": "resolved"},
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json()["status"] == "resolved"

    # Generate/fetch evidence report
    evid_res = await async_client.get(
        f"/v1/incidents/{inc_id}/evidence", headers=headers
    )
    assert evid_res.status_code == 200
    evid_data = evid_res.json()
    assert len(evid_data["checksum"]) == 64  # SHA-256 hex string length
    assert evid_data["file_size_bytes"] > 0

    # Verify evidence list endpoint
    list_evid_res = await async_client.get(
        "/v1/evidence", headers=headers
    )
    assert list_evid_res.status_code == 200
    assert len(list_evid_res.json()) >= 1

    # 8. Verify notification dispatched
    assert send_email_spy.call_count >= 1
