import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.modules.vendors.service import VendorService
from app.modules.vendors.constants import SEED_VENDORS


@pytest.mark.asyncio
async def test_seed_vendors():
    repo = MagicMock()
    repo.get_by_name = AsyncMock(return_value=None)
    repo.create = AsyncMock()

    service = VendorService(repository=repo)
    session = AsyncMock()
    count = await service.seed_vendors(session)

    assert count == len(SEED_VENDORS)
    assert repo.create.call_count == len(SEED_VENDORS)


@pytest.mark.asyncio
async def test_get_vendor_detail():
    repo = MagicMock()
    now = datetime.now(timezone.utc)
    fake_vendor = MagicMock()
    fake_vendor.id = uuid.uuid4()
    fake_vendor.vendor_name = "stripe"
    fake_vendor.display_name = "Stripe"
    fake_vendor.endpoint_url = "https://status.stripe.com"
    fake_vendor.category = "payments"
    fake_vendor.is_public = True
    fake_vendor.last_check_at = None
    fake_vendor.created_at = now
    fake_vendor.updated_at = now

    repo.get_by_name = AsyncMock(return_value=fake_vendor)

    service = VendorService(repository=repo)
    session = AsyncMock()
    res = await service.get_vendor_detail(session, "stripe")

    assert res.vendor_name == "stripe"
    assert res.recent_status == "operational"
