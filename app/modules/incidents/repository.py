"""Incident and correlation persistence."""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.incidents.constants import CorrelationMethod, IncidentSeverity, IncidentStatus
from app.modules.incidents.models import Incident, IncidentCorrelation


class IncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, org_id: UUID, incident_id: UUID) -> Incident | None:
        return cast(
            Incident | None,
            await self.session.scalar(
                select(Incident).where(Incident.id == incident_id, Incident.org_id == org_id)
            ),
        )

    async def get_any_org(self, incident_id: UUID) -> Incident | None:
        return await self.session.get(Incident, incident_id)

    async def open_for_dependency(self, dependency_id: UUID) -> Incident | None:
        return cast(
            Incident | None,
            await self.session.scalar(
                select(Incident)
                .where(
                    Incident.dependency_id == dependency_id, Incident.status == IncidentStatus.OPEN
                )
                .order_by(Incident.started_at.desc())
            ),
        )

    async def create(self, org_id: UUID, dependency_id: UUID) -> Incident:
        model = Incident(
            org_id=org_id,
            dependency_id=dependency_id,
            severity=IncidentSeverity.MAJOR,
            status=IncidentStatus.OPEN,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def list(
        self,
        org_id: UUID,
        limit: int,
        cursor: UUID | None,
        status: IncidentStatus | None,
        severity: IncidentSeverity | None,
    ) -> builtins.list[Incident]:
        statement = select(Incident).where(Incident.org_id == org_id)
        if status:
            statement = statement.where(Incident.status == status)
        if severity:
            statement = statement.where(Incident.severity == severity)
        if cursor:
            statement = statement.where(Incident.id < cursor)
        return list(
            (
                await self.session.scalars(
                    statement.order_by(Incident.started_at.desc()).limit(limit + 1)
                )
            ).all()
        )

    async def update(self, model: Incident, values: dict[str, object]) -> Incident:
        for field, value in values.items():
            setattr(model, field, value)
        await self.session.flush()
        return model

    async def candidates(
        self, org_id: UUID, dependency_id: UUID, start: datetime, end: datetime
    ) -> builtins.list[Incident]:
        return list(
            (
                await self.session.scalars(
                    select(Incident).where(
                        Incident.org_id == org_id,
                        Incident.dependency_id != dependency_id,
                        Incident.started_at.between(start, end),
                    )
                )
            ).all()
        )

    async def correlations(self, incident_id: UUID) -> builtins.list[IncidentCorrelation]:
        return list(
            (
                await self.session.scalars(
                    select(IncidentCorrelation)
                    .where(IncidentCorrelation.incident_id == incident_id)
                    .order_by(IncidentCorrelation.created_at)
                )
            ).all()
        )

    async def add_correlation(
        self,
        incident_id: UUID,
        dependency_id: UUID,
        confidence: float,
        window: int,
        method: CorrelationMethod,
    ) -> IncidentCorrelation:
        existing = await self.session.scalar(
            select(IncidentCorrelation).where(
                IncidentCorrelation.incident_id == incident_id,
                IncidentCorrelation.correlated_dependency_id == dependency_id,
            )
        )
        if existing:
            return existing
        model = IncidentCorrelation(
            incident_id=incident_id,
            correlated_dependency_id=dependency_id,
            correlation_confidence=confidence,
            time_window_seconds=window,
            correlation_method=method,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def attach_evidence(self, incident_id: UUID, report_id: UUID) -> None:
        incident = await self.session.get(Incident, incident_id)
        if incident is None:
            raise ValueError("Incident not found")
        incident.evidence_report_id = report_id
        await self.session.flush()

    async def open_count(self, org_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(Incident.org_id == org_id, Incident.status == IncidentStatus.OPEN)
            )
            or 0
        )
