from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.webhooks.models import Webhook, WebhookDelivery


class WebhookRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        webhook_id: uuid.UUID,
        org_id: uuid.UUID | None = None,
        include_deleted: bool = False,
    ) -> Webhook | None:
        query = select(Webhook).where(Webhook.id == webhook_id)
        if org_id is not None:
            query = query.where(Webhook.org_id == org_id)
        if not include_deleted:
            query = query.where(Webhook.is_deleted == False)  # noqa: E712
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_org(
        session: AsyncSession,
        org_id: uuid.UUID,
    ) -> list[Webhook]:
        query = (
            select(Webhook)
            .where(
                Webhook.org_id == org_id,
                Webhook.is_deleted == False,  # noqa: E712
            )
            .order_by(Webhook.created_at.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_active_for_org_and_event(
        session: AsyncSession,
        org_id: uuid.UUID,
        event_type: str,
    ) -> list[Webhook]:
        """Return active, non-deleted webhooks whose events list includes *event_type*."""
        query = (
            select(Webhook)
            .where(
                Webhook.org_id == org_id,
                Webhook.is_active == True,  # noqa: E712
                Webhook.is_deleted == False,  # noqa: E712
            )
            .order_by(Webhook.created_at.asc())
        )
        result = await session.execute(query)
        all_webhooks = list(result.scalars().all())
        return [w for w in all_webhooks if event_type in (w.events or [])]

    @staticmethod
    async def create(
        session: AsyncSession,
        org_id: uuid.UUID,
        name: str,
        url: str,
        events: list[str],
        secret_hash: str | None,
        custom_headers: dict | None,
        is_active: bool,
        created_by: uuid.UUID,
    ) -> Webhook:
        webhook = Webhook(
            org_id=org_id,
            name=name,
            url=url,
            events=events,
            secret_hash=secret_hash,
            custom_headers=custom_headers,
            is_active=is_active,
            created_by=created_by,
        )
        session.add(webhook)
        await session.flush()
        return webhook

    @staticmethod
    async def soft_delete(
        session: AsyncSession,
        webhook: Webhook,
    ) -> None:
        from datetime import datetime, timezone

        webhook.is_deleted = True
        webhook.deleted_at = datetime.now(timezone.utc)
        session.add(webhook)
        await session.flush()

    @staticmethod
    async def update(
        session: AsyncSession,
        webhook: Webhook,
        **kwargs: object,
    ) -> Webhook:
        for key, value in kwargs.items():
            if value is not None:
                setattr(webhook, key, value)
        session.add(webhook)
        await session.flush()
        return webhook

    @staticmethod
    async def increment_failure_count(
        session: AsyncSession,
        webhook: Webhook,
    ) -> None:
        webhook.failure_count = (webhook.failure_count or 0) + 1
        session.add(webhook)
        await session.flush()

    @staticmethod
    async def reset_failure_count(
        session: AsyncSession,
        webhook: Webhook,
    ) -> None:
        webhook.failure_count = 0
        session.add(webhook)
        await session.flush()

    @staticmethod
    async def update_last_delivery(
        session: AsyncSession,
        webhook: Webhook,
        delivered_at,  # datetime
    ) -> None:
        webhook.last_delivery_at = delivered_at
        session.add(webhook)
        await session.flush()


class WebhookDeliveryRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        delivery_id: uuid.UUID,
    ) -> WebhookDelivery | None:
        query = select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        result = await session.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_webhook(
        session: AsyncSession,
        webhook_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        query = select(WebhookDelivery).where(
            WebhookDelivery.webhook_id == webhook_id
        )
        if status is not None:
            query = query.where(WebhookDelivery.status == status)
        query = query.order_by(WebhookDelivery.created_at.desc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        webhook_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> WebhookDelivery:
        delivery = WebhookDelivery(
            webhook_id=webhook_id,
            event_type=event_type,
            payload=payload,
        )
        session.add(delivery)
        await session.flush()
        return delivery

    @staticmethod
    async def mark_success(
        session: AsyncSession,
        delivery: WebhookDelivery,
        status_code: int,
        response_body: str | None = None,
    ) -> None:
        from datetime import datetime, timezone

        delivery.status = "success"
        delivery.response_status_code = status_code
        delivery.response_body = response_body
        delivery.delivered_at = datetime.now(timezone.utc)
        session.add(delivery)
        await session.flush()

    @staticmethod
    async def mark_failed(
        session: AsyncSession,
        delivery: WebhookDelivery,
        status_code: int | None = None,
        response_body: str | None = None,
        next_retry_at = None,  # datetime | None
    ) -> None:
        delivery.status = "failed" if next_retry_at is None else "retrying"
        delivery.response_status_code = status_code
        delivery.response_body = response_body
        delivery.attempt_count = (delivery.attempt_count or 1)
        if next_retry_at is not None:
            delivery.next_retry_at = next_retry_at
            delivery.attempt_count += 1
        session.add(delivery)
        await session.flush()

    @staticmethod
    async def mark_permanently_failed(
        session: AsyncSession,
        delivery: WebhookDelivery,
    ) -> None:
        delivery.status = "failed_permanently"
        session.add(delivery)
        await session.flush()
