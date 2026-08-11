"""Extensible notification strategy registry and routing service."""

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

import httpx

from app.core.exceptions import AppError, NotFoundError
from app.infrastructure.email import EmailClient
from app.modules.notifications.constants import ChannelType
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import (
    AlertConfigCreateRequest,
    AlertConfigResponse,
    AlertConfigUpdateRequest,
    AlertPayload,
    NotificationResult,
)


class BaseNotificationChannel(ABC):
    @abstractmethod
    async def send(self, payload: AlertPayload, config: dict[str, Any]) -> bool: ...


class EmailChannel(BaseNotificationChannel):
    def __init__(self, email: EmailClient) -> None:
        self.email = email

    async def send(self, payload: AlertPayload, config: dict[str, Any]) -> bool:
        recipient = str(config.get("recipient", ""))
        if not recipient:
            raise AppError("Email notification requires config.recipient")
        await self.email.send(recipient, payload.title, payload.body)
        return True


class WebhookChannel(BaseNotificationChannel):
    async def send(self, payload: AlertPayload, config: dict[str, Any]) -> bool:
        url = str(config.get("url", ""))
        if not url:
            raise AppError("Webhook notification requires config.url")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload.model_dump(mode="json"))
            response.raise_for_status()
        return True


class SlackChannel(WebhookChannel):
    async def send(self, payload: AlertPayload, config: dict[str, Any]) -> bool:
        url = str(config.get("webhook_url", ""))
        if not url:
            raise AppError("Slack notification requires config.webhook_url")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json={"text": f"*{payload.title}*\n{payload.body}"})
            response.raise_for_status()
        return True


class PagerDutyChannel(WebhookChannel):
    async def send(self, payload: AlertPayload, config: dict[str, Any]) -> bool:
        routing_key = str(config.get("routing_key", ""))
        if not routing_key:
            raise AppError("PagerDuty notification requires config.routing_key")
        body = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": payload.title,
                "source": "reliastra",
                "severity": payload.severity,
                "custom_details": payload.metadata,
            },
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://events.pagerduty.com/v2/enqueue", json=body)
            response.raise_for_status()
        return True


class NotificationService:
    def __init__(self, repository: NotificationRepository, email: EmailClient) -> None:
        self.repository = repository
        self.channels: dict[ChannelType, BaseNotificationChannel] = {
            ChannelType.EMAIL: EmailChannel(email),
            ChannelType.SLACK: SlackChannel(),
            ChannelType.WEBHOOK: WebhookChannel(),
            ChannelType.PAGERDUTY: PagerDutyChannel(),
        }

    def register_channel(self, channel_type: ChannelType, channel: BaseNotificationChannel) -> None:
        self.channels[channel_type] = channel

    async def list(self, org_id: UUID) -> list[AlertConfigResponse]:
        return [
            AlertConfigResponse.model_validate(item) for item in await self.repository.list(org_id)
        ]

    async def get(self, org_id: UUID, config_id: UUID) -> AlertConfigResponse:
        model = await self.repository.get(org_id, config_id)
        if model is None:
            raise NotFoundError("Alert configuration not found")
        return AlertConfigResponse.model_validate(model)

    async def create(self, org_id: UUID, request: AlertConfigCreateRequest) -> AlertConfigResponse:
        self._validate_config(request.channel_type, request.config)
        return AlertConfigResponse.model_validate(
            await self.repository.create(org_id, request.model_dump())
        )

    async def update(
        self, org_id: UUID, config_id: UUID, request: AlertConfigUpdateRequest
    ) -> AlertConfigResponse:
        model = await self.repository.get(org_id, config_id)
        if model is None:
            raise NotFoundError("Alert configuration not found")
        values = request.model_dump(exclude_unset=True)
        if request.config is not None:
            self._validate_config(model.channel_type, request.config)
        return AlertConfigResponse.model_validate(await self.repository.update(model, values))

    async def delete(self, org_id: UUID, config_id: UUID) -> None:
        model = await self.repository.get(org_id, config_id)
        if model is None:
            raise NotFoundError("Alert configuration not found")
        await self.repository.delete(model)

    async def test(self, org_id: UUID, config_id: UUID) -> NotificationResult:
        payload = AlertPayload(
            org_id=org_id,
            severity="minor",
            title="Reliastra test alert",
            body="Your notification channel is configured correctly.",
        )
        delivered = await self.send_one(org_id, config_id, payload)
        return NotificationResult(config_id=config_id, delivered=delivered)

    async def send_one(self, org_id: UUID, config_id: UUID, payload: AlertPayload) -> bool:
        config = await self.repository.get(org_id, config_id)
        if config is None:
            raise NotFoundError("Alert configuration not found")
        if not config.is_active:
            return False
        return await self.channels[config.channel_type].send(payload, config.config)

    async def dispatch(self, payload: AlertPayload) -> builtins.list[NotificationResult]:
        configs = await self.repository.list(payload.org_id, active_only=True)
        results = []
        for config in configs:
            delivered = await self.channels[config.channel_type].send(payload, config.config)
            results.append(NotificationResult(config_id=config.id, delivered=delivered))
        return results

    @staticmethod
    def _validate_config(channel: ChannelType, config: dict[str, Any]) -> None:
        required = {
            ChannelType.EMAIL: "recipient",
            ChannelType.SLACK: "webhook_url",
            ChannelType.WEBHOOK: "url",
            ChannelType.PAGERDUTY: "routing_key",
        }[channel]
        if not config.get(required):
            raise AppError(f"{channel.value} configuration requires '{required}'")
