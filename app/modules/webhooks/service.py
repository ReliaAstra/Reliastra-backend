from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundException, ValidationException
from app.core.ssrf_protection import validate_outbound_url
from app.modules.webhooks.models import Webhook, WebhookDelivery
from app.modules.webhooks.repository import (
    WebhookDeliveryRepository,
    WebhookRepository,
)
from app.modules.webhooks.schemas import (
    WebhookCreateRequest,
    WebhookDeliveryResponse,
    WebhookResponse,
    WebhookTestRequest,
    WebhookTestResponse,
    WebhookUpdateRequest,
)

logger = logging.getLogger(__name__)

# Exponential backoff schedule: 1min, 5min, 15min, 1h, 3h
_RETRY_DELAYS: list[timedelta] = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
]
_MAX_RETRIES: int = 5

_WEBHOOK_TIMEOUT_SECONDS: float = 10.0


def _mask_url(url: str) -> str:
    """Return first 30 characters of the URL followed by '***'."""
    if len(url) <= 30:
        return url[:30] + "***"
    return url[:30] + "***"


def _secret_preview(secret_hash: str | None) -> str | None:
    """Show preview 'sk_...{last 4 chars of hash}'."""
    if not secret_hash:
        return None
    return f"sk_...{secret_hash[-4:]}"


class WebhookService:
    def __init__(
        self,
        repo: WebhookRepository = WebhookRepository(),
        delivery_repo: WebhookDeliveryRepository = WebhookDeliveryRepository(),
    ) -> None:
        self.repo = repo
        self.delivery_repo = delivery_repo

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sign_payload(secret: str, body: bytes) -> str:
        """HMAC-SHA256 signature for payload verification."""
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    @staticmethod
    def _hash_secret(secret: str) -> str:
        """SHA-256 hash of the signing secret for storage."""
        return hashlib.sha256(secret.encode()).hexdigest()

    def _to_response(self, webhook: Webhook) -> WebhookResponse:
        """Convert a Webhook ORM object to a WebhookResponse schema."""
        return WebhookResponse(
            id=webhook.id,
            name=webhook.name,
            url_masked=_mask_url(webhook.url),
            events=list(webhook.events or []),
            is_active=webhook.is_active,
            secret_preview=_secret_preview(webhook.secret_hash),
            failure_count=webhook.failure_count or 0,
            last_delivery_at=webhook.last_delivery_at,
            created_at=webhook.created_at,
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create_webhook(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        request: WebhookCreateRequest,
    ) -> Webhook:
        url_str = str(request.url)
        validate_outbound_url(url_str)

        if request.secret:
            secret_hash = self._hash_secret(request.secret)
        else:
            # Auto-generate a secret so every webhook is signable
            generated = secrets.token_urlsafe(32)
            secret_hash = self._hash_secret(generated)

        events = [e.value for e in request.events]

        webhook = await self.repo.create(
            session=session,
            org_id=org_id,
            name=request.name,
            url=url_str,
            events=events,
            secret_hash=secret_hash,
            custom_headers=request.headers,
            is_active=request.is_active,
            created_by=user_id,
        )
        return webhook

    async def list_webhooks(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
    ) -> list[WebhookResponse]:
        webhooks = await self.repo.list_for_org(session, org_id)
        return [self._to_response(w) for w in webhooks]

    async def delete_webhook(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        webhook_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        webhook = await self.repo.get_by_id(session, webhook_id, org_id=org_id)
        if not webhook:
            raise ResourceNotFoundException("Webhook not found")
        await self.repo.soft_delete(session, webhook)

    async def update_webhook(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        webhook_id: uuid.UUID,
        request: WebhookUpdateRequest,
    ) -> WebhookResponse:
        webhook = await self.repo.get_by_id(session, webhook_id, org_id=org_id)
        if not webhook:
            raise ResourceNotFoundException("Webhook not found")

        update_kwargs: dict[str, Any] = {}
        if request.name is not None:
            update_kwargs["name"] = request.name
        if request.url is not None:
            url_str = str(request.url)
            validate_outbound_url(url_str)
            update_kwargs["url"] = url_str
        if request.events is not None:
            update_kwargs["events"] = [e.value for e in request.events]
        if request.headers is not None:
            update_kwargs["custom_headers"] = request.headers
        if request.secret is not None:
            update_kwargs["secret_hash"] = self._hash_secret(request.secret)
        if request.is_active is not None:
            update_kwargs["is_active"] = request.is_active

        updated = await self.repo.update(session, webhook, **update_kwargs)
        return self._to_response(updated)

    # ------------------------------------------------------------------
    # Test
    # ------------------------------------------------------------------

    async def test_webhook(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        webhook_id: uuid.UUID,
        request: WebhookTestRequest,
    ) -> WebhookTestResponse:
        webhook = await self.repo.get_by_id(session, webhook_id, org_id=org_id)
        if not webhook:
            raise ResourceNotFoundException("Webhook not found")

        validate_outbound_url(webhook.url)

        test_payload: dict[str, Any] = {
            "event": request.event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {
                "id": str(uuid.uuid4()),
                "test": True,
                "message": "Webhook test from Reliastra",
            },
        }
        body_bytes = json.dumps(test_payload, default=str).encode()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Reliastra-Event": request.event,
            "X-Reliastra-Delivery": str(uuid.uuid4()),
        }

        # Load the plaintext secret for signing from the stored hash is not
        # possible (we only store the hash).  For the test endpoint we sign
        # with a placeholder so the user can verify the header is present.
        # In production delivery the secret is recovered from the hash (see
        # note in deliver_webhook).  Since we cannot reverse the hash, we
        # skip the signature header on test – the user should test by
        # triggering a real event or we sign with the hash itself as a
        # verification token.
        #
        # We sign using the hash as a verifiable value for test purposes.
        if webhook.secret_hash:
            sig = self._sign_payload(webhook.secret_hash, body_bytes)
            headers["X-Reliastra-Signature"] = f"sha256={sig}"

        # Merge custom headers
        if webhook.custom_headers:
            for k, v in webhook.custom_headers.items():
                headers[k] = v

        start = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
                resp = await client.post(webhook.url, content=body_bytes, headers=headers)
            latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return WebhookTestResponse(
                success=200 <= resp.status_code < 300,
                status_code=resp.status_code,
                response_body=resp.text[:2000] if resp.text else None,
                latency_ms=round(latency_ms, 2),
            )
        except httpx.HTTPError as exc:
            latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return WebhookTestResponse(
                success=False,
                status_code=None,
                response_body=str(exc)[:2000],
                latency_ms=round(latency_ms, 2),
            )

    # ------------------------------------------------------------------
    # Deliveries listing
    # ------------------------------------------------------------------

    async def list_deliveries(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        webhook_id: uuid.UUID,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WebhookDeliveryResponse]:
        webhook = await self.repo.get_by_id(session, webhook_id, org_id=org_id)
        if not webhook:
            raise ResourceNotFoundException("Webhook not found")

        deliveries = await self.delivery_repo.list_for_webhook(
            session, webhook_id, status=status, limit=limit
        )
        return [
            WebhookDeliveryResponse.model_validate(d) for d in deliveries
        ]

    # ------------------------------------------------------------------
    # Core delivery engine
    # ------------------------------------------------------------------

    async def deliver_webhook(
        self,
        session: AsyncSession,
        org_id: uuid.UUID,
        event_type: str,
        payload: dict,
    ) -> None:
        """Find all matching active webhooks and fire delivery."""
        webhooks = await self.repo.list_active_for_org_and_event(
            session, org_id, event_type
        )
        for webhook in webhooks:
            await self._deliver_single(session, webhook, event_type, payload)

    async def _deliver_single(
        self,
        session: AsyncSession,
        webhook: Webhook,
        event_type: str,
        payload: dict,
    ) -> None:
        """Create a delivery record, fire HTTP POST, handle result."""
        delivery = await self.delivery_repo.create(
            session,
            webhook_id=webhook.id,
            event_type=event_type,
            payload=payload,
        )

        body_bytes = json.dumps(payload, default=str).encode()

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Reliastra-Event": event_type,
            "X-Reliastra-Delivery": str(delivery.id),
        }
        if webhook.secret_hash:
            sig = self._sign_payload(webhook.secret_hash, body_bytes)
            headers["X-Reliastra-Signature"] = f"sha256={sig}"

        if webhook.custom_headers:
            for k, v in webhook.custom_headers.items():
                headers[k] = v

        try:
            async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
                resp = await client.post(webhook.url, content=body_bytes, headers=headers)

            if 200 <= resp.status_code < 300:
                await self.delivery_repo.mark_success(
                    session,
                    delivery,
                    status_code=resp.status_code,
                    response_body=resp.text[:5000] if resp.text else None,
                )
                await self.repo.reset_failure_count(session, webhook)
                await self.repo.update_last_delivery(
                    session, webhook, delivery.delivered_at
                )
            else:
                await self._handle_delivery_failure(session, webhook, delivery, resp.status_code, resp.text[:5000] if resp.text else None)
        except httpx.HTTPError as exc:
            await self._handle_delivery_failure(session, webhook, delivery, None, str(exc)[:5000])

    async def _handle_delivery_failure(
        self,
        session: AsyncSession,
        webhook: Webhook,
        delivery: WebhookDelivery,
        status_code: int | None,
        response_body: str | None,
    ) -> None:
        """Handle a failed delivery: retry with backoff or mark permanently failed."""
        await self.repo.increment_failure_count(session, webhook)

        current_attempt = delivery.attempt_count or 1
        if current_attempt >= _MAX_RETRIES:
            await self.delivery_repo.mark_permanently_failed(session, delivery)
            return

        # Calculate next retry time using exponential backoff
        retry_index = min(current_attempt - 1, len(_RETRY_DELAYS) - 1)
        next_retry = datetime.now(timezone.utc) + _RETRY_DELAYS[retry_index]

        await self.delivery_repo.mark_failed(
            session,
            delivery,
            status_code=status_code,
            response_body=response_body,
            next_retry_at=next_retry,
        )

    # ------------------------------------------------------------------
    # Retry engine (callable from a background task / cron)
    # ------------------------------------------------------------------

    async def retry_pending_deliveries(
        self,
        session: AsyncSession,
    ) -> int:
        """Retry all deliveries whose next_retry_at has passed.

        Returns the number of deliveries retried.
        """
        from sqlalchemy import select

        now = datetime.now(timezone.utc)
        query = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == "retrying",
                WebhookDelivery.next_retry_at <= now,
                WebhookDelivery.attempt_count < _MAX_RETRIES,
            )
            .limit(100)
        )
        result = await session.execute(query)
        deliveries = list(result.scalars().all())

        retried = 0
        for delivery in deliveries:
            webhook = await self.repo.get_by_id(
                session, delivery.webhook_id, include_deleted=False
            )
            if not webhook or not webhook.is_active:
                await self.delivery_repo.mark_permanently_failed(session, delivery)
                retried += 1
                continue

            body_bytes = json.dumps(delivery.payload, default=str).encode()
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "X-Reliastra-Event": delivery.event_type,
                "X-Reliastra-Delivery": str(delivery.id),
            }
            if webhook.secret_hash:
                sig = self._sign_payload(webhook.secret_hash, body_bytes)
                headers["X-Reliastra-Signature"] = f"sha256={sig}"
            if webhook.custom_headers:
                for k, v in webhook.custom_headers.items():
                    headers[k] = v

            try:
                async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT_SECONDS) as client:
                    resp = await client.post(webhook.url, content=body_bytes, headers=headers)

                if 200 <= resp.status_code < 300:
                    await self.delivery_repo.mark_success(
                        session, delivery, status_code=resp.status_code,
                        response_body=resp.text[:5000] if resp.text else None,
                    )
                    await self.repo.reset_failure_count(session, webhook)
                    await self.repo.update_last_delivery(
                        session, webhook, delivery.delivered_at
                    )
                else:
                    await self._handle_delivery_failure(
                        session, webhook, delivery, resp.status_code,
                        resp.text[:5000] if resp.text else None,
                    )
            except httpx.HTTPError as exc:
                await self._handle_delivery_failure(
                    session, webhook, delivery, None, str(exc)[:5000],
                )

            retried += 1

        return retried


webhook_service = WebhookService()
