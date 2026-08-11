from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.infrastructure.email import EmailClient
from app.modules.notifications.constants import ChannelType
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import AlertPayload
from app.modules.notifications.service import BaseNotificationChannel, NotificationService


class CapturingChannel(BaseNotificationChannel):
    def __init__(self) -> None:
        self.called = False

    async def send(self, payload: AlertPayload, config: dict[str, Any]) -> bool:
        self.called = payload.title == "Test"
        return self.called


@pytest.mark.asyncio
async def test_new_channel_can_be_registered_without_router_changes() -> None:
    service = NotificationService(
        AsyncMock(spec=NotificationRepository), AsyncMock(spec=EmailClient)
    )
    channel = CapturingChannel()
    service.register_channel(ChannelType.WEBHOOK, channel)
    assert await channel.send(
        AlertPayload(org_id=uuid4(), severity="minor", title="Test", body="ok"), {}
    )
    assert channel.called
