import abc
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException
from app.modules.incidents.constants import (
    DEFAULT_CORRELATION_CONFIDENCE,
    TEMPORAL_WINDOW_SECONDS,
    CorrelationMethod,
    IncidentSeverity,
    IncidentStatus,
)
from app.modules.incidents.models import Incident, IncidentCorrelation
from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.schemas import (
    IncidentCorrelateRequest,
    IncidentCorrelationResponse,
    IncidentDetailResponse,
    IncidentResponse,
    IncidentUpdateRequest,
)

logger = logging.getLogger(__name__)


class BaseCorrelationStrategy(abc.ABC):
    @abc.abstractmethod
    async def correlate(
        self, session: AsyncSession, incident: Incident
    ) -> list[IncidentCorrelation]:
        pass


class TemporalCorrelationStrategy(BaseCorrelationStrategy):
    def __init__(
        self,
        window_seconds: int = TEMPORAL_WINDOW_SECONDS,
        repository: IncidentRepository = IncidentRepository(),
    ) -> None:
        self.window_seconds = window_seconds
        self.repository = repository

    async def correlate(
        self, session: AsyncSession, incident: Incident
    ) -> list[IncidentCorrelation]:
        other_incidents = await self.repository.list_open_in_window(
            session=session,
            org_id=incident.org_id,
            center_time=incident.started_at,
            window_seconds=self.window_seconds,
            exclude_incident_id=incident.id,
        )
        correlations: list[IncidentCorrelation] = []
        for other in other_incidents:
            if other.dependency_id != incident.dependency_id:
                corr = await self.repository.create_correlation(
                    session=session,
                    incident_id=incident.id,
                    correlated_dependency_id=other.dependency_id,
                    confidence=DEFAULT_CORRELATION_CONFIDENCE,
                    time_window_seconds=self.window_seconds,
                    method=CorrelationMethod.TEMPORAL.value,
                )
                correlations.append(corr)
                # Also create reverse correlation on the existing incident
                await self.repository.create_correlation(
                    session=session,
                    incident_id=other.id,
                    correlated_dependency_id=incident.dependency_id,
                    confidence=DEFAULT_CORRELATION_CONFIDENCE,
                    time_window_seconds=self.window_seconds,
                    method=CorrelationMethod.TEMPORAL.value,
                )
                logger.info(
                    "Temporal correlation created between incident %s and dependency %s",
                    incident.id,
                    other.dependency_id,
                )
        return correlations


class IncidentService:
    def __init__(
        self,
        repository: IncidentRepository = IncidentRepository(),
        correlation_strategy: BaseCorrelationStrategy = TemporalCorrelationStrategy(),
    ) -> None:
        self.repository = repository
        self.correlation_strategy = correlation_strategy

    async def check_and_create_incident(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        dependency_id: uuid.UUID,
        error_message: str = "Quorum confirmed failure",
    ) -> Incident:
        existing = await self.repository.get_open_for_dependency(
            session, dependency_id
        )
        if existing:
            return existing

        incident = await self.repository.create(
            session=session,
            org_id=org_id,
            dependency_id=dependency_id,
            severity=IncidentSeverity.MAJOR.value,
            description=error_message,
        )
        await self.correlation_strategy.correlate(session, incident)

        try:
            from app.modules.notifications.service import notification_service
            from app.modules.notifications.schemas import AlertPayload

            alert = AlertPayload(
                org_id=org_id,
                incident_id=incident.id,
                severity=incident.severity,
                title="Service Degradation Detected",
                body=f"Dependency {dependency_id} is reporting failure: {error_message}",
                metadata={"dependency_id": str(dependency_id)},
            )
            await notification_service.dispatch_alert(session, alert)
        except Exception as exc:
            logger.warning("Failed to dispatch alert for incident %s: %s", incident.id, exc)

        return incident

    async def resolve_incident(
        self,
        session: AsyncSession,
        incident_id: uuid.UUID,
        org_id: uuid.UUID | None = None,
    ) -> Incident:
        incident = await self.repository.get_by_id(session, incident_id)
        if not incident or (org_id and incident.org_id != org_id):
            raise ResourceNotFoundException("Incident not found")

        updated = await self.repository.update(
            session=session,
            incident=incident,
            status=IncidentStatus.RESOLVED.value,
            resolved_at=datetime.now(timezone.utc),
        )

        correlations = await self.repository.get_correlations(session, incident.id)
        if correlations:
            try:
                from app.modules.evidence.tasks import generate_evidence_report

                generate_evidence_report.delay(str(incident.id))
                logger.info("Dispatched evidence report task for incident %s", incident.id)
            except Exception as exc:
                logger.warning("Could not dispatch evidence task: %s", exc)

        return updated

    async def list_incidents(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        limit: int = 50,
        status: str | None = None,
        severity: str | None = None,
    ) -> list[IncidentResponse]:
        incidents = await self.repository.list_for_org(
            session, org_id, limit=limit, status_filter=status, severity_filter=severity
        )
        return [IncidentResponse.model_validate(inc) for inc in incidents]

    async def get_incident_detail(
        self, session: AsyncSession, org_id: uuid.UUID, inc_id: uuid.UUID
    ) -> IncidentDetailResponse:
        incident = await self.repository.get_by_id(session, inc_id)
        if not incident or incident.org_id != org_id:
            raise ResourceNotFoundException("Incident not found")

        correlations = await self.repository.get_correlations(session, inc_id)
        correlations_resp = [
            IncidentCorrelationResponse.model_validate(c) for c in correlations
        ]

        data = IncidentResponse.model_validate(incident).model_dump()
        data["correlations"] = correlations_resp
        return IncidentDetailResponse.model_validate(data)

    async def update_incident(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        inc_id: uuid.UUID,
        request: IncidentUpdateRequest,
    ) -> IncidentResponse:
        incident = await self.repository.get_by_id(session, inc_id)
        if not incident or incident.org_id != org_id:
            raise ResourceNotFoundException("Incident not found")

        update_kwargs = {}
        if request.status is not None:
            update_kwargs["status"] = request.status.value
            if request.status == IncidentStatus.RESOLVED and not incident.resolved_at:
                update_kwargs["resolved_at"] = datetime.now(timezone.utc)
        if request.severity is not None:
            update_kwargs["severity"] = request.severity.value
        if request.root_cause is not None:
            update_kwargs["root_cause"] = request.root_cause.value
        if request.description is not None:
            update_kwargs["description"] = request.description

        updated = await self.repository.update(session, incident, **update_kwargs)
        return IncidentResponse.model_validate(updated)

    async def manually_correlate(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        inc_id: uuid.UUID,
        request: IncidentCorrelateRequest,
    ) -> IncidentCorrelationResponse:
        incident = await self.repository.get_by_id(session, inc_id)
        if not incident or incident.org_id != org_id:
            raise ResourceNotFoundException("Incident not found")

        corr = await self.repository.create_correlation(
            session=session,
            incident_id=inc_id,
            correlated_dependency_id=request.correlated_dependency_id,
            confidence=request.correlation_confidence,
            time_window_seconds=request.time_window_seconds,
            method=request.correlation_method.value,
        )
        return IncidentCorrelationResponse.model_validate(corr)

    async def get_or_trigger_evidence(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        inc_id: uuid.UUID,
    ) -> dict[str, Any]:
        incident = await self.repository.get_by_id(session, inc_id)
        if not incident or incident.org_id != org_id:
            raise ResourceNotFoundException("Incident not found")

        from app.modules.evidence.repository import EvidenceRepository
        from app.modules.evidence.schemas import EvidenceReportResponse

        report = await EvidenceRepository.get_by_incident(session, inc_id)
        if report:
            return EvidenceReportResponse.model_validate(report).model_dump()

        from app.modules.evidence.service import evidence_service

        report = await evidence_service.generate_for_incident(session, inc_id)
        return EvidenceReportResponse.model_validate(report).model_dump()


incident_service = IncidentService()
