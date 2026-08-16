import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.attribution.service import AttributionEngine


@pytest.mark.asyncio
async def test_attribution_is_deterministic(mocker):
    incident = SimpleNamespace(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        dependency_id=uuid.uuid4(),
        started_at=datetime.now(timezone.utc),
    )
    observations = [
        SimpleNamespace(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            region="us-east",
            latency_ms=100.0,
            status_code=500,
            error_type="unexpected_status_code",
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            region="eu-west",
            latency_ms=800.0,
            status_code=500,
            error_type="unexpected_status_code",
        ),
    ]
    mocker.patch(
        "app.modules.attribution.service.IncidentRepository.list_open_in_window",
        new=AsyncMock(return_value=[SimpleNamespace(id=uuid.uuid4())]),
    )
    mocker.patch(
        "app.modules.attribution.service.IncidentRepository.get_correlations",
        new=AsyncMock(
            return_value=[SimpleNamespace(correlation_confidence=0.85)]
        ),
    )

    engine = AttributionEngine()
    first = await engine.compute_attribution(
        AsyncMock(), incident, observations
    )
    second = await engine.compute_attribution(
        AsyncMock(), incident, observations
    )

    assert first.confidence_score == second.confidence_score
    assert first.classification == second.classification
    assert first.signal_breakdown == second.signal_breakdown
    assert first.methodology_version == "v1.0"
