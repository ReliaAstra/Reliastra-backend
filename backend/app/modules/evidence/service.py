import hashlib
import io
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import jinja2
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import AuditLogService
from app.core.exceptions import ResourceNotFoundException
from app.infrastructure.storage import storage_client
from app.modules.evidence.constants import EVIDENCE_TEMPLATE_PATH
from app.modules.evidence.repository import (
    EvidenceRepository,
    EvidenceSnapshotRepository,
)
from app.modules.evidence.schemas import (
    EvidenceReportDownloadResponse,
    EvidenceReportResponse,
)
from app.modules.incidents.repository import IncidentRepository

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    EVIDENCE_TEMPLATE_PATH,
)


class EvidenceService:
    def __init__(
        self,
        repository: EvidenceRepository = EvidenceRepository(),
        inc_repository: IncidentRepository = IncidentRepository(),
        snapshot_repository: EvidenceSnapshotRepository = EvidenceSnapshotRepository(),
    ) -> None:
        self.repository = repository
        self.inc_repository = inc_repository
        self.snapshot_repository = snapshot_repository
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(os.path.dirname(_TEMPLATE_PATH)),
            autoescape=True,
        )

    async def _render_html(
        self,
        incident: Any,
        dependency: Any,
        correlations: list[Any],
        uptime_pct: float,
        sla_impact_pct: float,
        data_hash: str,
        verification_id: str,
        generated_at: datetime,
        attribution: dict[str, Any] | None = None,
        ai_explanation: str | None = None,
    ) -> str:
        template = self.jinja_env.get_template(os.path.basename(_TEMPLATE_PATH))
        return template.render(
            incident=incident,
            dependency=dependency,
            correlations=correlations,
            uptime_pct=round(uptime_pct, 2),
            sla_impact_pct=round(sla_impact_pct, 2),
            checksum=data_hash,
            data_hash=data_hash,
            verification_id=verification_id,
            attribution=attribution,
            ai_explanation=ai_explanation,
            generated_at=generated_at.isoformat(),
        )

    async def _html_to_pdf(self, html_str: str) -> bytes:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(html_str)
                pdf_bytes = await page.pdf(format="A4", print_background=True)
                await browser.close()
                return pdf_bytes
        except Exception as exc:
            logger.info(
                "Playwright PDF generation unavailable (%s), using xhtml2pdf fallback",
                exc,
            )

        from xhtml2pdf import pisa

        buffer = io.BytesIO()
        status = pisa.CreatePDF(io.StringIO(html_str), dest=buffer)
        if status.err:
            raise RuntimeError(
                "PDF generation failed via both Playwright and xhtml2pdf"
            )
        return buffer.getvalue()

    @staticmethod
    def _attribution_payload(result: Any | None) -> dict[str, Any] | None:
        if result is None:
            return None
        return {
            "id": str(result.id),
            "classification": result.classification,
            "confidence_score": result.confidence_score,
            "signal_breakdown": result.signal_breakdown,
            "supporting_evidence": result.supporting_evidence,
            "contradicting_evidence": result.contradicting_evidence,
            "methodology_version": result.methodology_version,
        }

    @staticmethod
    def _observation_payload(observation: Any) -> dict[str, Any]:
        return {
            "id": str(observation.id),
            "timestamp": observation.timestamp.isoformat(),
            "source_type": observation.source_type,
            "source_id": (
                str(observation.source_id) if observation.source_id else None
            ),
            "region": observation.region,
            "endpoint_url": observation.endpoint_url,
            "latency_ms": observation.latency_ms,
            "status_code": observation.status_code,
            "error_type": observation.error_type,
            "error_message": observation.error_message,
            "metadata": observation.observation_metadata,
        }

    async def generate_for_incident(
        self, session: AsyncSession, incident_id: uuid.UUID
    ) -> EvidenceReportResponse:
        incident = await self.inc_repository.get_by_id(session, incident_id)
        if not incident:
            raise ResourceNotFoundException("Incident not found")

        from app.modules.dependencies.repository import DependencyRepository

        dependency = await DependencyRepository.get_by_id(
            session, incident.dependency_id
        )
        if not dependency:
            raise ResourceNotFoundException("Dependency not found")

        correlations = await self.inc_repository.get_correlations(
            session, incident_id
        )
        from app.modules.checks.repository import CheckRepository

        stats = await CheckRepository.get_aggregated_stats(
            session, dependency.id, window_hours=24
        )
        uptime_pct = stats.get("uptime_percentage", 100.0)
        sla_impact_pct = round(max(0.0, 100.0 - uptime_pct), 2)

        generated_at = datetime.now(timezone.utc)
        window_end = incident.resolved_at or generated_at
        from app.modules.observations.repository import ObservationRepository

        observations = await ObservationRepository.list_for_source(
            session,
            dependency.id,
            source_type="customer_check",
            limit=1000,
            since=incident.started_at,
            until=window_end,
        )
        from app.modules.attribution.repository import AttributionRepository

        attribution_result = await AttributionRepository.get_by_incident(
            session, incident.id
        )
        attribution = self._attribution_payload(attribution_result)
        methodology_version = (
            attribution_result.methodology_version
            if attribution_result
            else "v1.0"
        )

        evidence_data = {
            "schema_version": "1.0",
            "incident": {
                "id": str(incident.id),
                "org_id": str(incident.org_id),
                "dependency_id": str(incident.dependency_id),
                "started_at": incident.started_at.isoformat(),
                "resolved_at": (
                    incident.resolved_at.isoformat()
                    if incident.resolved_at
                    else None
                ),
                "severity": incident.severity,
                "status": incident.status,
                "root_cause": incident.root_cause,
            },
            "dependency": {
                "id": str(dependency.id),
                "name": dependency.name,
                "endpoint_url": dependency.endpoint_url,
                "regions": dependency.regions,
            },
            "time_window": {
                "start": incident.started_at.isoformat(),
                "end": window_end.isoformat(),
            },
            "observations": [
                self._observation_payload(item) for item in observations
            ],
            "attribution": attribution,
            "methodology_version": methodology_version,
        }
        canonical_bytes = json.dumps(
            evidence_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        data_hash = hashlib.sha256(canonical_bytes).hexdigest()
        verification_id = secrets.token_urlsafe(24).rstrip("=")

        ai_explanation = None
        try:
            from app.modules.ai_integration.service import ai_service

            ai_explanation = await ai_service.generate_explanation(
                context={
                    "attribution": attribution,
                    "uptime_percentage": uptime_pct,
                    "sla_impact_percentage": sla_impact_pct,
                    "observation_count": len(observations),
                },
                instruction=(
                    "Explain the measured incident and deterministic attribution "
                    "in language suitable for an SLA evidence report."
                ),
                session=session,
                org_id=incident.org_id,
            )
        except Exception as exc:
            # AI is explicitly optional and can never block factual evidence.
            logger.warning("AI explanation unavailable: %s", exc)

        html = await self._render_html(
            incident=incident,
            dependency=dependency,
            correlations=correlations,
            uptime_pct=uptime_pct,
            sla_impact_pct=sla_impact_pct,
            data_hash=data_hash,
            verification_id=verification_id,
            generated_at=generated_at,
            attribution=attribution,
            ai_explanation=ai_explanation,
        )
        pdf_bytes = await self._html_to_pdf(html)
        report_checksum = hashlib.sha256(pdf_bytes).hexdigest()

        generation_key = uuid.uuid4().hex
        base_path = f"evidence/{incident.org_id}/{incident.id}/{generation_key}"
        report_path = f"{base_path}.pdf"
        json_path = f"{base_path}.json"
        json_document = {
            **evidence_data,
            "data_hash": data_hash,
            "verification_id": verification_id,
            "report_checksum": report_checksum,
            "generated_at": generated_at.isoformat(),
        }
        # Create the DB record FIRST so that a failed S3 upload leaves a
        # record that can be regenerated (P2-6 fix — dual-write compensation).
        report = await self.repository.create(
            session=session,
            org_id=incident.org_id,
            incident_id=incident.id,
            file_path=report_path,
            file_size_bytes=len(pdf_bytes),
            checksum=report_checksum,
        )
        storage_client.upload_bytes(pdf_bytes, report_path, "application/pdf")
        storage_client.upload_bytes(
            json.dumps(
                json_document, sort_keys=True, separators=(",", ":")
            ).encode("utf-8"),
            json_path,
            "application/json",
        )
        snapshot = await self.snapshot_repository.create(
            session,
            incident_id=incident.id,
            org_id=incident.org_id,
            dependency_id=dependency.id,
            time_window_start=incident.started_at,
            time_window_end=window_end,
            observation_ids=[str(item.id) for item in observations],
            attribution_result=attribution,
            methodology_version=methodology_version,
            data_hash=data_hash,
            verification_id=verification_id,
            report_file_path=report_path,
            report_checksum=report_checksum,
            json_evidence_path=json_path,
        )

        await AuditLogService.log_event(
            session=session,
            event_type="EVIDENCE_GENERATED",
            org_id=incident.org_id,
            resource_type="evidence_snapshot",
            resource_id=str(snapshot.id),
            payload={
                "incident_id": str(incident.id),
                "report_id": str(report.id),
                "data_hash": data_hash,
                "report_checksum": report_checksum,
                "verification_id": verification_id,
            },
        )

        try:
            from app.modules.notifications.schemas import AlertPayload
            from app.modules.notifications.service import notification_service

            await notification_service.dispatch_alert(
                session,
                AlertPayload(
                    org_id=incident.org_id,
                    incident_id=incident.id,
                    severity=incident.severity,
                    title="SLA Evidence Report Generated",
                    body=(
                        f"Evidence report generated for incident {incident.id}. "
                        f"Verification ID: {verification_id}"
                    ),
                    metadata={
                        "report_id": str(report.id),
                        "verification_id": verification_id,
                        "checksum": report_checksum,
                        "download_url": storage_client.get_presigned_url(
                            report.file_path, 3600
                        ),
                    },
                ),
            )
        except Exception as exc:
            logger.warning(
                "Could not dispatch alert for evidence report %s: %s",
                report.id,
                exc,
            )

        return EvidenceReportResponse.model_validate(report)

    async def list_reports(
        self, session: AsyncSession, org_id: uuid.UUID, limit: int = 50
    ) -> list[EvidenceReportResponse]:
        reports = await self.repository.list_for_org(
            session, org_id, limit=limit
        )
        return [EvidenceReportResponse.model_validate(item) for item in reports]

    async def get_report_download(
        self, session: AsyncSession, org_id: uuid.UUID, report_id: uuid.UUID
    ) -> EvidenceReportDownloadResponse:
        report = await self.repository.get_by_id(session, report_id)
        if not report or report.org_id != org_id:
            raise ResourceNotFoundException("Evidence report not found")
        data = EvidenceReportResponse.model_validate(report).model_dump()
        data["download_url"] = storage_client.get_presigned_url(
            report.file_path, expires_seconds=3600
        )
        return EvidenceReportDownloadResponse.model_validate(data)

    async def regenerate_report(
        self, session: AsyncSession, org_id: uuid.UUID, report_id: uuid.UUID
    ) -> EvidenceReportResponse:
        report = await self.repository.get_by_id(session, report_id)
        if not report or report.org_id != org_id:
            raise ResourceNotFoundException("Evidence report not found")
        return await self.generate_for_incident(session, report.incident_id)


evidence_service = EvidenceService()
