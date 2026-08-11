"""Public vendor catalog queries."""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vendors.models import VendorTracking


class VendorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_public(self) -> list[VendorTracking]:
        return list(
            (
                await self.session.scalars(
                    select(VendorTracking)
                    .where(VendorTracking.is_public.is_(True))
                    .order_by(VendorTracking.display_name)
                )
            ).all()
        )

    async def get_public(self, vendor_name: str) -> VendorTracking | None:
        return cast(
            VendorTracking | None,
            await self.session.scalar(
                select(VendorTracking).where(
                    VendorTracking.vendor_name == vendor_name.lower(),
                    VendorTracking.is_public.is_(True),
                )
            ),
        )
