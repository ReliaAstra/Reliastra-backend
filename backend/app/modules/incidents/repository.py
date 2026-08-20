import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.incidents.models import Incident, IncidentCorrelation
from app.modules.incidents.constants import IncidentSeverity, IncidentStatus


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
            status=IncidentStatus.OPEN.value,
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
            Incident.status == IncidentStatus.OPEN.value,
        )
        result = await session.execute(query)
        # `.first()` instead of `.scalar_one_or_none()`: legacy duplicate open
        # incidents (pre-0014) would raise MultipleResultsFound and crash the
        # quorum path.  The partial unique index now prevents new duplicates.
        return result.scalars().first()

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
            Incident.status == IncidentStatus.OPEN.value,
        )
        if exclude_incident_id:
            query = query.where(Incident.id != exclude_incident_id)
        result = await session.execute(query)
        return list(result.scalars().all())

    # Allowed update fields for Incident — any key not in this set is silently
    # ignored so callers (even internal ones) cannot overwrite protected columns
    # like `org_id`, `dependency_id`, `created_at` via setattr.
    _UPDATABLE_FIELDS = {
        "status", "severity", "description", "root_cause",
        "resolved_at", "evidence_report_id",
    }

    @staticmethod
    async def update(
        session: AsyncSession, incident: Incident, **kwargs: Any
    ) -> Incident:
        for key, value in kwargs.items():
            if key in IncidentRepository._UPDATABLE_FIELDS and value is not None:
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

    @staticmethod
    async def list_with_correlations_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 20,
        cursor: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch incidents for an org with their correlations in a batched manner.

        Returns a list of dicts with 'incident' and 'correlations' keys
        to avoid N+1 queries in the dashboard timeline. Supports cursor
        pagination (FIX 17): *cursor* is the incident id of the last item of
        the previous page.
        """
        incidents_query = (
            select(Incident)
            .where(Incident.org_id == org_id)
            .order_by(Incident.started_at.desc(), Incident.id.desc())
            .limit(limit)
        )
        if cursor:
            cursor_incident = await session.get(Incident, cursor)
            if cursor_incident is not None:
                incidents_query = incidents_query.where(
                    (Incident.started_at < cursor_incident.started_at)
                    | (
                        (Incident.started_at == cursor_incident.started_at)
                        & (Incident.id < cursor_incident.id)
                    )
                )
        inc_result = await session.execute(incidents_query)
        incidents = list(inc_result.scalars().all())

        if not incidents:
            return []

        incident_ids = [inc.id for inc in incidents]
        corr_query = (
            select(IncidentCorrelation)
            .where(IncidentCorrelation.incident_id.in_(incident_ids))
            .order_by(IncidentCorrelation.correlation_confidence.desc())
        )
        corr_result = await session.execute(corr_query)
        all_correlations = list(corr_result.scalars().all())

        corr_by_incident: dict[uuid.UUID, list[IncidentCorrelation]] = {}
        for c in all_correlations:
            corr_by_incident.setdefault(c.incident_id, []).append(c)

        return [
            {
                "incident": inc,
                "correlations": corr_by_incident.get(inc.id, []),
            }
            for inc in incidents
        ]
