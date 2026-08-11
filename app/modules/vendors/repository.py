from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.vendors.models import VendorTracking


class VendorRepository:
    @staticmethod
    async def list_public(session: AsyncSession) -> list[VendorTracking]:
        query = (
            select(VendorTracking)
            .where(VendorTracking.is_public == True)  # noqa: E712
            .order_by(VendorTracking.display_name.asc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_name(
        session: AsyncSession, vendor_name: str
    ) -> VendorTracking | None:
        query = select(VendorTracking).where(
            VendorTracking.vendor_name == vendor_name.lower()
        )
        result = await session.execute(query)
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
        return vendor

    @staticmethod
    async def update_check_time(
        session: AsyncSession, vendor: VendorTracking
    ) -> None:
        vendor.last_check_at = datetime.now(timezone.utc)
        session.add(vendor)
        await session.flush()
