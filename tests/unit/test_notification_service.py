import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.modules.notifications.service import (
    NotificationService,
    EmailChannel,
    SlackChannel,
    PagerDutyChannel,
    WebhookChannel,
)
from app.modules.notifications.schemas import AlertPayload, AlertConfigCreateRequest
from app.modules.notifications.constants import ChannelType


@pytest.mark.asyncio
async def test_email_channel_send(mocker):
    channel = EmailChannel()
    alert = AlertPayload(
        org_id=uuid.uuid4(),
        severity="major",
        title="Test Alert",
        body="Alert body",
    )
    mocker.patch("app.infrastructure.email.email_client.send_email", return_value=True)
    res = await channel.send(alert, {"email": "test@reliastra.com"})
    assert res is True


@pytest.mark.asyncio
async def test_create_config():
    repo = MagicMock()
    org_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    fake_config = MagicMock()
    fake_config.id = uuid.uuid4()
    fake_config.org_id = org_id
    fake_config.channel_type = ChannelType.EMAIL.value
    fake_config.config = {"email": "test@reliastra.com"}
    fake_config.is_active = True
    fake_config.created_at = now
    fake_config.updated_at = now

    repo.create = AsyncMock(return_value=fake_config)

    service = NotificationService(repository=repo)
    session = AsyncMock()
    req = AlertConfigCreateRequest(
        channel_type=ChannelType.EMAIL, config={"email": "test@reliastra.com"}
    )
    res = await service.create_config(session, org_id, req)
    assert res.channel_type == ChannelType.EMAIL.value


@pytest.mark.asyncio
async def test_dispatch_alert():
    repo = MagicMock()
    org_id = uuid.uuid4()
    fake_config = MagicMock()
    fake_config.id = uuid.uuid4()
    fake_config.org_id = org_id
    fake_config.channel_type = ChannelType.PAGERDUTY.value
    fake_config.config = {"routing_key": "12345"}
    fake_config.is_active = True

    repo.list_for_org = AsyncMock(return_value=[fake_config])

    service = NotificationService(repository=repo)
    session = AsyncMock()
    alert = AlertPayload(
        org_id=org_id,
        severity="critical",
        title="Outage",
        body="System down",
    )
    count = await service.dispatch_alert(session, alert)
    assert count == 1
