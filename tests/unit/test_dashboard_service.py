import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.modules.dashboard.service import DashboardService


@pytest.mark.asyncio
async def test_get_summary():
    repo = MagicMock()
    repo.get_summary_stats = AsyncMock(
        return_value={
            "active_dependencies_count": 10,
            "open_incidents_count": 1,
            "overall_uptime_percentage": 99.8,
            "alerts_today_count": 3,
        }
    )

    service = DashboardService(repository=repo)
    session = AsyncMock()
    res = await service.get_summary(session, uuid.uuid4())

    assert res.active_dependencies_count == 10
    assert res.open_incidents_count == 1
