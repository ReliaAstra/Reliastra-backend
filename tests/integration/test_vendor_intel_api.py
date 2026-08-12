import pytest


@pytest.mark.asyncio
async def test_vendor_metrics_and_incidents(async_client):
    # These are public endpoints (no auth) but need a vendor seeded. The legacy
    # vendor_trackings table is seeded via migration, but the new `vendors`
    # table is separate. Seed one directly so the metrics/incidents endpoints
    # have data to return.

    # Seed via the vendor intel repository against the test DB.
    from app.modules.vendors.vendor_models import Vendor
    from app.db.session import get_session_maker

    session_maker = get_session_maker()
    async with session_maker() as session:
        existing = await session.get(Vendor, "00000000-0000-0000-0000-000000000000")
        # create a fresh vendor if not present
        from uuid import uuid4
        from app.modules.vendors.vendor_models import VendorMetricsDaily
        from datetime import datetime, timezone

        vendor = Vendor(
            id=uuid4(),
            vendor_name="stripe",
            slug="stripe",
            display_name="Stripe",
            endpoint_url="https://status.stripe.com",
            category="payments",
            is_public=True,
        )
        session.add(vendor)
        await session.flush()
        VendorMetricsDaily(
            vendor_id=vendor.id,
            date=datetime.now(timezone.utc),
            uptime_percentage=99.99,
            avg_latency_ms=120.0,
            total_checks=100,
            total_up=99,
            total_down=1,
        )
        await session.commit()

    # GET /v1/public/vendors/{slug}/metrics
    metrics_res = await async_client.get("/v1/public/vendors/stripe/metrics?days=7")
    assert metrics_res.status_code == 200, metrics_res.text
    assert metrics_res.json()["vendor_slug"] == "stripe"

    # GET /v1/public/vendors/{slug}/incidents
    inc_res = await async_client.get("/v1/public/vendors/stripe/incidents")
    assert inc_res.status_code == 200, inc_res.text
    assert isinstance(inc_res.json(), list)
