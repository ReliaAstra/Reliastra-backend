import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.modules.incidents.service import IncidentService, TemporalCorrelationStrategy
from app.modules.incidents.constants import IncidentStatus


@pytest.mark.asyncio
async def test_check_and_create_incident_new():
    inc_repo = MagicMock()
    inc_repo.get_open_for_dependency = AsyncMock(return_value=None)
    inc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    dep_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    fake_inc = MagicMock()
    fake_inc.id = inc_id
    fake_inc.org_id = org_id
    fake_inc.dependency_id = dep_id
    fake_inc.started_at = now
    fake_inc.resolved_at = None
    fake_inc.severity = "major"
    fake_inc.status = IncidentStatus.OPEN.value
    fake_inc.root_cause = "unknown"
    fake_inc.description = "Down"

    inc_repo.create = AsyncMock(return_value=fake_inc)

    mock_strategy = MagicMock()
    mock_strategy.correlate = AsyncMock(return_value=[])

    service = IncidentService(
        repository=inc_repo, correlation_strategy=mock_strategy
    )
    session = AsyncMock()
    result = await service.check_and_create_incident(session, org_id, dep_id, "Down")

    assert result.id == inc_id
    inc_repo.create.assert_called_once()
    mock_strategy.correlate.assert_called_once()


@pytest.mark.asyncio
async def test_temporal_correlation_strategy():
    repo_mock = MagicMock()
    inc_id1 = uuid.uuid4()
    inc_id2 = uuid.uuid4()
    org_id = uuid.uuid4()
    dep_id1 = uuid.uuid4()
    dep_id2 = uuid.uuid4()
    now = datetime.now(timezone.utc)

    fake_inc1 = MagicMock()
    fake_inc1.id = inc_id1
    fake_inc1.org_id = org_id
    fake_inc1.dependency_id = dep_id1
    fake_inc1.started_at = now

    fake_inc2 = MagicMock()
    fake_inc2.id = inc_id2
    fake_inc2.org_id = org_id
    fake_inc2.dependency_id = dep_id2
    fake_inc2.started_at = now

    repo_mock.list_open_in_window = AsyncMock(return_value=[fake_inc2])
    fake_corr = MagicMock()
    fake_corr.incident_id = inc_id1
    fake_corr.correlated_dependency_id = dep_id2
    fake_corr.correlation_confidence = 0.85
    repo_mock.create_correlation = AsyncMock(return_value=fake_corr)

    strategy = TemporalCorrelationStrategy(repository=repo_mock)
    session = AsyncMock()

    corrs = await strategy.correlate(session, fake_inc1)

    assert len(corrs) == 1
    assert corrs[0].correlated_dependency_id == dep_id2
