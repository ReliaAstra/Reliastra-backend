"""Playwright PDF evidence generation pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from app.config import Settings
from app.core.audit_log import AuditLogService
from app.infrastructure.celery_app import celery_app
from app.infrastructure.storage import ObjectStorage
from app.infrastructure.workers.runtime import worker_session
from app.modules.notifications.schemas import AlertPayload


@celery_app.task(  # type: ignore[untyped-decorator]
    name="evidence.generate_report", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def generate_evidence_report(incident_id: str) -> str:
    return asyncio.run(_generate(UUID(incident_id)))


async def _generate(incident_id: UUID) -> str:
    from app.dependencies import (
        build_check_service,
        build_evidence_repository,
        build_incident_service,
        build_organization_service,
    )
    from app.modules.evidence.constants import EVIDENCE_PLANS

    settings = Settings()
    async with worker_session(settings) as session:
        incidents = build_incident_service(session, settings)
        incident = await incidents.repository.get_any_org(incident_id)
        if incident is None:
            raise ValueError("Incident not found")
        detail = await incidents.detail(incident.org_id, incident_id)
        if detail.status.value != "resolved" or not detail.correlations:
            raise ValueError("Evidence requires a resolved, correlated incident")
        organization = await build_organization_service(session).get(incident.org_id)
        if organization.plan not in EVIDENCE_PLANS:
            raise PermissionError("Organization plan does not include evidence reports")
        now = datetime.now(UTC)
        checks = build_check_service(session, settings)
        results = await checks.evidence_results(
            incident.org_id, incident.dependency_id, now - timedelta(days=1), now
        )
        total = len(results)
        measured_uptime = sum(item.is_up for item in results) / total if total else 0.0
        structured = {
            "incident": detail.model_dump(mode="json"),
            "checks": [item.model_dump(mode="json") for item in results],
            "generated_at": now.isoformat(),
            "measured_uptime": measured_uptime,
            "sla_impact": max(0.0, 1.0 - measured_uptime),
        }
        payload_checksum = hashlib.sha256(
            json.dumps(structured, sort_keys=True).encode()
        ).hexdigest()
        html = _render_html(structured, payload_checksum)
        pdf = await _render_pdf(html)
        checksum = hashlib.sha256(pdf).hexdigest()
        key = f"{incident.org_id}/{incident.id}/{now:%Y%m%dT%H%M%SZ}-{checksum[:12]}.pdf"
        storage = _storage(settings)
        await asyncio.to_thread(storage.upload_bytes, key, pdf, "application/pdf")
        report = await build_evidence_repository(session).create(
            {
                "org_id": incident.org_id,
                "incident_id": incident.id,
                "file_path": key,
                "file_size_bytes": len(pdf),
                "checksum": checksum,
                "generated_at": now,
            }
        )
        await incidents.attach_evidence(incident.id, report.id)
        await AuditLogService(session).record(
            "evidence.generated",
            "evidence_report",
            org_id=incident.org_id,
            resource_id=report.id,
            metadata={
                "incident_id": str(incident.id),
                "file_checksum": checksum,
                "payload_checksum": payload_checksum,
                "object_key": key,
            },
        )
        download_url = await asyncio.to_thread(storage.presign, key)
        celery_app.send_task(
            "notifications.dispatch",
            args=[
                AlertPayload(
                    org_id=incident.org_id,
                    incident_id=incident.id,
                    severity=incident.severity.value,
                    title="SLA evidence report ready",
                    body=(
                        f"Evidence report {report.id} is ready. "
                        f"Download (expires in one hour): {download_url}"
                    ),
                    metadata={
                        "report_id": str(report.id),
                        "checksum": checksum,
                        "download_url": download_url,
                    },
                ).model_dump(mode="json")
            ],
        )
        return str(report.id)


def _render_html(structured: dict[str, object], payload_checksum: str) -> str:
    root = Path(__file__).resolve().parents[3]
    environment = Environment(
        loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape()
    )
    template = environment.get_template("evidence/default.html")
    return template.render(**structured, payload_checksum=payload_checksum)


async def _render_pdf(html: str) -> bytes:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="networkidle")
        pdf = await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "18mm", "right": "15mm", "bottom": "18mm", "left": "15mm"},
        )
        await browser.close()
        return pdf


def _storage(settings: Settings) -> ObjectStorage:
    return ObjectStorage(
        settings.minio_endpoint,
        settings.minio_access_key.get_secret_value(),
        settings.minio_secret_key.get_secret_value(),
        settings.minio_bucket,
        settings.minio_use_ssl,
    )
