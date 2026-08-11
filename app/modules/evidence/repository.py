"""Evidence report metadata persistence."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceReport


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, values: dict[str, object]) -> EvidenceReport:
        report = EvidenceReport(**values)
        self.session.add(report)
        await self.session.flush()
        return report

    async def get(self, org_id: UUID, report_id: UUID) -> EvidenceReport | None:
        return cast(
            EvidenceReport | None,
            await self.session.scalar(
                select(EvidenceReport).where(
                    EvidenceReport.id == report_id, EvidenceReport.org_id == org_id
                )
            ),
        )

    async def latest_for_incident(self, org_id: UUID, incident_id: UUID) -> EvidenceReport | None:
        return cast(
            EvidenceReport | None,
            await self.session.scalar(
                select(EvidenceReport)
                .where(
                    EvidenceReport.org_id == org_id,
                    EvidenceReport.incident_id == incident_id,
                )
                .order_by(EvidenceReport.generated_at.desc())
            ),
        )

    async def list(self, org_id: UUID) -> list[EvidenceReport]:
        return list(
            (
                await self.session.scalars(
                    select(EvidenceReport)
                    .where(EvidenceReport.org_id == org_id)
                    .order_by(EvidenceReport.generated_at.desc())
                )
            ).all()
        )
