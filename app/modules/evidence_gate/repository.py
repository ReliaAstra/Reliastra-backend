from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evidence_gate.models import (
    EvidenceGateToken,
    LeadCaptureEvent,
    PublicEvidenceReport,
)


class PublicEvidenceReportRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        incident_id: uuid.UUID,
        vendor_name: str,
        report_id: uuid.UUID,
        is_public: bool = True,
        custom_title: str | None = None,
        custom_summary: str | None = None,
    ) -> PublicEvidenceReport:
        record = PublicEvidenceReport(
            incident_id=incident_id,
            vendor_name=vendor_name,
            report_id=report_id,
            is_public=is_public,
            custom_title=custom_title,
            custom_summary=custom_summary,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_by_id(
        session: AsyncSession, report_id: uuid.UUID
    ) -> PublicEvidenceReport | None:
        result = await session.execute(
            select(PublicEvidenceReport).where(PublicEvidenceReport.id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_incident(
        session: AsyncSession, incident_id: uuid.UUID
    ) -> PublicEvidenceReport | None:
        result = await session.execute(
            select(PublicEvidenceReport)
            .where(PublicEvidenceReport.incident_id == incident_id)
            .order_by(PublicEvidenceReport.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_public_for_vendor(
        session: AsyncSession,
        vendor_name: str,
    ) -> list[PublicEvidenceReport]:
        result = await session.execute(
            select(PublicEvidenceReport)
            .where(
                PublicEvidenceReport.vendor_name == vendor_name,
                PublicEvidenceReport.is_public.is_(True),
            )
            .order_by(PublicEvidenceReport.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_publicity(
        session: AsyncSession,
        report: PublicEvidenceReport,
        is_public: bool,
        custom_title: str | None = None,
        custom_summary: str | None = None,
    ) -> PublicEvidenceReport:
        report.is_public = is_public
        if custom_title is not None:
            report.custom_title = custom_title
        if custom_summary is not None:
            report.custom_summary = custom_summary
        session.add(report)
        await session.flush()
        return report

    @staticmethod
    async def increment_download_count(
        session: AsyncSession, report_id: uuid.UUID
    ) -> None:
        await session.execute(
            update(PublicEvidenceReport)
            .where(PublicEvidenceReport.id == report_id)
            .values(download_count=PublicEvidenceReport.download_count + 1)
        )
        await session.flush()

    @staticmethod
    async def increment_accounts_created(
        session: AsyncSession, report_id: uuid.UUID
    ) -> None:
        await session.execute(
            update(PublicEvidenceReport)
            .where(PublicEvidenceReport.id == report_id)
            .values(accounts_created=PublicEvidenceReport.accounts_created + 1)
        )
        await session.flush()


class EvidenceGateTokenRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        report_id: uuid.UUID,
        email: str,
        token_hash: str,
        ip_address: str | None = None,
        user_id: uuid.UUID | None = None,
        expires_at: datetime | None = None,
    ) -> EvidenceGateToken:
        record = EvidenceGateToken(
            report_id=report_id,
            email=email,
            token_hash=token_hash,
            ip_address=ip_address,
            user_id=user_id,
            expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(hours=1)),
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_by_token_hash(
        session: AsyncSession, token_hash: str
    ) -> EvidenceGateToken | None:
        result = await session.execute(
            select(EvidenceGateToken).where(
                EvidenceGateToken.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_downloaded(
        session: AsyncSession, token_id: uuid.UUID
    ) -> None:
        await session.execute(
            update(EvidenceGateToken)
            .where(EvidenceGateToken.id == token_id)
            .values(downloaded_at=datetime.now(timezone.utc))
        )
        await session.flush()


class LeadCaptureEventRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        source: str,
        email: str,
        vendor_name: str | None = None,
        incident_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        ref_code: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata_: dict[str, Any] | None = None,
    ) -> LeadCaptureEvent:
        record = LeadCaptureEvent(
            source=source,
            email=email,
            user_id=user_id,
            vendor_name=vendor_name,
            incident_id=incident_id,
            ref_code=ref_code,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_=metadata_,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def get_total_downloads(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.count(EvidenceGateToken.id)).where(
                EvidenceGateToken.downloaded_at.is_not(None)
            )
        )
        return result.scalar_one() or 0

    @staticmethod
    async def get_total_accounts_created(session: AsyncSession) -> int:
        result = await session.execute(
            select(func.sum(PublicEvidenceReport.accounts_created))
        )
        return result.scalar_one() or 0

    @staticmethod
    async def get_conversion_rate(session: AsyncSession) -> float:
        total_downloads = await LeadCaptureEventRepository.get_total_downloads(session)
        total_conversions = await session.execute(
            select(func.count(LeadCaptureEvent.id)).where(
                LeadCaptureEvent.source == "evidence_download",
                LeadCaptureEvent.converted_to_signup.is_(True),
            )
        )
        conversion_count = total_conversions.scalar_one() or 0
        if total_downloads == 0:
            return 0.0
        return round(conversion_count / total_downloads * 100, 2)

    @staticmethod
    async def get_top_vendors(session: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
        result = await session.execute(
            select(
                LeadCaptureEvent.vendor_name,
                func.count(LeadCaptureEvent.id).label("count"),
            )
            .where(LeadCaptureEvent.source == "evidence_download")
            .group_by(LeadCaptureEvent.vendor_name)
            .order_by(func.count(LeadCaptureEvent.id).desc())
            .limit(limit)
        )
        return [
            {"vendor_name": row.vendor_name, "count": row.count}
            for row in result.all()
        ]

    @staticmethod
    async def get_recent_conversions(
        session: AsyncSession, limit: int = 10
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            select(LeadCaptureEvent)
            .where(
                LeadCaptureEvent.source == "evidence_download",
                LeadCaptureEvent.converted_to_signup.is_(True),
            )
            .order_by(LeadCaptureEvent.converted_at.desc())
            .limit(limit)
        )
        events = result.scalars().all()
        return [
            {
                "email": e.email,
                "vendor_name": e.vendor_name,
                "converted_at": e.converted_at.isoformat() if e.converted_at else None,
            }
            for e in events
        ]

    @staticmethod
    async def mark_converted(
        session: AsyncSession, user_id: uuid.UUID, email: str
    ) -> None:
        await session.execute(
            update(LeadCaptureEvent)
            .where(
                LeadCaptureEvent.email == email,
                LeadCaptureEvent.user_id.is_(None),
            )
            .values(
                user_id=user_id,
                converted_to_signup=True,
                converted_at=datetime.now(timezone.utc),
            )
        )
        await session.flush()
