import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException
from app.modules.checks.repository import CheckRepository
from app.modules.vendors.constants import SEED_VENDORS
from app.modules.vendors.models import VendorTracking
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import (
    VendorDetailResponse,
    VendorHistoryResponse,
    VendorResponse,
)

logger = logging.getLogger(__name__)


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

        # Derive recent status from actual check results
        recent = await CheckRepository.get_vendor_recent_status(
            session, vendor.endpoint_url, limit=5
        )
        if recent:
            all_up = all(r.is_up for r in recent)
            data["recent_status"] = "operational" if all_up else "degraded"
        else:
            data["recent_status"] = "unknown"

        return VendorDetailResponse.model_validate(data)

    async def get_vendor_history(
        self, session: AsyncSession, vendor_name: str
    ) -> VendorHistoryResponse:
        vendor = await self.repository.get_by_name(session, vendor_name)
        if not vendor:
            raise ResourceNotFoundException(
                f"Vendor '{vendor_name}' not found"
            )

        # Derive stats from actual check results across all deps pointing to this vendor
        stats = await CheckRepository.get_vendor_aggregated_stats(
            session, vendor.endpoint_url, window_hours=24
        )

        return VendorHistoryResponse(
            vendor_name=vendor.vendor_name,
            uptime_percentage_24h=stats["uptime_percentage"],
            avg_latency_ms_24h=stats["avg_latency_ms"],
            recent_checks_count=stats["total_checks"],
        )


vendor_service = VendorService()
