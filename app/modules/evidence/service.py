import hashlib
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
import jinja2
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.audit_log import AuditLogService
from app.core.exceptions import ResourceNotFoundException
from app.infrastructure.storage import storage_client
from app.modules.evidence.constants import EVIDENCE_TEMPLATE_PATH
from app.modules.evidence.models import EvidenceReport
from app.modules.evidence.repository import EvidenceRepository
from app.modules.evidence.schemas import (
    EvidenceReportDownloadResponse,
    EvidenceReportResponse,
)
from app.modules.incidents.repository import IncidentRepository

logger = logging.getLogger(__name__)


class EvidenceService:
    def __init__(
        self,
        repository: EvidenceRepository = EvidenceRepository(),
        inc_repository: IncidentRepository = IncidentRepository(),
    ) -> None:
        self.repository = repository
        self.inc_repository = inc_repository
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("."),
            autoescape=True,
        )

    async def _render_html(
        self,
        incident: Any,
        dependency: Any,
        correlations: list[Any],
        uptime_pct: float,
        sla_impact_pct: float,
        checksum: str,
        generated_at: datetime,
    ) -> str:
        template = self.jinja_env.get_template(EVIDENCE_TEMPLATE_PATH)
        return template.render(
            incident=incident,
            dependency=dependency,
            correlations=correlations,
            uptime_pct=round(uptime_pct, 2),
            sla_impact_pct=round(sla_impact_pct, 2),
            checksum=checksum,
            generated_at=generated_at.isoformat(),
        )

    async def _html_to_pdf(self, html_str: str) -> bytes:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(html_str)
                pdf_bytes = await page.pdf(format="A4", print_background=True)
                await browser.close()
                return pdf_bytes
        except Exception as exc:
            logger.info("Playwright PDF generation unavailable (%s), using xhtml2pdf fallback", exc)

        from xhtml2pdf import pisa

        buffer = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.StringIO(html_str), dest=buffer)
        if pisa_status.err:
            raise RuntimeError("PDF generation failed via both Playwright and xhtml2pdf")
        return buffer.getvalue()

    async def generate_for_incident(
        self, session: AsyncSession, incident_id: uuid.UUID
    ) -> EvidenceReportResponse:
        incident = await self.inc_repository.get_by_id(session, incident_id)
        if not incident:
            raise ResourceNotFoundException("Incident not found")

        from app.modules.dependencies.repository import DependencyRepository
        dependency = await DependencyRepository.get_by_id(session, incident.dependency_id)
        if not dependency:
            raise ResourceNotFoundException("Dependency not found")

        correlations = await self.inc_repository.get_correlations(session, incident_id)

        from app.modules.checks.repository import CheckRepository
        stats = await CheckRepository.get_aggregated_stats(session, dependency.id, window_hours=24)
        uptime_pct = stats.get("uptime_percentage", 100.0)
        sla_impact_pct = round(max(0.0, (100.0 - uptime_pct) / 100.0) * 100.0, 2)

        now = datetime.now(timezone.utc)
        placeholder_checksum = "PENDING_SHA256"
        html_str = await self._render_html(
            incident=incident,
            dependency=dependency,
            correlations=correlations,
            uptime_pct=uptime_pct,
            sla_impact_pct=sla_impact_pct,
            checksum=placeholder_checksum,
            generated_at=now,
        )

        pdf_bytes = await self._html_to_pdf(html_str)
        checksum = hashlib.sha256(pdf_bytes).hexdigest()

        html_str_final = await self._render_html(
            incident=incident,
            dependency=dependency,
            correlations=correlations,
            uptime_pct=uptime_pct,
            sla_impact_pct=sla_impact_pct,
            checksum=checksum,
            generated_at=now,
        )
        final_pdf_bytes = await self._html_to_pdf(html_str_final)
        final_checksum = hashlib.sha256(final_pdf_bytes).hexdigest()

        object_key = f"evidence/{incident.org_id}/{incident.id}.pdf"
        storage_client.upload_bytes(final_pdf_bytes, object_key, "application/pdf")

        existing = await self.repository.get_by_incident(session, incident.id)
        if existing:
            report = await self.repository.update(
                session=session,
                report=existing,
                file_path=object_key,
                file_size_bytes=len(final_pdf_bytes),
                checksum=final_checksum,
            )
        else:
            report = await self.repository.create(
                session=session,
                org_id=incident.org_id,
                incident_id=incident.id,
                file_path=object_key,
                file_size_bytes=len(final_pdf_bytes),
                checksum=final_checksum,
            )

        await AuditLogService.log_event(
            session=session,
            event_type="EVIDENCE_GENERATED",
            org_id=incident.org_id,
            resource_type="evidence_report",
            resource_id=str(report.id),
            payload={"incident_id": str(incident.id), "checksum": final_checksum},
        )

        try:
            from app.modules.notifications.service import notification_service
            from app.modules.notifications.schemas import AlertPayload

            alert = AlertPayload(
                org_id=incident.org_id,
                incident_id=incident.id,
                severity=incident.severity,
                title="SLA Evidence Report Generated",
                body=f"Evidence report generated for incident {incident.id}. SHA256: {final_checksum}",
                metadata={
                    "report_id": str(report.id),
                    "checksum": final_checksum,
                    "download_url": storage_client.get_presigned_url(report.file_path, 3600),
                },
            )
            await notification_service.dispatch_alert(session, alert)
        except Exception as exc:
            logger.warning("Could not dispatch alert for evidence report %s: %s", report.id, exc)

        return EvidenceReportResponse.model_validate(report)

    async def list_reports(
        self, session: AsyncSession, org_id: uuid.UUID, limit: int = 50
    ) -> list[EvidenceReportResponse]:
        reports = await self.repository.list_for_org(session, org_id, limit=limit)
        return [EvidenceReportResponse.model_validate(r) for r in reports]

    async def get_report_download(
        self, session: AsyncSession, org_id: uuid.UUID, report_id: uuid.UUID
    ) -> EvidenceReportDownloadResponse:
        report = await self.repository.get_by_id(session, report_id)
        if not report or report.org_id != org_id:
            raise ResourceNotFoundException("Evidence report not found")

        url = storage_client.get_presigned_url(report.file_path, expires_seconds=3600)
        data = EvidenceReportResponse.model_validate(report).model_dump()
        data["download_url"] = url
        return EvidenceReportDownloadResponse.model_validate(data)

    async def regenerate_report(
        self, session: AsyncSession, org_id: uuid.UUID, report_id: uuid.UUID
    ) -> EvidenceReportResponse:
        report = await self.repository.get_by_id(session, report_id)
        if not report or report.org_id != org_id:
            raise ResourceNotFoundException("Evidence report not found")

        return await self.generate_for_incident(session, report.incident_id)


evidence_service = EvidenceService()
