from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dependencies.models import Dependency
from app.modules.incidents.models import Incident
from app.modules.vendors.models import VendorEndpoint, VendorTracking


class VendorRepository:
    @staticmethod
    async def list_public(session: AsyncSession) -> list[VendorTracking]:
        result = await session.execute(
            select(VendorTracking)
            .where(VendorTracking.is_public.is_(True))
            .order_by(VendorTracking.display_name.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_name(
        session: AsyncSession, vendor_name: str
    ) -> VendorTracking | None:
        result = await session.execute(
            select(VendorTracking).where(
                VendorTracking.vendor_name == vendor_name.lower()
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        vendor_name: str,
        display_name: str,
        endpoint_url: str,
        category: str,
        is_public: bool = True,
    ) -> VendorTracking:
        vendor = VendorTracking(
            vendor_name=vendor_name.lower(),
            display_name=display_name,
            endpoint_url=endpoint_url,
            category=category,
            is_public=is_public,
        )
        session.add(vendor)
        await session.flush()
        await VendorRepository.create_vendor_endpoint(
            session, vendor.id, endpoint_url
        )
        return vendor

    @staticmethod
    async def update_check_time(
        session: AsyncSession, vendor: VendorTracking
    ) -> None:
        vendor.last_check_at = datetime.now(timezone.utc)
        session.add(vendor)
        await session.flush()

    @staticmethod
    async def create_vendor_endpoint(
        session: AsyncSession,
        vendor_id,
        endpoint_url: str,
    ) -> VendorEndpoint:
        endpoint = VendorEndpoint(
            vendor_id=vendor_id,
            endpoint_url=endpoint_url,
            check_interval_seconds=300,
            regions=["us-east", "eu-west"],
            is_active=True,
            health_status="unknown",
        )
        session.add(endpoint)
        await session.flush()
        return endpoint

    @staticmethod
    async def list_vendor_endpoints(
        session: AsyncSession, vendor_name: str
    ) -> list[VendorEndpoint]:
        result = await session.execute(
            select(VendorEndpoint)
            .join(
                VendorTracking,
                VendorEndpoint.vendor_id == VendorTracking.id,
            )
            .where(VendorTracking.vendor_name == vendor_name.lower())
            .order_by(VendorEndpoint.endpoint_url.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_incidents_for_endpoints(
        session: AsyncSession,
        endpoint_urls: list[str],
        limit: int = 50,
    ) -> list[tuple[Incident, Dependency]]:
        if not endpoint_urls:
            return []
        result = await session.execute(
            select(Incident, Dependency)
            .join(Dependency, Incident.dependency_id == Dependency.id)
            .where(Dependency.endpoint_url.in_(endpoint_urls))
            .order_by(Incident.started_at.desc())
            .limit(limit)
        )
        return list(result.all())
