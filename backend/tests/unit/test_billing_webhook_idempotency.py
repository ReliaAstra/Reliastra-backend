"""Tests for FIX 31: idempotent Paystack webhook processing."""

import hashlib
import hmac
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.modules.billing.service import BillingService

# Webhook HMAC verification needs a configured Paystack secret.
settings.PAYSTACK_SECRET_KEY = "sk_test_webhook_secret_for_tests"


def _signed_body(payload: dict, body: bytes) -> tuple[str, bytes]:
    sig = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"), body, hashlib.sha512
    ).hexdigest()
    return sig, body


def _payload(reference: str = "ref-123", event_id: int = 42) -> dict:
    return {
        "event": "charge.success",
        "data": {"reference": reference, "id": event_id, "status": "success"},
    }


@pytest.mark.asyncio
async def test_webhook_event_id_derivation():
    service = BillingService(repository=MagicMock())
    assert service._webhook_event_id(_payload()) == "charge.success:42"
    assert (
        service._webhook_event_id({"event": "x", "data": {}}) is None
    )


@pytest.mark.asyncio
async def test_charge_success_processed_only_once(fake_redis, monkeypatch):
    """The same event delivered twice must only be processed once."""
    import json

    payload = _payload()
    raw_body = json.dumps(payload).encode()
    signature, _ = _signed_body(payload, raw_body)

    repo = MagicMock()
    service = BillingService(repository=repo)
    service.verify_transaction = AsyncMock()

    # First delivery: processed.
    resp1 = await service.handle_webhook(
        MagicMock(), payload, signature=signature, raw_body=raw_body
    )
    assert resp1.received is True
    assert service.verify_transaction.await_count == 1

    # Retry delivery of the same event: skipped.
    resp2 = await service.handle_webhook(
        MagicMock(), payload, signature=signature, raw_body=raw_body
    )
    assert resp2.received is True
    assert service.verify_transaction.await_count == 1


@pytest.mark.asyncio
async def test_distinct_events_are_all_processed(fake_redis):
    import json

    repo = MagicMock()
    service = BillingService(repository=repo)
    service.verify_transaction = AsyncMock()

    for event_id in (1, 2):
        payload = _payload(reference=f"ref-{event_id}", event_id=event_id)
        raw_body = json.dumps(payload).encode()
        signature, _ = _signed_body(payload, raw_body)
        await service.handle_webhook(
            MagicMock(), payload, signature=signature, raw_body=raw_body
        )
    assert service.verify_transaction.await_count == 2


@pytest.mark.asyncio
async def test_missing_signature_still_rejected():
    from app.core.exceptions import UnauthorizedException

    service = BillingService(repository=MagicMock())
    with pytest.raises(UnauthorizedException):
        await service.handle_webhook(MagicMock(), _payload(), signature=None)
