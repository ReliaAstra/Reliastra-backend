"""Incident lifecycle and pluggable correlation strategy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page
from app.modules.dependencies.service import DependencyService
from app.modules.incidents.constants import (
    CORRELATION_WINDOW_SECONDS,
    TEMPORAL_CONFIDENCE,
    CorrelationMethod,
    IncidentSeverity,
    IncidentStatus,
)
from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.schemas import (
    CorrelationResponse,
    IncidentDetailResponse,
    IncidentResponse,
    IncidentUpdateRequest,
    ManualCorrelationRequest,
)
from app.modules.organizations.constants import Plan
from app.modules.organizations.service import OrganizationService


class IncidentTaskDispatcher(Protocol):
    def send(self, task: str, *args: object) -> None: ...


class CorrelationStrategy(ABC):
    @abstractmethod
    async def correlate(self, incident_id: UUID) -> list[CorrelationResponse]: ...


class TemporalCorrelationStrategy(CorrelationStrategy):
    def __init__(self, repository: IncidentRepository) -> None:
        self.repository = repository

    async def correlate(self, incident_id: UUID) -> list[CorrelationResponse]:
        incident = await self.repository.get_any_org(incident_id)
        if incident is None:
            raise NotFoundError("Incident not found")
        delta = timedelta(seconds=CORRELATION_WINDOW_SECONDS)
        candidates = await self.repository.candidates(
            incident.org_id,
            incident.dependency_id,
            incident.started_at - delta,
            incident.started_at + delta,
        )
        return [
            CorrelationResponse.model_validate(
                await self.repository.add_correlation(
                    incident.id,
                    candidate.dependency_id,
                    TEMPORAL_CONFIDENCE,
                    CORRELATION_WINDOW_SECONDS,
                    CorrelationMethod.TEMPORAL,
                )
            )
            for candidate in candidates
        ]


class IncidentService:
    def __init__(
        self,
        repository: IncidentRepository,
        dependencies: DependencyService,
        dispatcher: IncidentTaskDispatcher | None = None,
        organizations: OrganizationService | None = None,
    ) -> None:
        self.repository = repository
        self.dependencies = dependencies
        self.dispatcher = dispatcher
        self.organizations = organizations
        self.strategies: dict[str, CorrelationStrategy] = {
            "temporal": TemporalCorrelationStrategy(repository)
        }

    def register_strategy(self, name: str, strategy: CorrelationStrategy) -> None:
        self.strategies[name] = strategy

    async def create_for_dependency(self, dependency_id: UUID) -> IncidentDetailResponse:
        existing = await self.repository.open_for_dependency(dependency_id)
        if existing:
            return await self.detail(existing.org_id, existing.id)
        dependency = await self.dependencies.execution_config(dependency_id)
        incident = await self.repository.create(dependency.org_id, dependency.id)
        correlations = await self.strategies["temporal"].correlate(incident.id)
        return IncidentDetailResponse(
            **IncidentResponse.model_validate(incident).model_dump(), correlations=correlations
        )

    async def resolve_for_dependency(self, dependency_id: UUID) -> IncidentDetailResponse | None:
        incident = await self.repository.open_for_dependency(dependency_id)
        if incident is None:
            return None
        await self.repository.update(
            incident, {"status": IncidentStatus.RESOLVED, "resolved_at": datetime.now(UTC)}
        )
        detail = await self.detail(incident.org_id, incident.id)
        if (
            detail.correlations
            and self.dispatcher
            and await self._plan_supports_evidence(incident.org_id)
        ):
            self.dispatcher.send("evidence.generate_report", str(incident.id))
        return detail

    async def list(
        self,
        org_id: UUID,
        limit: int,
        cursor: UUID | None,
        status: IncidentStatus | None,
        severity: IncidentSeverity | None,
    ) -> Page[IncidentResponse]:
        models = await self.repository.list(org_id, limit, cursor, status, severity)
        has_more = len(models) > limit
        items = [IncidentResponse.model_validate(model) for model in models[:limit]]
        return Page(items=items, next_cursor=items[-1].id if has_more else None)

    async def detail(self, org_id: UUID, incident_id: UUID) -> IncidentDetailResponse:
        model = await self.repository.get(org_id, incident_id)
        if model is None:
            raise NotFoundError("Incident not found")
        correlations = [
            CorrelationResponse.model_validate(item)
            for item in await self.repository.correlations(incident_id)
        ]
        return IncidentDetailResponse(
            **IncidentResponse.model_validate(model).model_dump(), correlations=correlations
        )

    async def update(
        self, org_id: UUID, incident_id: UUID, request: IncidentUpdateRequest
    ) -> IncidentDetailResponse:
        model = await self.repository.get(org_id, incident_id)
        if model is None:
            raise NotFoundError("Incident not found")
        values = request.model_dump(exclude_unset=True)
        if request.status == IncidentStatus.RESOLVED and model.status == IncidentStatus.OPEN:
            values["resolved_at"] = datetime.now(UTC)
        await self.repository.update(model, values)
        detail = await self.detail(org_id, incident_id)
        if request.status == IncidentStatus.RESOLVED and detail.correlations and self.dispatcher:
            self.dispatcher.send("evidence.generate_report", str(incident_id))
        return detail

    async def manual_correlate(
        self, org_id: UUID, incident_id: UUID, request: ManualCorrelationRequest
    ) -> CorrelationResponse:
        incident = await self.repository.get(org_id, incident_id)
        if incident is None:
            raise NotFoundError("Incident not found")
        if incident.dependency_id == request.correlated_dependency_id:
            raise ConflictError("An incident cannot be correlated to its own dependency")
        await self.dependencies.get(org_id, request.correlated_dependency_id)
        model = await self.repository.add_correlation(
            incident_id,
            request.correlated_dependency_id,
            request.confidence,
            CORRELATION_WINDOW_SECONDS,
            CorrelationMethod.MANUAL,
        )
        return CorrelationResponse.model_validate(model)

    async def _plan_supports_evidence(self, org_id: UUID) -> bool:
        if self.organizations is None:
            return False
        organization = await self.organizations.get(org_id)
        return organization.plan != Plan.FREE

    async def attach_evidence(self, incident_id: UUID, report_id: UUID) -> None:
        await self.repository.attach_evidence(incident_id, report_id)

    async def open_count(self, org_id: UUID) -> int:
        return await self.repository.open_count(org_id)
