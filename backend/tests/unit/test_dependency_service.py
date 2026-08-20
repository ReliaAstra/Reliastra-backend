import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.core.exceptions import ConflictException, ValidationException
from app.modules.dependencies.schemas import (
    DependencyCreateRequest,
)
from app.modules.dependencies.service import DependencyService
from app.modules.dependencies.constants import HttpMethod


@pytest.mark.asyncio
async def test_create_dependency_success(mocker):
    dep_repo = MagicMock()
    org_repo = MagicMock()
    now = datetime.now(timezone.utc)
    org_id = uuid.uuid4()
    fake_org = MagicMock()
    fake_org.id = org_id
    fake_org.plan = "standard"
    org_repo.get_by_id = AsyncMock(return_value=fake_org)
    dep_repo.count_for_org = AsyncMock(return_value=2)

    fake_dep = MagicMock()
    fake_dep.id = uuid.uuid4()
    fake_dep.org_id = org_id
    fake_dep.application_id = uuid.uuid4()
    fake_dep.name = "Stripe API"
    fake_dep.endpoint_url = "https://api.stripe.com/health"
    fake_dep.method = "GET"
    fake_dep.headers = {"_encrypted_data": "encrypted"}
    fake_dep.expected_status_codes = [200]
    fake_dep.timeout_seconds = 10
    fake_dep.check_interval_seconds = 60
    fake_dep.next_check_at = now
    fake_dep.regions = ["us-east", "eu-west"]
    fake_dep.alert_threshold_ms = 500
    fake_dep.is_active = True
    fake_dep.created_at = now
    fake_dep.updated_at = now

    dep_repo.create = AsyncMock(return_value=fake_dep)
    mocker.patch(
        "app.modules.agencies.repository.AgencyRepository.get_default_application",
        new=AsyncMock(
            return_value=MagicMock(id=fake_dep.application_id, org_id=org_id)
        ),
    )

    service = DependencyService(repository=dep_repo, org_repository=org_repo)
    session = AsyncMock()
    req = DependencyCreateRequest(
        name="Stripe API",
        endpoint_url="https://api.stripe.com/health",
        method=HttpMethod.GET,
        check_interval_seconds=60,
    )
    result = await service.create_dependency(session, org_id, req)

    assert result.name == "Stripe API"
    assert result.check_interval_seconds == 60


@pytest.mark.asyncio
async def test_create_dependency_interval_too_low():
    dep_repo = MagicMock()
    org_repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock()
    fake_org.id = org_id
    fake_org.plan = "free"
    org_repo.get_by_id = AsyncMock(return_value=fake_org)

    service = DependencyService(repository=dep_repo, org_repository=org_repo)
    session = AsyncMock()
    req = DependencyCreateRequest(
        name="Stripe API",
        endpoint_url="https://api.stripe.com/health",
        method=HttpMethod.GET,
        check_interval_seconds=30,  # Minimum for free is 300
    )

    with pytest.raises(ValidationException):
        await service.create_dependency(session, org_id, req)


@pytest.mark.asyncio
async def test_create_dependency_limit_reached():
    dep_repo = MagicMock()
    org_repo = MagicMock()
    org_id = uuid.uuid4()
    fake_org = MagicMock()
    fake_org.id = org_id
    fake_org.plan = "free"
    org_repo.get_by_id = AsyncMock(return_value=fake_org)
    dep_repo.count_for_org = AsyncMock(return_value=5)  # Limit for free is 5

    service = DependencyService(repository=dep_repo, org_repository=org_repo)
    session = AsyncMock()
    req = DependencyCreateRequest(
        name="Stripe API",
        endpoint_url="https://api.stripe.com/health",
        method=HttpMethod.GET,
        check_interval_seconds=300,
    )

    with pytest.raises(ConflictException):
        await service.create_dependency(session, org_id, req)
