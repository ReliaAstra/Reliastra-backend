"""Tests for FIX 9: observation transactional outbox."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, text

from app.modules.checks.models import CheckResult
from app.modules.checks.service import CheckService
from app.modules.observations.models import OutboxEvent, Observation
from app.modules.observations.outbox import process_outbox_batch


async def _make_org(db_session):
    """Observations.org_id has a FK to organizations — create a real org."""
    from app.modules.organizations.repository import OrganizationRepository

    org = await OrganizationRepository.create(
        db_session,
        name="Outbox Org",
        slug=f"org-{uuid.uuid4().hex[:8]}",
        plan="free",
    )
    await db_session.commit()
    return org


def _fake_check_result(org_id: uuid.UUID | None = None) -> MagicMock:
    return MagicMock(
        id=uuid.uuid4(),
        dependency_id=uuid.uuid4(),
        org_id=org_id or uuid.uuid4(),
        region="us-east",
        executed_at=datetime.now(timezone.utc),
        latency_ms=42.0,
        status_code=200,
        is_up=True,
        error_message=None,
        quorum_confirmed=False,
    )


@pytest.mark.asyncio
async def test_check_service_writes_outbox_instead_of_direct_observation(db_session):
    """The check path must write an OutboxEvent, not call observation service."""
    service = CheckService()
    org = await _make_org(db_session)
    result = _fake_check_result(org_id=org.id)
    with patch(
        "app.modules.observations.service.observation_service.record_observation",
        new=AsyncMock(),
    ) as record_mock:
        await service._enqueue_observation_outbox(
            db_session, result, "https://example.com/health", "GET"
        )
    record_mock.assert_not_awaited()

    events = (
        await db_session.execute(select(OutboxEvent))
    ).scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "observation_created"
    payload = json.loads(events[0].payload)
    assert payload["source_type"] == "customer_check"
    assert payload["region"] == "us-east"
    assert payload["latency_ms"] == 42.0


@pytest.mark.asyncio
async def test_outbox_processor_records_observation_and_deletes_event(db_session):
    service = CheckService()
    org = await _make_org(db_session)
    result = _fake_check_result(org_id=org.id)
    await service._enqueue_observation_outbox(
        db_session, result, "https://example.com/health", "GET"
    )
    await db_session.commit()

    processed = await process_outbox_batch(db_session)
    assert processed == 1
    await db_session.commit()

    observations = (
        await db_session.execute(select(Observation))
    ).scalars().all()
    assert len(observations) == 1
    assert observations[0].source_id == result.dependency_id

    remaining = (
        await db_session.execute(select(OutboxEvent))
    ).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_outbox_processor_retries_failed_events(db_session):
    """A failing observation write leaves the event pending (at-least-once)."""
    service = CheckService()
    org = await _make_org(db_session)
    result = _fake_check_result(org_id=org.id)
    await service._enqueue_observation_outbox(
        db_session, result, "https://example.com/health", "GET"
    )
    await db_session.commit()

    with patch(
        "app.modules.observations.outbox.observation_service.record_observation",
        side_effect=RuntimeError("db exploded"),
    ):
        processed = await process_outbox_batch(db_session)
    assert processed == 0
    await db_session.rollback()

    remaining = (
        await db_session.execute(select(OutboxEvent))
    ).scalars().all()
    assert len(remaining) == 1


@pytest.mark.asyncio
async def test_outbox_processor_skips_unknown_event_types(db_session):
    event = OutboxEvent(
        event_type="mystery_event",
        payload="{}",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(event)
    await db_session.commit()

    processed = await process_outbox_batch(db_session)
    assert processed == 0
    await db_session.commit()

    remaining = (
        await db_session.execute(select(OutboxEvent))
    ).scalars().all()
    assert remaining == []
