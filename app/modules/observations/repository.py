import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observations.models import Observation


class ObservationRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source_type: str,
        endpoint_url: str,
        region: str,
        latency_ms: float,
        source_id: uuid.UUID | None = None,
        org_id: uuid.UUID | None = None,
        timestamp: datetime | None = None,
        status_code: int | None = None,
        response_time_ms: float | None = None,
        tls_version: str | None = None,
        tls_certificate_issuer: str | None = None,
        tls_certificate_expiry: datetime | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> Observation:
        obs = Observation(
            source_type=source_type,
            source_id=source_id,
            org_id=org_id,
            timestamp=timestamp or datetime.now(timezone.utc),
            region=region,
            endpoint_url=endpoint_url,
            latency_ms=latency_ms,
            status_code=status_code,
            response_time_ms=response_time_ms,
            tls_version=tls_version,
            tls_certificate_issuer=tls_certificate_issuer,
            tls_certificate_expiry=tls_certificate_expiry,
            error_type=error_type,
            error_message=error_message,
            extra_data=extra_data,
        )
        session.add(obs)
        await session.flush()
        return obs

    @staticmethod
    async def get_by_id(session: AsyncSession, obs_id: uuid.UUID) -> Observation | None:
        result = await session.execute(select(Observation).where(Observation.id == obs_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_dependency(
        session: AsyncSession,
        dependency_id: uuid.UUID,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[Observation]:
        query = select(Observation).where(Observation.source_id == dependency_id)
        if since:
            query = query.where(Observation.timestamp >= since)
        query = query.order_by(Observation.timestamp.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
    ) -> list[Observation]:
        query = (
            select(Observation)
            .where(Observation.org_id == org_id)
            .order_by(Observation.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())
