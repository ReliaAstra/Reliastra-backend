from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException
from app.modules.vendors.intel_repository import VendorIntelRepository
from app.modules.vendors.intel_schemas import (
    VendorIncidentResponse,
    VendorMetricsResponse,
)


class VendorIntelService:
    def __init__(
        self, repository: VendorIntelRepository = VendorIntelRepository()
    ) -> None:
        self.repository = repository

    async def get_metrics(
        self, session: AsyncSession, slug: str, days: int = 90
    ) -> VendorMetricsResponse:
        vendor = await self.repository.get_by_slug(session, slug)
        if not vendor:
            raise ResourceNotFoundException(f"Vendor '{slug}' not found")
        metrics = await self.repository.get_metrics_daily(session, vendor.id, days=days)
        return VendorMetricsResponse(
            vendor_id=vendor.id,
            vendor_slug=vendor.slug,
            days=days,
            metrics=[
                m for m in [self._to_point(m) for m in metrics]
            ],
        )

    async def list_incidents(
        self, session: AsyncSession, slug: str, limit: int = 50
    ) -> list[VendorIncidentResponse]:
        vendor = await self.repository.get_by_slug(session, slug)
        if not vendor:
            raise ResourceNotFoundException(f"Vendor '{slug}' not found")
        incidents = await self.repository.list_incidents(session, vendor.id, limit=limit)
        return [VendorIncidentResponse.model_validate(i) for i in incidents]

    @staticmethod
    def _to_point(m):
        from app.modules.vendors.intel_schemas import VendorMetricsPoint

        return VendorMetricsPoint(
            date=m.date,
            uptime_percentage=m.uptime_percentage,
            avg_latency_ms=m.avg_latency_ms,
            total_checks=m.total_checks,
            total_up=m.total_up,
            total_down=m.total_down,
        )


vendor_intel_service = VendorIntelService()
