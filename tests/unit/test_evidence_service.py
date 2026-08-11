import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.modules.evidence.service import EvidenceService
from app.modules.evidence.schemas import EvidenceReportResponse


@pytest.mark.asyncio
async def test_generate_for_incident(mocker):
    evid_repo = MagicMock()
    inc_repo = MagicMock()
    inc_id = uuid.uuid4()
    org_id = uuid.uuid4()
    dep_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    fake_inc = MagicMock(
        id=inc_id,
        org_id=org_id,
        dependency_id=dep_id,
        started_at=now,
        resolved_at=now,
        severity="major",
        status="resolved",
    )
    inc_repo.get_by_id = AsyncMock(return_value=fake_inc)
    inc_repo.get_correlations = AsyncMock(return_value=[])

    fake_dep = MagicMock(
        id=dep_id,
        name="Stripe API",
        endpoint_url="https://status.stripe.com",
        regions=["us-east", "eu-west"],
    )

    fake_report = MagicMock(
        id=uuid.uuid4(),
        org_id=org_id,
        incident_id=inc_id,
        file_path=f"evidence/{org_id}/{inc_id}.pdf",
        file_size_bytes=1024,
        checksum="abcd123456",
        generated_at=now,
        expires_at=None,
        created_at=now,
        updated_at=now,
    )
    evid_repo.get_by_incident = AsyncMock(return_value=None)
    evid_repo.create = AsyncMock(return_value=fake_report)

    service = EvidenceService(repository=evid_repo, inc_repository=inc_repo)
    session = AsyncMock()

    with patch("app.modules.dependencies.repository.DependencyRepository.get_by_id", new=AsyncMock(return_value=fake_dep)), \
         patch("app.modules.checks.repository.CheckRepository.get_aggregated_stats", new=AsyncMock(return_value={"uptime_percentage": 95.0})), \
         patch("app.infrastructure.storage.storage_client.upload_bytes", return_value=f"evidence/{org_id}/{inc_id}.pdf"), \
         patch("app.core.audit_log.AuditLogService.log_event", new=AsyncMock()):
        result = await service.generate_for_incident(session, inc_id)

    assert result.checksum == "abcd123456"
    assert result.incident_id == inc_id
