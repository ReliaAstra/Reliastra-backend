import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observations.models import Observation


class ObservationRepository:
    @staticmethod
    async def create(session: AsyncSession, dto: Any) -> Observation:
        observation = Observation(
            id=uuid.uuid4(),
            timestamp=dto.timestamp or datetime.now(timezone.utc),
            source_type=dto.source_type,
            source_id=dto.source_id,
            org_id=dto.org_id,
            region=dto.region,
            endpoint_url=dto.endpoint_url,
            latency_ms=dto.latency_ms,
            status_code=dto.status_code,
            response_time_ms=dto.response_time_ms,
            tls_version=dto.tls_version,
            tls_certificate_issuer=dto.tls_certificate_issuer,
            tls_certificate_expiry=dto.tls_certificate_expiry,
            error_type=dto.error_type,
            error_message=dto.error_message,
            observation_metadata=dto.metadata,
        )
        session.add(observation)
        await session.flush()
        return observation

    @staticmethod
    async def list_for_source(
        session: AsyncSession,
        source_id: uuid.UUID,
        source_type: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Observation]:
        query = select(Observation).where(Observation.source_id == source_id)
        if source_type:
            query = query.where(Observation.source_type == source_type)
        if since:
            query = query.where(Observation.timestamp >= since)
        if until:
            query = query.where(Observation.timestamp <= until)
        result = await session.execute(
            query.order_by(Observation.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
        since: datetime | None = None,
    ) -> list[Observation]:
        query = select(Observation).where(Observation.org_id == org_id)
        if since:
            query = query.where(Observation.timestamp >= since)
        result = await session.execute(
            query.order_by(Observation.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_endpoints(
        session: AsyncSession,
        endpoint_urls: list[str],
        source_type: str = "customer_check",
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[Observation]:
        if not endpoint_urls:
            return []
        query = select(Observation).where(
            Observation.endpoint_url.in_(endpoint_urls),
            Observation.source_type == source_type,
        )
        if since:
            query = query.where(Observation.timestamp >= since)
        result = await session.execute(
            query.order_by(Observation.timestamp.desc()).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_aggregated_stats(
        session: AsyncSession,
        source_id: uuid.UUID,
        window_hours: int = 24,
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        failure = case(
            (
                (Observation.status_code.is_(None))
                | (Observation.error_type.is_not(None)),
                1,
            ),
            else_=0,
        )
        query = select(
            func.count(Observation.id).label("total"),
            func.avg(Observation.latency_ms).label("avg_latency"),
            func.sum(failure).label("error_count"),
            func.min(Observation.source_type).label("source_type"),
            func.min(Observation.endpoint_url).label("endpoint_url"),
            func.percentile_cont(0.95)
            .within_group(Observation.latency_ms)
            .label("p95"),
        ).where(
            Observation.source_id == source_id,
            Observation.timestamp >= since,
        )
        row = (await session.execute(query)).one_or_none()
        if not row or not row.total:
            return {
                "total": 0,
                "uptime_pct": 100.0,
                "avg_latency": 0.0,
                "p95": None,
                "source_type": "unknown",
                "endpoint_url": "",
            }
        total = int(row.total)
        errors = int(row.error_count or 0)
        return {
            "total": total,
            "uptime_pct": round(((total - errors) / total) * 100, 2),
            "avg_latency": round(float(row.avg_latency or 0), 2),
            "p95": round(float(row.p95), 2) if row.p95 is not None else None,
            "source_type": row.source_type or "unknown",
            "endpoint_url": row.endpoint_url or "",
        }

    @staticmethod
    async def get_endpoint_stats(
        session: AsyncSession,
        endpoint_urls: list[str],
        window_hours: int,
        source_type: str = "customer_check",
    ) -> dict[str, Any]:
        if not endpoint_urls:
            return {
                "total": 0,
                "uptime_percentage": 100.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": None,
            }
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        failure = case(
            (
                (Observation.status_code.is_(None))
                | (Observation.error_type.is_not(None)),
                1,
            ),
            else_=0,
        )
        row = (
            await session.execute(
                select(
                    func.count(Observation.id).label("total"),
                    func.sum(failure).label("failures"),
                    func.avg(Observation.latency_ms).label("avg_latency"),
                    func.percentile_cont(0.95)
                    .within_group(Observation.latency_ms)
                    .label("p95"),
                ).where(
                    Observation.endpoint_url.in_(endpoint_urls),
                    Observation.source_type == source_type,
                    Observation.timestamp >= since,
                )
            )
        ).one()
        total = int(row.total or 0)
        failures = int(row.failures or 0)
        return {
            "total": total,
            "uptime_percentage": (
                round(((total - failures) / total) * 100, 2)
                if total
                else 100.0
            ),
            "avg_latency_ms": round(float(row.avg_latency or 0), 2),
            "p95_latency_ms": (
                round(float(row.p95), 2) if row.p95 is not None else None
            ),
        }

    @staticmethod
    async def get_sla_degradation(
        session: AsyncSession,
        org_id: uuid.UUID,
        period_days: int,
    ) -> dict[str, Any]:
        since = datetime.now(timezone.utc) - timedelta(days=period_days)
        failure = case(
            (
                (Observation.status_code.is_(None))
                | (Observation.error_type.is_not(None)),
                1,
            ),
            else_=0,
        )
        rows = (
            await session.execute(
                select(
                    Observation.source_id,
                    func.count(Observation.id).label("total"),
                    func.sum(failure).label("failures"),
                )
                .where(
                    Observation.org_id == org_id,
                    Observation.source_type == "customer_check",
                    Observation.timestamp >= since,
                )
                .group_by(Observation.source_id)
            )
        ).all()
        degradations = [
            (int(row.failures or 0) / int(row.total)) * 100
            for row in rows
            if row.total
        ]
        return {
            "total_degradation_pct": round(
                sum(degradations) / len(degradations), 2
            )
            if degradations
            else 0.0,
            "affected_services": sum(1 for value in degradations if value > 0),
        }

    @staticmethod
    async def delete_before(
        session: AsyncSession, cutoff: datetime
    ) -> int:
        result = await session.execute(
            delete(Observation).where(Observation.timestamp < cutoff)
        )
        return int(result.rowcount or 0)

    @staticmethod
    async def count_between(
        session: AsyncSession, start: datetime, end: datetime
    ) -> int:
        result = await session.execute(
            select(func.count(Observation.id)).where(
                Observation.timestamp >= start,
                Observation.timestamp < end,
            )
        )
        return int(result.scalar() or 0)
