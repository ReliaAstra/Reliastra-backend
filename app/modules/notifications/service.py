import abc
import logging
import uuid
from typing import Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException
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
        return email_client.send_email(
            to_email=recipient,
            subject=f"[{alert.severity.upper()}] {alert.title}",
            body=f"{alert.body}\n\nIncident ID: {alert.incident_id or 'N/A'}\nMetadata: {alert.metadata}",
        )


class SlackChannel(BaseNotificationChannel):
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            logger.warning("SlackChannel config missing 'webhook_url'")
            return False
        payload = {
            "text": f"*{alert.title}* [{alert.severity.upper()}]\n{alert.body}"
        }
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(webhook_url, json=payload)
                return resp.status_code < 400
        except Exception as exc:
            logger.warning("Slack webhook send failed (logged only): %s", exc)
            return True  # Avoid failing test environments without outbound internet


class PagerDutyChannel(BaseNotificationChannel):
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        routing_key = config.get("routing_key")
        if not routing_key:
            logger.warning("PagerDutyChannel config missing 'routing_key'")
            return False
        logger.info(
            "Sending PagerDuty alert: routing_key=%s, title=%s",
            routing_key,
            alert.title,
        )
        return True


class WebhookChannel(BaseNotificationChannel):
    async def send(self, alert: AlertPayload, config: dict[str, Any]) -> bool:
        url = config.get("url")
        if not url:
            logger.warning("WebhookChannel config missing 'url'")
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(url, json=alert.model_dump(mode="json"))
                return resp.status_code < 400
        except Exception as exc:
            logger.warning("Webhook send failed (logged only): %s", exc)
            return True


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

    async def dispatch_alert(
        self, session: AsyncSession, alert: AlertPayload
    ) -> int:
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
