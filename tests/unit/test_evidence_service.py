import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.evidence.service import EvidenceService


@pytest.mark.asyncio
async def test_generate_for_incident():
    evidence_repository = MagicMock()
    incident_repository = MagicMock()
    snapshot_repository = MagicMock()
    incident_id = uuid.uuid4()
    org_id = uuid.uuid4()
    dependency_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    incident = SimpleNamespace(
        id=incident_id,
        org_id=org_id,
        dependency_id=dependency_id,
        started_at=now,
        resolved_at=now,
        severity="major",
        status="resolved",
        root_cause="unknown",
    )
    incident_repository.get_by_id = AsyncMock(return_value=incident)
    incident_repository.get_correlations = AsyncMock(return_value=[])

    dependency = SimpleNamespace(
        id=dependency_id,
        name="Payment API",
        endpoint_url="https://status.example.com",
        regions=["us-east", "eu-west"],
    )
    report = MagicMock(
        id=uuid.uuid4(),
        org_id=org_id,
        incident_id=incident_id,
        file_path=f"evidence/{org_id}/{incident_id}.pdf",
        file_size_bytes=13,
        checksum="abcd123456",
        generated_at=now,
        expires_at=None,
        created_at=now,
        updated_at=now,
    )
    evidence_repository.create = AsyncMock(return_value=report)
    snapshot_repository.create = AsyncMock(
        return_value=MagicMock(id=uuid.uuid4())
    )

    service = EvidenceService(
        repository=evidence_repository,
        inc_repository=incident_repository,
        snapshot_repository=snapshot_repository,
    )
    service._html_to_pdf = AsyncMock(return_value=b"immutable-pdf")

    with (
        patch(
            "app.modules.dependencies.repository.DependencyRepository.get_by_id",
            new=AsyncMock(return_value=dependency),
        ),
        patch(
            "app.modules.checks.repository.CheckRepository.get_aggregated_stats",
            new=AsyncMock(return_value={"uptime_percentage": 95.0}),
        ),
        patch(
            "app.modules.observations.repository.ObservationRepository.list_for_source",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.modules.attribution.repository.AttributionRepository.get_by_incident",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.ai_integration.service.ai_service.generate_explanation",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.modules.evidence.service.storage_client.upload_bytes",
            return_value="stored",
        ),
        patch(
            "app.modules.evidence.service.AuditLogService.log_event",
            new=AsyncMock(),
        ),
        patch(
            "app.modules.notifications.service.notification_service.dispatch_alert",
            new=AsyncMock(return_value=0),
        ),
    ):
        result = await service.generate_for_incident(
            AsyncMock(), incident_id
        )

    assert result.checksum == "abcd123456"
    assert result.incident_id == incident_id
    snapshot_repository.create.assert_awaited_once()
