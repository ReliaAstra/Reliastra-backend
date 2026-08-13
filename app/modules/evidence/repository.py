import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceReport, EvidenceSnapshot


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
        result = await session.execute(
            select(EvidenceReport).where(EvidenceReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> EvidenceReport | None:
        result = await session.execute(
            select(EvidenceReport)
            .where(EvidenceReport.incident_id == incident_id)
            .order_by(EvidenceReport.generated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
    ) -> list[EvidenceReport]:
        result = await session.execute(
            select(EvidenceReport)
            .where(EvidenceReport.org_id == org_id)
            .order_by(EvidenceReport.generated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class EvidenceSnapshotRepository:
    @staticmethod
    async def create(
        session: AsyncSession, **values: Any
    ) -> EvidenceSnapshot:
        snapshot = EvidenceSnapshot(**values)
        session.add(snapshot)
        await session.flush()
        return snapshot

    @staticmethod
    async def get_by_verification_id(
        session: AsyncSession, verification_id: str
    ) -> EvidenceSnapshot | None:
        result = await session.execute(
            select(EvidenceSnapshot).where(
                EvidenceSnapshot.verification_id == verification_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_latest_for_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> EvidenceSnapshot | None:
        result = await session.execute(
            select(EvidenceSnapshot)
            .where(EvidenceSnapshot.incident_id == incident_id)
            .order_by(EvidenceSnapshot.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
