import abc
import asyncio
import hashlib
import hmac
import logging
import time
import uuid
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.core.exceptions import ResourceNotFoundException
from app.core.ssrf_protection import validate_outbound_url
from app.infrastructure.email import email_client
from app.modules.notifications.constants import ChannelType
from app.modules.notifications.models import AlertConfig
from app.modules.notifications.repository import AlertConfigRepository
from app.modules.notifications.schemas import (
    AlertConfigCreateRequest,
    AlertConfigResponse,
    AlertConfigUpdateRequest,
    AlertPayload,
    AlertTestResponse,
)

logger = logging.getLogger(__name__)

# FIX 20: module-level pooled HTTP client shared by Slack/Webhook/PagerDuty —
# no more fresh httpx.AsyncClient() (and handshake) per alert.
_notification_http_client: httpx.AsyncClient | None = None


def get_notification_http_client() -> httpx.AsyncClient:
    global _notification_http_client
    if _notification_http_client is None:
        _notification_http_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=50, max_keepalive_connections=10
            ),
            timeout=httpx.Timeout(10.0),
        )
    return _notification_http_client


async def close_notification_http_client() -> None:
    global _notification_http_client
    if _notification_http_client is not None:
        await _notification_http_client.aclose()
        _notification_http_client = None


def _webhook_secret_for_org(org_id: uuid.UUID) -> bytes:
    """Deterministic per-org webhook signing secret (FIX 30).

    Derived from the server SECRET_KEY + org id so it never has to be stored
    in plaintext and differs across organizations.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"webhook:{org_id}".encode("utf-8"),
        hashlib.sha256,
    ).digest()


def sign_webhook_payload(org_id: uuid.UUID, body: bytes) -> dict[str, str]:
    """Return the X-Reliastra-Signature / X-Reliastra-Timestamp headers."""
    timestamp = str(int(time.time()))
    signature = hmac.new(
        _webhook_secret_for_org(org_id),
        f"{timestamp}.".encode("utf-8") + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Reliastra-Signature": f"t={timestamp},sha256={signature}",
        "X-Reliastra-Timestamp": timestamp,
    }


class BaseNotificationChannel(abc.ABC):
    @abc.abstractmethod
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        pass


class EmailChannel(BaseNotificationChannel):
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        recipient = config.get("email") or config.get("recipient")
        if not recipient:
            logger.warning("EmailChannel config missing 'email' or 'recipient'")
            return False
        result = await asyncio.to_thread(
            email_client.send_email,
            to_email=recipient,
            subject=f"[{alert.severity.upper()}] {alert.title}",
            body=f"{alert.body}\n\nIncident ID: {alert.incident_id or 'N/A'}\nMetadata: {alert.metadata}",
        )
        return result


class SlackChannel(BaseNotificationChannel):
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            logger.warning("SlackChannel config missing 'webhook_url'")
            return False
        # SSRF protection
        try:
            validate_outbound_url(webhook_url)
        except ValueError as exc:
            logger.warning("Slack webhook URL blocked by SSRF protection: %s", exc)
            return False
        payload = {
            "text": f"*{alert.title}* [{alert.severity.upper()}]\n{alert.body}"
        }
        try:
            client = get_notification_http_client()
            resp = await client.post(webhook_url, json=payload)
            return resp.status_code < 400
        except Exception as exc:
            logger.warning("Slack webhook send failed: %s", exc)
            return False


class PagerDutyChannel(BaseNotificationChannel):
    """PagerDuty Events API v2 integration (FIX 19).

    POSTs a ``trigger`` event to https://events.pagerduty.com/v2/enqueue with
    the routing key from the alert config — the previous implementation only
    logged and returned True without sending anything.
    """

    EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"
    _SEVERITY_MAP = {
        "critical": "critical",
        "major": "error",
        "minor": "warning",
    }

    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        routing_key = config.get("routing_key")
        if not routing_key:
            logger.warning("PagerDutyChannel config missing 'routing_key'")
            return False
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": alert.title,
                "source": "reliastra",
                "severity": self._SEVERITY_MAP.get(
                    str(alert.severity).lower(), "info"
                ),
                "custom_details": {
                    "body": alert.body,
                    "incident_id": (
                        str(alert.incident_id) if alert.incident_id else None
                    ),
                    "metadata": alert.metadata,
                },
            },
        }
        try:
            client = get_notification_http_client()
            resp = await client.post(self.EVENTS_API_URL, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "PagerDuty Events API returned %s: %s",
                    resp.status_code,
                    resp.text[:300],
                )
            return resp.status_code < 400
        except Exception as exc:
            logger.warning("PagerDuty alert send failed: %s", exc)
            return False


class WebhookChannel(BaseNotificationChannel):
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        url = config.get("url")
        if not url:
            logger.warning("WebhookChannel config missing 'url'")
            return False
        # SSRF protection
        try:
            validate_outbound_url(url)
        except ValueError as exc:
            logger.warning("Webhook URL blocked by SSRF protection: %s", exc)
            return False
        try:
            body = alert.model_dump_json().encode("utf-8")
            # FIX 30: sign outbound webhooks with the per-org HMAC secret so
            # customers can verify authenticity and reject replays.
            headers = sign_webhook_payload(alert.org_id, body)
            headers["Content-Type"] = "application/json"
            client = get_notification_http_client()
            resp = await client.post(url, content=body, headers=headers)
            return resp.status_code < 400
        except Exception as exc:
            logger.warning("Webhook send failed: %s", exc)
            return False


CHANNEL_REGISTRY: dict[str, type[BaseNotificationChannel]] = {
    ChannelType.EMAIL.value: EmailChannel,
    ChannelType.SLACK.value: SlackChannel,
    ChannelType.PAGERDUTY.value: PagerDutyChannel,
    ChannelType.WEBHOOK.value: WebhookChannel,
}


class NotificationService:
    def __init__(
        self, repository: AlertConfigRepository = AlertConfigRepository()
    ) -> None:
        self.repository = repository

    async def list_configs(
        self, session: AsyncSession, org_id: uuid.UUID
    ) -> list[AlertConfigResponse]:
        configs = await self.repository.list_for_org(session, org_id)
        return [AlertConfigResponse.model_validate(c) for c in configs]

    async def create_config(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        request: AlertConfigCreateRequest,
    ) -> AlertConfigResponse:
        cfg = await self.repository.create(
            session=session,
            org_id=org_id,
            channel_type=request.channel_type.value,
            config=request.config,
            is_active=request.is_active,
        )
        return AlertConfigResponse.model_validate(cfg)

    async def get_config(
        self, session: AsyncSession, org_id: uuid.UUID, config_id: uuid.UUID
    ) -> AlertConfigResponse:
        cfg = await self.repository.get_by_id(session, config_id)
        if not cfg or cfg.org_id != org_id:
            raise ResourceNotFoundException("Alert configuration not found")
        return AlertConfigResponse.model_validate(cfg)

    async def update_config(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        config_id: uuid.UUID,
        request: AlertConfigUpdateRequest,
    ) -> AlertConfigResponse:
        cfg = await self.repository.get_by_id(session, config_id)
        if not cfg or cfg.org_id != org_id:
            raise ResourceNotFoundException("Alert configuration not found")

        update_kwargs = {}
        if request.channel_type is not None:
            update_kwargs["channel_type"] = request.channel_type.value
        if request.config is not None:
            update_kwargs["config"] = request.config
        if request.is_active is not None:
            update_kwargs["is_active"] = request.is_active

        updated = await self.repository.update(session, cfg, **update_kwargs)
        return AlertConfigResponse.model_validate(updated)

    async def delete_config(
        self, session: AsyncSession, org_id: uuid.UUID, config_id: uuid.UUID
    ) -> None:
        cfg = await self.repository.get_by_id(session, config_id)
        if not cfg or cfg.org_id != org_id:
            raise ResourceNotFoundException("Alert configuration not found")
        await self.repository.delete(session, cfg)

    async def send_to_channel(
        self, alert: AlertPayload, channel_type: str, config: dict[str, Any]
    ) -> bool:
        channel_cls = CHANNEL_REGISTRY.get(channel_type.lower())
        if not channel_cls:
            logger.warning("Unsupported channel type: %s", channel_type)
            return False
        channel = channel_cls()
        return await channel.send(alert, config)

    async def send_test_alert(
        self, session: AsyncSession, org_id: uuid.UUID, config_id: uuid.UUID
    ) -> AlertTestResponse:
        cfg = await self.repository.get_by_id(session, config_id)
        if not cfg or cfg.org_id != org_id:
            raise ResourceNotFoundException("Alert configuration not found")

        test_alert = AlertPayload(
            org_id=org_id,
            severity="minor",
            title="Reliastra Test Alert",
            body="This is a test notification from Reliastra MVP.",
            metadata={"test": True},
        )
        success = await self.send_to_channel(
            test_alert, cfg.channel_type, cfg.config
        )
        return AlertTestResponse(
            success=success,
            message="Test alert sent successfully" if success else "Failed to send test alert",
        )

    def _alert_fingerprint(self, alert: AlertPayload) -> str:
        key = (
            f"{alert.org_id}|{alert.severity}|{alert.title}|"
            f"{alert.incident_id or alert.metadata.get('dependency_id', '')}"
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    async def _is_duplicate_alert(self, alert: AlertPayload) -> bool:
        """FIX 39: deduplicate near-identical alerts within a 60s window.

        An incident storm previously multiplied outbound requests (100
        incidents × N channels). Redis SET-NX claims the window; Redis
        failures fail open so alerts are never silently dropped.
        """
        try:
            from app.infrastructure.redis_client import safe_redis_set_nx

            claimed = await safe_redis_set_nx(
                f"alert:dedup:{self._alert_fingerprint(alert)}",
                "1",
                ex=60,
            )
            return not claimed
        except Exception:
            return False

    async def dispatch_alert(
        self, session: AsyncSession, alert: AlertPayload
    ) -> int:
        if await self._is_duplicate_alert(alert):
            logger.info(
                "Suppressing duplicate alert within 60s window: %s",
                alert.title,
            )
            return 0
        configs = await self.repository.list_for_org(
            session, alert.org_id, active_only=True
        )
        sent_count = 0
        for cfg in configs:
            try:
                success = await self.send_to_channel(
                    alert, cfg.channel_type, cfg.config
                )
                if success:
                    sent_count += 1
            except Exception as exc:
                logger.warning("Alert send failed for config %s: %s", cfg.id, exc)
        return sent_count


notification_service = NotificationService()
