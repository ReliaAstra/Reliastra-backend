import pytest


@pytest.mark.asyncio
async def test_public_vendors_endpoints(async_client, db_session):
    # Ensure seed vendors exist
    from app.modules.vendors.service import vendor_service

    await vendor_service.seed_vendors(db_session)
    await db_session.commit()

    # GET /v1/vendors (FIX 17: cursor-paginated envelope)
    list_res = await async_client.get("/v1/vendors")
    assert list_res.status_code == 200, list_res.text
    envelope = list_res.json()
    assert set(envelope.keys()) >= {"items", "next_cursor", "has_more"}
    vendors = envelope["items"]
    assert len(vendors) >= 5

    # GET /v1/vendors/{vendor_name}
    get_res = await async_client.get("/v1/vendors/stripe")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["vendor_name"] == "stripe"
    assert "recent_status" in detail

    # GET /v1/vendors/{vendor_name}/history
    hist_res = await async_client.get("/v1/vendors/stripe/history")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert "uptime_percentage_24h" in history
