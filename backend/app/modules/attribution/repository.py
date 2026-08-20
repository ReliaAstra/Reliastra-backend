import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attribution.models import AttributionResult


class AttributionRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession, result_id: uuid.UUID
    ) -> AttributionResult | None:
        result = await session.execute(
            select(AttributionResult).where(AttributionResult.id == result_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> AttributionResult | None:
        result = await session.execute(
            select(AttributionResult).where(
                AttributionResult.incident_id == incident_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession, result: AttributionResult
    ) -> AttributionResult:
        session.add(result)
        await session.flush()
        return result
