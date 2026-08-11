from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.modules.dependencies.constants import HttpMethod
from app.modules.dependencies.schemas import DependencyExecutionDTO
from app.modules.dependencies.service import DependencyService
from app.modules.incidents.repository import IncidentRepository
from app.modules.incidents.service import IncidentService


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_confirmed_failure_creates_an_incident_through_service_boundary() -> None:
    dependency_id, org_id = uuid4(), uuid4()
    dependencies = AsyncMock(spec=DependencyService)
    dependencies.execution_config.return_value = DependencyExecutionDTO(
        id=dependency_id,
        org_id=org_id,
        endpoint_url="http://failure.local",
        method=HttpMethod.GET,
        headers={},
        expected_status_codes=[200],
        timeout_seconds=1,
        regions=["us-east", "eu-west"],
        alert_threshold_ms=None,
    )
    repository = AsyncMock(spec=IncidentRepository)
    repository.open_for_dependency.return_value = None
    incident = AsyncMock()
    incident.id, incident.org_id, incident.dependency_id = uuid4(), org_id, dependency_id
    incident.started_at, incident.resolved_at = datetime.now(UTC), None
    incident.severity, incident.status, incident.root_cause = "major", "open", "unknown"
    incident.description, incident.evidence_report_id = None, None
    incident.created_at = incident.updated_at = datetime.now(UTC)
    repository.create.return_value = incident
    repository.get_any_org.return_value = incident
    repository.candidates.return_value = []
    service = IncidentService(repository, dependencies)
    result = await service.create_for_dependency(dependency_id)
    assert result.id == incident.id
    repository.create.assert_awaited_once_with(org_id, dependency_id)
