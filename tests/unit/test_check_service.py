import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.modules.checks.service import CheckService
from app.modules.dependencies.schemas import DependencyInternalDTO


@pytest.mark.asyncio
async def test_execute_check_success(mocker):
    chk_repo = MagicMock()
    dep_repo = MagicMock()
    dep_id = uuid.uuid4()
    org_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    fake_dto = DependencyInternalDTO(
        id=dep_id,
        org_id=org_id,
        name="Test API",
        endpoint_url="https://example.com/api",
        method="GET",
        headers={},
        expected_status_codes=[200],
        timeout_seconds=5,
        check_interval_seconds=60,
        regions=["us-east", "eu-west"],
        alert_threshold_ms=500,
        is_active=True,
    )

    fake_result = MagicMock(
        id=uuid.uuid4(),
        dependency_id=dep_id,
        org_id=org_id,
        region="us-east",
        executed_at=now,
        latency_ms=45.0,
        status_code=200,
        is_up=True,
        error_message=None,
        quorum_confirmed=False,
    )
    chk_repo.create = AsyncMock(return_value=fake_result)
    chk_repo.list_recent_for_dependency = AsyncMock(return_value=[fake_result])

    service = CheckService(repository=chk_repo, dep_repository=dep_repo)
    session = AsyncMock()

    with patch(
        "app.modules.dependencies.service.dependency_service.get_dependency_config_internal",
        new=AsyncMock(return_value=fake_dto),
    ), patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_resp = MagicMock(status_code=200)
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with patch("app.modules.incidents.repository.IncidentRepository.get_open_for_dependency", new=AsyncMock(return_value=None)):
            res = await service.execute_check(session, dep_id, "us-east")

    assert res is not None
    assert res.is_up is True
    assert res.status_code == 200
