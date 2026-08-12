import base64
import hashlib
import secrets
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

    # --- Immutable snapshot helpers (Phase 7) --------------------------------

    @staticmethod
    async def create_snapshot(
        session: AsyncSession,
        *,
        incident_id: uuid.UUID,
        org_id: uuid.UUID,
        dependency_id: uuid.UUID,
        time_window_start: datetime,
        time_window_end: datetime,
        observation_ids: list[uuid.UUID],
        attribution_result: dict[str, Any],
        methodology_version: str,
        data_hash: str,
        report_file_path: str,
        report_checksum: str,
        json_evidence_path: str,
    ) -> EvidenceSnapshot:
        snapshot = EvidenceSnapshot(
            incident_id=incident_id,
            org_id=org_id,
            dependency_id=dependency_id,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            observation_ids=observation_ids,
            attribution_result=attribution_result,
            methodology_version=methodology_version,
            data_hash=data_hash,
            verification_id=generate_verification_id(),
            report_file_path=report_file_path,
            report_checksum=report_checksum,
            json_evidence_path=json_evidence_path,
        )
        session.add(snapshot)
        await session.flush()
        return snapshot

    @staticmethod
    async def get_snapshot_by_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> EvidenceSnapshot | None:
        stmt = (
            select(EvidenceSnapshot)
            .where(EvidenceSnapshot.incident_id == incident_id)
            .order_by(EvidenceSnapshot.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()


def generate_verification_id() -> str:
    """Return a short URL-safe public identifier (<= 32 chars) for verification URLs."""
    raw = secrets.token_bytes(18)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")[:32]


def compute_data_hash(evidence_json: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON evidence for cryptographic integrity."""
    import json

    canonical = json.dumps(evidence_json, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(canonical).hexdigest()
