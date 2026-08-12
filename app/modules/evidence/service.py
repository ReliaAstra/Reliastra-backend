import hashlib
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
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

# Resolve template path relative to the repository root (not CWD).
# app/modules/evidence/service.py -> repository root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATE_PATH = _REPO_ROOT / EVIDENCE_TEMPLATE_PATH


class EvidenceService:
    def __init__(
        self,
        repository: EvidenceRepository = EvidenceRepository(),
        inc_repository: IncidentRepository = IncidentRepository(),
    ) -> None:
        self.repository = repository
        self.inc_repository = inc_repository
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_PATH.parent)),
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
        template = self.jinja_env.get_template(_TEMPLATE_PATH.name)
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

        # Create an immutable evidence snapshot (Phase 7).
        try:
            await self._create_snapshot(
                session=session,
                incident=incident,
                dependency=dependency,
                correlations=correlations,
                report=report,
                checksum=final_checksum,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create evidence snapshot for %s: %s", incident.id, exc)

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

    async def _create_snapshot(
        self,
        *,
        session: AsyncSession,
        incident: Any,
        dependency: Any,
        correlations: list[Any],
        report: Any,
        checksum: str,
    ) -> None:
        """Build and persist an immutable evidence snapshot + JSON evidence."""
        from datetime import timedelta

        from app.modules.attribution.service import attribution_service
        from app.modules.observations.repository import ObservationRepository

        time_window_end = incident.resolved_at or datetime.now(timezone.utc)
        time_window_start = incident.started_at or (
            time_window_end - timedelta(hours=24)
        )

        observations = await ObservationRepository.list_for_dependency(
            session, incident.dependency_id, limit=500
        )
        observation_ids = [o.id for o in observations]

        attribution_result = {}
        try:
            attribution = await attribution_service.compute_for_incident(
                session, incident.id
            )
            attribution_result = attribution.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not compute attribution for snapshot %s: %s", incident.id, exc
            )

        methodology_version = attribution_result.get("methodology_version", "v1.0")
        evidence_json = {
            "incident_id": str(incident.id),
            "dependency_id": str(incident.dependency_id),
            "time_window_start": time_window_start.isoformat(),
            "time_window_end": time_window_end.isoformat(),
            "methodology_version": methodology_version,
            "observation_ids": [str(o) for o in observation_ids],
            "attribution_result": attribution_result,
            "report_checksum": checksum,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # The integrity hash covers the exact bytes that are stored, so a
        # verifier can independently re-hash the downloaded JSON and match.
        import hashlib
        import json

        json_evidence_bytes = json.dumps(
            evidence_json, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        data_hash = hashlib.sha256(json_evidence_bytes).hexdigest()
        json_evidence_path = (
            f"evidence/{incident.org_id}/{incident.id}.json"
        )
        storage_client.upload_bytes(
            json_evidence_bytes, json_evidence_path, "application/json"
        )

        from app.modules.evidence.repository import EvidenceRepository

        await EvidenceRepository.create_snapshot(
            session,
            incident_id=incident.id,
            org_id=incident.org_id,
            dependency_id=incident.dependency_id,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            observation_ids=[str(o) for o in observation_ids],
            attribution_result=attribution_result,
            methodology_version=methodology_version,
            data_hash=data_hash,
            report_file_path=report.file_path,
            report_checksum=checksum,
            json_evidence_path=json_evidence_path,
        )

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
