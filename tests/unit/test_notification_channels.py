"""Tests for FIX 19 (PagerDuty), FIX 20 (HTTP pool), FIX 30 (webhook signing),
FIX 39 (alert dedupe)."""

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.modules.notifications.service import (
    NotificationService,
    PagerDutyChannel,
    WebhookChannel,
    get_notification_http_client,
    sign_webhook_payload,
)
from app.modules.notifications.schemas import AlertPayload


def _alert() -> AlertPayload:
    return AlertPayload(
        org_id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        severity="major",
        title="Service Degradation Detected",
        body="dependency is down",
        metadata={"dependency_id": str(uuid.uuid4())},
    )


@pytest.mark.asyncio
async def test_pagerduty_sends_events_api_v2(fake_redis):
    """FIX 19: PagerDuty must POST a real Events API v2 payload."""
    captured = {}

    class FakeResponse:
        status_code = 202

        @property
        def text(self):
            return ""

    class FakeClient:
        async def post(self, url, json=None):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    with patch(
        "app.modules.notifications.service.get_notification_http_client",
        return_value=FakeClient(),
    ):
        channel = PagerDutyChannel()
        ok = await channel.send(_alert(), {"routing_key": "rk-123"})

    assert ok is True
    assert captured["url"] == PagerDutyChannel.EVENTS_API_URL
    assert captured["payload"]["routing_key"] == "rk-123"
    assert captured["payload"]["event_action"] == "trigger"
    assert captured["payload"]["payload"]["severity"] == "error"
    assert "summary" in captured["payload"]["payload"]


@pytest.mark.asyncio
async def test_webhook_channel_signs_payload(fake_redis):
    """FIX 30: outbound webhooks carry a per-org HMAC-SHA256 signature."""
    captured = {}

    class FakeResponse:
        status_code = 200

    class FakeClient:
        async def post(self, url, content=None, headers=None):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return FakeResponse()

    alert = _alert()
    with patch(
        "app.modules.notifications.service.get_notification_http_client",
        return_value=FakeClient(),
    ), patch(
        "app.modules.notifications.service.validate_outbound_url",
        return_value=None,
    ):
        channel = WebhookChannel()
        ok = await channel.send(alert, {"url": "https://customer.example.com/hook"})

    assert ok is True
    signature_header = captured["headers"]["X-Reliastra-Signature"]
    assert signature_header.startswith("t=")
    _, digest = signature_header.split(",", 1)
    _, hex_digest = digest.split("=", 1)

    # Recompute the signature with the per-org secret and verify it matches.
    secret = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"webhook:{alert.org_id}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    timestamp = captured["headers"]["X-Reliastra-Timestamp"]
    expected = hmac.new(
        secret,
        f"{timestamp}.".encode("utf-8") + captured["content"],
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(expected, hex_digest) is True


@pytest.mark.asyncio
async def test_notification_http_client_is_pooled(fake_redis):
    """FIX 20: repeated calls return the SAME client instance."""
    client_a = get_notification_http_client()
    client_b = get_notification_http_client()
    assert client_a is client_b


@pytest.mark.asyncio
async def test_dispatch_alert_dedupes_within_60s(fake_redis):
    """FIX 39: identical alerts within a minute are dispatched once."""
    repo = MagicMock()
    repo.list_for_org = AsyncMock(return_value=[])
    service = NotificationService(repository=repo)

    alert = _alert()
    first = await service.dispatch_alert(MagicMock(), alert)
    assert first == 0  # no configs, but the dedupe window was claimed

    calls = []
    repo.list_for_org = AsyncMock(
        return_value=[MagicMock(id=uuid.uuid4(), channel_type="email", config={"email": "a@b.c"})]
    )
    service.send_to_channel = AsyncMock(return_value=True)

    second = await service.dispatch_alert(MagicMock(), alert)
    # Duplicate within the 60s window: suppressed, nothing sent.
    assert second == 0
    assert service.send_to_channel.await_count == 0

    # A different incident alert passes through.
    other = _alert()
    other.incident_id = uuid.uuid4()
    third = await service.dispatch_alert(MagicMock(), other)
    assert third == 1
