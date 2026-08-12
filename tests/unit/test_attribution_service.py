import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.modules.attribution.service import AttributionService, SIGNAL_WEIGHTS
from app.modules.attribution.schemas import AttributionResultResponse


def test_score_within_range():
    service = AttributionService()
    signals = {k: 1.0 for k in SIGNAL_WEIGHTS}
    score = service._score(signals)
    assert 0.0 <= score <= 1.0
    assert score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_compute_for_incident_returns_response():
    repo = MagicMock()
    inc_repo = MagicMock()
    inc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    dep_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    fake_incident = MagicMock(
        id=inc_id, org_id=org_id, dependency_id=dep_id, started_at=now
    )
    inc_repo.get_by_id = AsyncMock(return_value=fake_incident)
    inc_repo.get_correlations = AsyncMock(return_value=[])

    fake_dep = MagicMock(id=dep_id, endpoint_url="https://status.stripe.com")
    fake_result = MagicMock(
        id=uuid.uuid4(),
        incident_id=inc_id,
        org_id=org_id,
        dependency_id=dep_id,
        confidence_score=0.5,
        methodology_version="v1.0",
        signals={"temporal_alignment": 0.0},
        evidence_chain={},
        summary="summary",
        created_at=now,
    )
    repo.create = AsyncMock(return_value=fake_result)

    service = AttributionService(repository=repo, inc_repository=inc_repo)
    session = AsyncMock()

    with patch(
        "app.modules.observations.repository.ObservationRepository.list_for_dependency",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.modules.checks.repository.CheckRepository.get_aggregated_stats",
        new=AsyncMock(return_value={"uptime_percentage": 99.0}),
    ), patch(
        "app.modules.dependencies.repository.DependencyRepository.get_by_id",
        new=AsyncMock(return_value=fake_dep),
    ), patch(
        "app.modules.dependencies.repository.DependencyRepository.count_by_endpoint",
        new=AsyncMock(return_value=0),
    ):
        res = await service.compute_for_incident(session, inc_id)

    assert isinstance(res, AttributionResultResponse)
    assert res.confidence_score == 0.5
