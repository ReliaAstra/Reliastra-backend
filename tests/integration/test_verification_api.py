import http.server
import threading
import uuid

import pytest


class Handler500(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(500)
        self.end_headers()
        self.wfile.write(b"500 - Simulated Vendor Outage")

    def log_message(self, format: str, *args) -> None:
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
async def test_evidence_snapshot_and_verification_flow(
    async_client, db_session, test_http_server
):
    headers = {}
    org_id = None

    reg_res = await async_client.post(
        "/v1/auth/register",
        json={
            "email": "verify-owner@reliastra.com",
            "password": "SuperSecret123!",
            "full_name": "Verify Owner",
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    token_data = reg_res.json()
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    orgs = await async_client.get("/v1/orgs", headers=headers)
    org_id = orgs.json()[0]["id"]

    dep_res = await async_client.post(
        f"/v1/orgs/{org_id}/dependencies",
        headers=headers,
        json={
            "name": "Vendor API",
            "endpoint_url": f"{test_http_server}/status",
            "method": "GET",
            "check_interval_seconds": 300,
            "expected_status_codes": [200],
        },
    )
    assert dep_res.status_code == 201, dep_res.text
    dep_id = dep_res.json()["id"]

    # Confirm a quorum failure -> incident created.
    from app.modules.checks.service import check_service

    for region in ("us-east", "eu-west"):
        await check_service.execute_check(db_session, uuid.UUID(dep_id), region)
    await db_session.commit()

    incs = await async_client.get(
        f"/v1/orgs/{org_id}/incidents", headers=headers
    )
    assert incs.status_code == 200
    incidents = [i for i in incs.json() if i["dependency_id"] == dep_id]
    assert incidents, "expected an incident to be created"
    inc_id = incidents[0]["id"]

    # Resolve -> auto-generates evidence + immutable snapshot.
    resolve = await async_client.patch(
        f"/v1/orgs/{org_id}/incidents/{inc_id}",
        headers=headers,
        json={"status": "resolved"},
    )
    assert resolve.status_code == 200, resolve.text

    evid = await async_client.get(
        f"/v1/orgs/{org_id}/incidents/{inc_id}/evidence", headers=headers
    )
    assert evid.status_code == 200, evid.text
    assert len(evid.json()["checksum"]) == 64

    # Pull the verification_id from the snapshot row.
    from app.modules.evidence.models import EvidenceSnapshot
    from app.db.session import get_session_maker

    session_maker = get_session_maker()
    async with session_maker() as session:
        result = await session.execute(
            EvidenceSnapshot.__table__.select().where(
                EvidenceSnapshot.__table__.c.incident_id == uuid.UUID(inc_id)
            )
        )
        row = result.mappings().first()
        assert row, "expected an evidence snapshot"
        vid = row["verification_id"]

    # Public verification endpoints.
    v_res = await async_client.get(f"/v1/verify/{vid}")
    assert v_res.status_code == 200, v_res.text
    assert v_res.json()["verification_id"] == vid
    assert v_res.json()["hashes_match"] is True

    h_res = await async_client.get(f"/v1/verify/{vid}/hash")
    assert h_res.status_code == 200
    assert len(h_res.json()["data_hash"]) == 64

    ev_res = await async_client.get(f"/v1/verify/{vid}/evidence")
    assert ev_res.status_code == 200
    assert ev_res.json()["data_hash"]
