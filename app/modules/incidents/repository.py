import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.incidents.models import Incident, IncidentCorrelation


class IncidentRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        dependency_id: uuid.UUID,
        severity: str = "major",
        description: str | None = None,
    ) -> Incident:
        inc = Incident(
            org_id=org_id,
            dependency_id=dependency_id,
            started_at=datetime.now(timezone.utc),
            severity=severity,
            status="open",
            root_cause="unknown",
            description=description,
        )
        session.add(inc)
        await session.flush()
        return inc

    @staticmethod
    async def get_by_id(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> Incident | None:
        query = select(Incident).where(Incident.id == incident_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_open_for_dependency(
        session: AsyncSession, dependency_id: uuid.UUID
    ) -> Incident | None:
        query = select(Incident).where(
            Incident.dependency_id == dependency_id,
            Incident.status == "open",
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
        status_filter: str | None = None,
        severity_filter: str | None = None,
    ) -> list[Incident]:
        query = (
            select(Incident)
            .where(Incident.org_id == org_id)
            .order_by(Incident.started_at.desc())
            .limit(limit)
        )
        if status_filter:
            query = query.where(Incident.status == status_filter)
        if severity_filter:
            query = query.where(Incident.severity == severity_filter)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_open_in_window(
        session: AsyncSession,
        org_id: uuid.UUID,
        center_time: datetime,
        window_seconds: int = 300,
        exclude_incident_id: uuid.UUID | None = None,
    ) -> list[Incident]:
        start = center_time - timedelta(seconds=window_seconds)
        end = center_time + timedelta(seconds=window_seconds)
        query = select(Incident).where(
            Incident.org_id == org_id,
            Incident.started_at >= start,
            Incident.started_at <= end,
            Incident.status == "open",
        )
        if exclude_incident_id:
            query = query.where(Incident.id != exclude_incident_id)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update(
        session: AsyncSession, incident: Incident, **kwargs: Any
    ) -> Incident:
        for key, value in kwargs.items():
            if value is not None and hasattr(incident, key):
                setattr(incident, key, value)
        session.add(incident)
        await session.flush()
        return incident

    @staticmethod
    async def create_correlation(
        session: AsyncSession,
        incident_id: uuid.UUID,
        correlated_dependency_id: uuid.UUID,
        confidence: float = 0.85,
        time_window_seconds: int = 300,
        method: str = "temporal",
    ) -> IncidentCorrelation:
        corr = IncidentCorrelation(
            incident_id=incident_id,
            correlated_dependency_id=correlated_dependency_id,
            correlation_confidence=confidence,
            time_window_seconds=time_window_seconds,
            correlation_method=method,
        )
        session.add(corr)
        await session.flush()
        return corr

    @staticmethod
    async def get_correlations(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> list[IncidentCorrelation]:
        query = (
            select(IncidentCorrelation)
            .where(IncidentCorrelation.incident_id == incident_id)
            .order_by(IncidentCorrelation.correlation_confidence.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())
