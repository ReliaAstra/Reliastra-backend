import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.attribution.models import AttributionResult


class AttributionRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        incident_id: uuid.UUID,
        org_id: uuid.UUID,
        dependency_id: uuid.UUID,
        confidence_score: float,
        methodology_version: str,
        signals: dict[str, Any],
        evidence_chain: dict[str, Any],
        summary: str | None = None,
    ) -> AttributionResult:
        result = AttributionResult(
            incident_id=incident_id,
            org_id=org_id,
            dependency_id=dependency_id,
            confidence_score=confidence_score,
            methodology_version=methodology_version,
            signals=signals,
            evidence_chain=evidence_chain,
            summary=summary,
        )
        session.add(result)
        await session.flush()
        return result

    @staticmethod
    async def get_for_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> AttributionResult | None:
        stmt = (
            select(AttributionResult)
            .where(AttributionResult.incident_id == incident_id)
            .order_by(AttributionResult.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, attribution_id: uuid.UUID
    ) -> AttributionResult | None:
        result = await session.execute(
            select(AttributionResult).where(AttributionResult.id == attribution_id)
        )
        return result.scalar_one_or_none()
