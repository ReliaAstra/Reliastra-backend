import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence.models import EvidenceSnapshot


class VerificationRepository:
    @staticmethod
    async def get_by_verification_id(
        session: AsyncSession, verification_id: str
    ) -> EvidenceSnapshot | None:
        stmt = select(EvidenceSnapshot).where(
            EvidenceSnapshot.verification_id == verification_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_id(
        session: AsyncSession, snapshot_id: uuid.UUID
    ) -> EvidenceSnapshot | None:
        result = await session.execute(
            select(EvidenceSnapshot).where(EvidenceSnapshot.id == snapshot_id)
        )
        return result.scalar_one_or_none()
