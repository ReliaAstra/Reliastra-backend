import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vendors.vendor_models import (
    Vendor,
    VendorEndpoint,
    VendorIncident,
    VendorMetricsDaily,
)


class VendorIntelRepository:
    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Vendor | None:
        stmt = select(Vendor).where(Vendor.slug == slug)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_metrics_daily(
        session: AsyncSession,
        vendor_id: uuid.UUID,
        days: int = 90,
    ) -> list[VendorMetricsDaily]:
        since = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(days=days)
        stmt = (
            select(VendorMetricsDaily)
            .where(
                VendorMetricsDaily.vendor_id == vendor_id,
                VendorMetricsDaily.date >= since,
            )
            .order_by(VendorMetricsDaily.date.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_incidents(
        session: AsyncSession,
        vendor_id: uuid.UUID,
        limit: int = 50,
    ) -> list[VendorIncident]:
        stmt = (
            select(VendorIncident)
            .where(VendorIncident.vendor_id == vendor_id)
            .order_by(VendorIncident.started_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
