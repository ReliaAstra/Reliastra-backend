from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException
from app.modules.vendors.constants import SEED_VENDORS
from app.modules.vendors.models import VendorTracking
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import (
    VendorDetailResponse,
    VendorHistoryResponse,
    VendorResponse,
)


class VendorService:
    def __init__(
        self, repository: VendorRepository = VendorRepository()
    ) -> None:
        self.repository = repository

    async def seed_vendors(self, session: AsyncSession) -> int:
        seeded_count = 0
        for item in SEED_VENDORS:
            existing = await self.repository.get_by_name(
                session, item["vendor_name"]
            )
            if not existing:
                await self.repository.create(
                    session=session,
                    vendor_name=item["vendor_name"],
                    display_name=item["display_name"],
                    endpoint_url=item["endpoint_url"],
                    category=item["category"],
                )
                seeded_count += 1
        return seeded_count

    async def list_public_vendors(
        self, session: AsyncSession
    ) -> list[VendorResponse]:
        vendors = await self.repository.list_public(session)
        return [VendorResponse.model_validate(v) for v in vendors]

    async def get_vendor_detail(
        self, session: AsyncSession, vendor_name: str
    ) -> VendorDetailResponse:
        vendor = await self.repository.get_by_name(session, vendor_name)
        if not vendor:
            raise ResourceNotFoundException(
                f"Vendor '{vendor_name}' not found"
            )
        data = VendorResponse.model_validate(vendor).model_dump()
        data["recent_status"] = "operational"
        return VendorDetailResponse.model_validate(data)

    async def get_vendor_history(
        self, session: AsyncSession, vendor_name: str
    ) -> VendorHistoryResponse:
        vendor = await self.repository.get_by_name(session, vendor_name)
        if not vendor:
            raise ResourceNotFoundException(
                f"Vendor '{vendor_name}' not found"
            )
        return VendorHistoryResponse(
            vendor_name=vendor.vendor_name,
            uptime_percentage_24h=99.99,
            avg_latency_ms_24h=45.0,
            recent_checks_count=288,
        )


vendor_service = VendorService()
