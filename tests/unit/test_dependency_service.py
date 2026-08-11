from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.modules.dependencies.repository import DependencyRepository
from app.modules.dependencies.schemas import DependencyCreateRequest
from app.modules.dependencies.service import DependencyService
from app.modules.organizations.constants import Plan
from app.modules.organizations.schemas import OrganizationResponse
from app.modules.organizations.service import OrganizationService
from tests.conftest import settings_factory


@pytest.mark.asyncio
async def test_free_plan_rejects_too_fast_interval() -> None:
    repo = AsyncMock(spec=DependencyRepository)
    repo.count.return_value = 0
    organizations = AsyncMock(spec=OrganizationService)
    organizations.get.return_value = OrganizationResponse(
        id=uuid4(),
        name="Test",
        slug="test",
        plan=Plan.FREE,
        billing_email=None,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )
    service = DependencyService(repo, organizations, settings_factory())
    request = DependencyCreateRequest(
        name="Vendor", endpoint_url="https://example.com", check_interval_seconds=60
    )
    with pytest.raises(AppError, match="plan minimum"):
        await service.create(organizations.get.return_value.id, request)
