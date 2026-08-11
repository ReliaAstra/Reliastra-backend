import pytest


@pytest.mark.asyncio
async def test_public_vendors_endpoints(async_client, db_session):
    # Ensure seed vendors exist
    from app.modules.vendors.service import vendor_service

    await vendor_service.seed_vendors(db_session)
    await db_session.commit()

    # GET /v1/public/vendors
    list_res = await async_client.get("/v1/public/vendors")
    assert list_res.status_code == 200, list_res.text
    vendors = list_res.json()
    assert len(vendors) >= 5

    # GET /v1/public/vendors/{vendor_name}
    get_res = await async_client.get("/v1/public/vendors/stripe")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["vendor_name"] == "stripe"
    assert "recent_status" in detail

    # GET /v1/public/vendors/{vendor_name}/history
    hist_res = await async_client.get("/v1/public/vendors/stripe/history")
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert "uptime_percentage_24h" in history
