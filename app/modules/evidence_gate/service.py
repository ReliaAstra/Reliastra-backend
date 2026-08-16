from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ConflictException, ResourceNotFoundException, ValidationException
from app.core.security import get_password_hash
from app.infrastructure.storage import storage_client
from app.modules.evidence.models import EvidenceReport
from app.modules.evidence.repository import EvidenceRepository
from app.modules.evidence_gate.models import PublicEvidenceReport
from app.modules.evidence_gate.repository import (
    EvidenceGateTokenRepository,
    LeadCaptureEventRepository,
    PublicEvidenceReportRepository,
)
from app.modules.evidence_gate.schemas import (
    EvidenceGateRequest,
    EvidenceGateResponse,
    EvidenceGateStats,
    PublicIncidentResponse,
    PublicizeEvidenceRequest,
    PublicizeResponse,
)
from app.modules.incidents.models import Incident
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)


class EvidenceGateService:
    def __init__(
        self,
        public_report_repo: PublicEvidenceReportRepository = PublicEvidenceReportRepository(),
        token_repo: EvidenceGateTokenRepository = EvidenceGateTokenRepository(),
        lead_repo: LeadCaptureEventRepository = LeadCaptureEventRepository(),
        user_repo: UserRepository = UserRepository(),
        org_repo: OrganizationRepository = OrganizationRepository(),
        evidence_repo: EvidenceRepository = EvidenceRepository(),
    ) -> None:
        self.public_report_repo = public_report_repo
        self.token_repo = token_repo
        self.lead_repo = lead_repo
        self.user_repo = user_repo
        self.org_repo = org_repo
        self.evidence_repo = evidence_repo

    # ------------------------------------------------------------------
    # list_public_incidents
    # ------------------------------------------------------------------

    async def list_public_incidents(
        self,
        session: AsyncSession,
        vendor_name: str,
    ) -> list[PublicIncidentResponse]:
        """Return public incidents for a vendor from the last 90 days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        # Get all public evidence reports for this vendor
        public_reports = await self.public_report_repo.list_public_for_vendor(
            session, vendor_name
        )
        if not public_reports:
            return []

        incident_ids = [pr.incident_id for pr in public_reports]
        report_map = {pr.incident_id: pr for pr in public_reports}

        result = await session.execute(
            select(Incident)
            .where(
                Incident.id.in_(incident_ids),
                Incident.started_at >= cutoff,
            )
            .order_by(Incident.started_at.desc())
        )
        incidents = result.scalars().all()

        responses: list[PublicIncidentResponse] = []
        for inc in incidents:
            pub = report_map.get(inc.id)
            duration = None
            if inc.resolved_at:
                duration = (inc.resolved_at - inc.started_at).total_seconds() / 60.0

            responses.append(
                PublicIncidentResponse(
                    incident_id=inc.id,
                    vendor_name=vendor_name,
                    title=pub.custom_title if pub and pub.custom_title else f"{vendor_name} Incident",
                    started_at=inc.started_at,
                    resolved_at=inc.resolved_at,
                    duration_minutes=duration,
                    severity=inc.severity,
                    status=inc.status,
                    max_latency_ms=None,
                    downtime_percentage=None,
                    has_evidence_report=True,
                    download_token=None,
                )
            )
        return responses

    # ------------------------------------------------------------------
    # process_gate
    # ------------------------------------------------------------------

    async def process_gate(
        self,
        session: AsyncSession,
        request: EvidenceGateRequest,
        client_ip: str | None,
        user_agent: str | None,
    ) -> EvidenceGateResponse:
        """Process the evidence gate: validate, optionally create account, issue token."""
        # 1. Validate incident has a public evidence report
        pub_report = await self.public_report_repo.get_by_incident(
            session, request.incident_id
        )
        if not pub_report or not pub_report.is_public:
            raise ResourceNotFoundException(
                "No public evidence report found for this incident"
            )

        # Verify vendor name matches
        if pub_report.vendor_name.lower() != request.vendor_name.lower():
            raise ValidationException("Vendor name does not match the evidence report")

        # 2. Check if email matches existing user
        existing_user = await self.user_repo.get_by_email(session, request.email)
        account_created = False
        user_id: uuid.UUID | None = existing_user.id if existing_user else None

        # 3. Auto-create account if no existing user
        if not existing_user:
            random_password = secrets.token_urlsafe(16)
            password_hash = get_password_hash(random_password)
            full_name = request.full_name or request.email.split("@")[0]

            new_user = await self.user_repo.create(
                session=session,
                email=request.email,
                password_hash=password_hash,
                full_name=full_name,
                is_email_verified=False,
            )
            user_id = new_user.id
            account_created = True

            # Create org if org_name provided
            if request.org_name:
                slug = re.sub(r"[^\w-]", "-", request.org_name.lower())
                slug = re.sub(r"-+", "-", slug).strip("-")
                slug = f"{slug}-{secrets.token_hex(4)}"

                new_org = await self.org_repo.create(
                    session=session,
                    name=request.org_name,
                    slug=slug,
                )
                await self.org_repo.add_member(
                    session=session,
                    org_id=new_org.id,
                    user_id=new_user.id,
                    role="owner",
                )

            # Increment accounts_created on the public report
            await self.public_report_repo.increment_accounts_created(
                session, pub_report.id
            )

            # Mark any prior lead events for this email as converted
            await self.lead_repo.mark_converted(session, user_id, request.email)

        # 4. Generate download token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        # 5. Set expires_at = now + 1 hour
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        # 6. Create EvidenceGateToken record
        await self.token_repo.create(
            session=session,
            report_id=pub_report.id,
            email=request.email,
            token_hash=token_hash,
            ip_address=client_ip,
            user_id=user_id,
            expires_at=expires_at,
        )

        # 7. Log LeadCaptureEvent
        await self.lead_repo.create(
            session=session,
            source="evidence_download",
            email=request.email,
            user_id=user_id,
            vendor_name=request.vendor_name,
            incident_id=request.incident_id,
            ref_code=request.ref_code,
            ip_address=client_ip,
            user_agent=user_agent,
            metadata_={"account_created": account_created},
        )

        # 8. Return download URL
        download_url = f"{settings.FRONTEND_BASE_URL}/evidence/download/{raw_token}"
        login_url = f"{settings.FRONTEND_BASE_URL}/login" if account_created else None

        message = (
            "Account created! Check your email to set your password and log in."
            if account_created
            else "Your download link is ready."
        )

        return EvidenceGateResponse(
            download_url=download_url,
            report_id=pub_report.id,
            expires_at=expires_at,
            account_created=account_created,
            login_url=login_url,
            message=message,
        )

    # ------------------------------------------------------------------
    # download_evidence
    # ------------------------------------------------------------------

    async def download_evidence(
        self,
        session: AsyncSession,
        token: str,
        client_ip: str | None,
        user_agent: str | None,
    ) -> tuple[bytes, str]:
        """Validate token, retrieve evidence file, mark as downloaded.

        Returns (file_bytes, filename).
        """
        # 1. Hash the token and look up
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        gate_token = await self.token_repo.get_by_token_hash(session, token_hash)
        if not gate_token:
            raise ResourceNotFoundException("Invalid or expired download token")

        # 2. Validate not expired
        if datetime.now(timezone.utc) > gate_token.expires_at:
            raise ValidationException("Download token has expired")

        # 3. Get the evidence report and file path
        pub_report = await self.public_report_repo.get_by_id(
            session, gate_token.report_id
        )
        if not pub_report:
            raise ResourceNotFoundException("Public evidence report not found")

        evidence_report = await self.evidence_repo.get_by_id(
            session, pub_report.report_id
        )
        if not evidence_report:
            raise ResourceNotFoundException("Evidence report file not found")

        # 4. Download file bytes from storage
        try:
            file_bytes = storage_client.download_bytes(evidence_report.file_path)
        except FileNotFoundError as exc:
            raise ResourceNotFoundException(
                "Evidence report file not found in storage"
            ) from exc

        # 5. Mark token as downloaded and increment count
        if gate_token.downloaded_at is None:
            await self.token_repo.mark_downloaded(session, gate_token.id)
            await self.public_report_repo.increment_download_count(
                session, pub_report.id
            )

        # Derive a human-friendly filename from the vendor name and incident
        safe_vendor = re.sub(r"[^\w-]", "-", pub_report.vendor_name.lower())
        filename = f"{safe_vendor}-evidence-{str(pub_report.incident_id)[:8]}.pdf"

        return file_bytes, filename

    # ------------------------------------------------------------------
    # publicize_evidence
    # ------------------------------------------------------------------

    async def publicize_evidence(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        admin_user_id: uuid.UUID,
        request: PublicizeEvidenceRequest,
    ) -> PublicizeResponse:
        """Make an evidence report public (or private)."""
        # Find the incident
        result = await session.execute(
            select(Incident).where(
                Incident.id == request.incident_id,
                Incident.org_id == org_id,
            )
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise ResourceNotFoundException("Incident not found")

        # Find the evidence report for this incident
        evidence_report = await self.evidence_repo.get_by_incident(
            session, incident.id
        )
        if not evidence_report:
            raise ResourceNotFoundException(
                "No evidence report exists for this incident. Generate one first."
            )

        # Determine vendor name from the dependency
        from app.modules.dependencies.repository import DependencyRepository

        dependency = await DependencyRepository.get_by_id(
            session, incident.dependency_id
        )
        vendor_name = dependency.name if dependency else "unknown"

        # Check if a public record already exists
        existing = await self.public_report_repo.get_by_incident(session, incident.id)

        if existing:
            await self.public_report_repo.update_publicity(
                session,
                existing,
                is_public=request.make_public,
                custom_title=request.custom_title,
                custom_summary=request.custom_summary,
            )
            report_id = existing.id
        elif request.make_public:
            new_pub = await self.public_report_repo.create(
                session=session,
                incident_id=incident.id,
                vendor_name=vendor_name,
                report_id=evidence_report.id,
                is_public=True,
                custom_title=request.custom_title,
                custom_summary=request.custom_summary,
            )
            report_id = new_pub.id
        else:
            raise ResourceNotFoundException(
                "No public record exists to unpublish"
            )

        action = "public" if request.make_public else "private"
        return PublicizeResponse(
            message=f"Evidence report is now {action}",
            report_id=report_id,
        )

    # ------------------------------------------------------------------
    # get_stats
    # ------------------------------------------------------------------

    async def get_stats(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
    ) -> EvidenceGateStats:
        """Get evidence gate conversion statistics."""
        total_downloads = await self.lead_repo.get_total_downloads(session)
        total_accounts = await self.lead_repo.get_total_accounts_created(session)
        conversion_rate = await self.lead_repo.get_conversion_rate(session)
        top_vendors = await self.lead_repo.get_top_vendors(session)
        recent_conversions = await self.lead_repo.get_recent_conversions(session)

        return EvidenceGateStats(
            total_gated_downloads=total_downloads,
            total_accounts_created=total_accounts,
            conversion_rate=conversion_rate,
            top_vendors=top_vendors,
            recent_conversions=recent_conversions,
        )


evidence_gate_service = EvidenceGateService()
