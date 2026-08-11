"""Evidence access, plan enforcement, and asynchronous generation dispatch."""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol
from uuid import UUID

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.infrastructure.storage import ObjectStorage
from app.modules.evidence.constants import DOWNLOAD_URL_TTL_SECONDS, EVIDENCE_PLANS
from app.modules.evidence.repository import EvidenceRepository
from app.modules.evidence.schemas import EvidenceQueuedResponse, EvidenceReportResponse
from app.modules.incidents.service import IncidentService
from app.modules.organizations.service import OrganizationService


class EvidenceTaskDispatcher(Protocol):
    def send(self, task: str, *args: object) -> None: ...


class EvidenceService:
    def __init__(
        self,
        repository: EvidenceRepository,
        incidents: IncidentService,
        organizations: OrganizationService,
        storage: ObjectStorage,
        dispatcher: EvidenceTaskDispatcher | None = None,
    ) -> None:
        self.repository = repository
        self.incidents = incidents
        self.organizations = organizations
        self.storage = storage
        self.dispatcher = dispatcher

    async def list(self, org_id: UUID) -> list[EvidenceReportResponse]:
        models = await self.repository.list(org_id)
        return [EvidenceReportResponse.model_validate(model) for model in models]

    async def get(self, org_id: UUID, report_id: UUID) -> EvidenceReportResponse:
        model = await self.repository.get(org_id, report_id)
        if model is None:
            raise NotFoundError("Evidence report not found")
        response = EvidenceReportResponse.model_validate(model)
        response.download_url = await self.storage.async_presign(
            model.file_path, timedelta(seconds=DOWNLOAD_URL_TTL_SECONDS)
        )
        return response

    async def get_or_trigger(
        self, org_id: UUID, incident_id: UUID
    ) -> EvidenceReportResponse | EvidenceQueuedResponse:
        await self._ensure_supported(org_id)
        incident = await self.incidents.detail(org_id, incident_id)
        if incident.status.value != "resolved":
            raise ConflictError("Evidence can only be generated for a resolved incident")
        if not incident.correlations:
            raise ConflictError("Evidence requires at least one confirmed correlation")
        existing = await self.repository.latest_for_incident(org_id, incident_id)
        if existing:
            return await self.get(org_id, existing.id)
        self._dispatch(incident_id)
        return EvidenceQueuedResponse(incident_id=incident_id)

    async def regenerate(self, org_id: UUID, report_id: UUID) -> EvidenceQueuedResponse:
        await self._ensure_supported(org_id)
        report = await self.repository.get(org_id, report_id)
        if report is None:
            raise NotFoundError("Evidence report not found")
        self._dispatch(report.incident_id)
        return EvidenceQueuedResponse(incident_id=report.incident_id)

    async def _ensure_supported(self, org_id: UUID) -> None:
        organization = await self.organizations.get(org_id)
        if organization.plan not in EVIDENCE_PLANS:
            raise ForbiddenError("Evidence reports require the standard plan or higher")

    def _dispatch(self, incident_id: UUID) -> None:
        if self.dispatcher is None:
            raise RuntimeError("Evidence task dispatcher is not configured")
        self.dispatcher.send("evidence.generate_report", str(incident_id))
