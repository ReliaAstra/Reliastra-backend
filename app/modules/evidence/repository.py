import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.evidence.models import EvidenceReport


class EvidenceRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        incident_id: uuid.UUID,
        file_path: str,
        file_size_bytes: int,
        checksum: str,
        expires_at: datetime | None = None,
    ) -> EvidenceReport:
        report = EvidenceReport(
            org_id=org_id,
            incident_id=incident_id,
            file_path=file_path,
            file_size_bytes=file_size_bytes,
            checksum=checksum,
            generated_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )
        session.add(report)
        await session.flush()
        return report

    @staticmethod
    async def get_by_id(
        session: AsyncSession, report_id: uuid.UUID
    ) -> EvidenceReport | None:
        query = select(EvidenceReport).where(EvidenceReport.id == report_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> EvidenceReport | None:
        query = select(EvidenceReport).where(
            EvidenceReport.incident_id == incident_id
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
    ) -> list[EvidenceReport]:
        query = (
            select(EvidenceReport)
            .where(EvidenceReport.org_id == org_id)
            .order_by(EvidenceReport.generated_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update(
        session: AsyncSession, report: EvidenceReport, **kwargs: Any
    ) -> EvidenceReport:
        for key, value in kwargs.items():
            if value is not None and hasattr(report, key):
                setattr(report, key, value)
        session.add(report)
        await session.flush()
        return report
