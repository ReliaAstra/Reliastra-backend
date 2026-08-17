"""Tests for FIX 1/FIX 4: the Redis ZSET check queue scheduler."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.infrastructure import scheduler


@pytest.mark.asyncio
async def test_enqueue_check_adds_scored_member(fake_redis):
    dep_id = str(uuid.uuid4())
    due_at = datetime.now(timezone.utc)
    ok = await scheduler.enqueue_check(dep_id, "us-east", due_at)
    assert ok is True
    members = await fake_redis.zrangebyscore(
        scheduler.CHECK_QUEUE_KEY, "-inf", "+inf", withscores=True
    )
    assert len(members) == 1
    member, score = members[0]
    assert json.loads(member) == {"d": dep_id, "r": "us-east"}
    assert score == pytest.approx(due_at.timestamp())


@pytest.mark.asyncio
async def test_pop_due_claims_atomically_and_only_due_entries(fake_redis):
    now = datetime.now(timezone.utc)
    due_dep = str(uuid.uuid4())
    future_dep = str(uuid.uuid4())
    await scheduler.enqueue_check(due_dep, "us-east", now - timedelta(seconds=5))
    await scheduler.enqueue_check(future_dep, "eu-west", now + timedelta(seconds=60))

    claimed = await scheduler.pop_due_checks(now=now)
    assert claimed == [(due_dep, "us-east")]

    # The future entry must still be in the queue; the claimed one must not.
    remaining = await fake_redis.zrange(scheduler.CHECK_QUEUE_KEY, 0, -1)
    assert json.loads(remaining[0]) == {"d": future_dep, "r": "eu-west"}


@pytest.mark.asyncio
async def test_pop_due_single_claim_between_instances(fake_redis):
    """Two schedulers popping concurrently must not double-dispatch."""
    dep_id = str(uuid.uuid4())
    await scheduler.enqueue_check(
        dep_id, "us-east", datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    first = await scheduler.pop_due_checks()
    second = await scheduler.pop_due_checks()
    assert first == [(dep_id, "us-east")]
    assert second == []


@pytest.mark.asyncio
async def test_scan_due_dependencies_enqueues_and_limits(db_session):
    """FIX 4/FIX 25: scan reads due deps (bounded) and enqueues only."""
    from app.modules.dependencies.repository import DependencyRepository
    from app.modules.organizations.repository import OrganizationRepository
    from app.modules.users.repository import UserRepository
    from app.core.security import get_password_hash

    user = await UserRepository.create(
        db_session,
        email="sched@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Sched User",
    )
    org = await OrganizationRepository.create(
        db_session, name="Sched Org", slug=f"org-{uuid.uuid4().hex[:8]}", plan="free"
    )
    await OrganizationRepository.add_member(
        db_session, org_id=org.id, user_id=user.id, role="owner"
    )
    dep = await DependencyRepository.create(
        db_session,
        org_id=org.id,
        application_id=None,
        name="due-dep",
        endpoint_url="https://example.com/health",
        method="GET",
        headers=None,
        expected_status_codes=[200],
        timeout_seconds=10,
        check_interval_seconds=300,
        regions=["us-east", "eu-west"],
    )
    dep.next_check_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    db_session.add(dep)
    await db_session.commit()

    enqueued = await scheduler.scan_due_dependencies()
    assert enqueued == 2  # two regions

    # next_check_at must NOT be changed by the scan (advance happens after
    # dispatch only — FIX 1).
    await db_session.refresh(dep)
    assert dep.next_check_at < datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_advance_next_check_at_updates_after_enqueue(db_session):
    """FIX 1: next_check_at advances in a separate, fast transaction."""
    from app.modules.dependencies.repository import DependencyRepository
    from app.modules.organizations.repository import OrganizationRepository
    from app.modules.users.repository import UserRepository
    from app.core.security import get_password_hash

    user = await UserRepository.create(
        db_session,
        email="sched2@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Sched User 2",
    )
    org = await OrganizationRepository.create(
        db_session, name="Sched Org 2", slug=f"org-{uuid.uuid4().hex[:8]}", plan="free"
    )
    await OrganizationRepository.add_member(
        db_session, org_id=org.id, user_id=user.id, role="owner"
    )
    dep = await DependencyRepository.create(
        db_session,
        org_id=org.id,
        application_id=None,
        name="advance-dep",
        endpoint_url="https://example.com/health",
        method="GET",
        headers=None,
        expected_status_codes=[200],
        timeout_seconds=10,
        check_interval_seconds=120,
        regions=["us-east"],
    )
    await db_session.commit()

    await scheduler._advance_next_check_at([str(dep.id)])

    await db_session.refresh(dep)
    expected_min = datetime.now(timezone.utc) + timedelta(seconds=115)
    assert dep.next_check_at >= expected_min


@pytest.mark.asyncio
async def test_dispatch_due_checks_fires_celery_task_and_advances(db_session, fake_redis, monkeypatch):
    """End-to-end dispatch: pop → execute_check.delay → advance next_check_at."""
    from app.modules.dependencies.repository import DependencyRepository
    from app.modules.organizations.repository import OrganizationRepository
    from app.modules.users.repository import UserRepository
    from app.core.security import get_password_hash

    user = await UserRepository.create(
        db_session,
        email="sched3@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Sched User 3",
    )
    org = await OrganizationRepository.create(
        db_session, name="Sched Org 3", slug=f"org-{uuid.uuid4().hex[:8]}", plan="free"
    )
    await OrganizationRepository.add_member(
        db_session, org_id=org.id, user_id=user.id, role="owner"
    )
    dep = await DependencyRepository.create(
        db_session,
        org_id=org.id,
        application_id=None,
        name="dispatch-dep",
        endpoint_url="https://example.com/health",
        method="GET",
        headers=None,
        expected_status_codes=[200],
        timeout_seconds=10,
        check_interval_seconds=60,
        regions=["us-east"],
    )
    await db_session.commit()

    await scheduler.enqueue_check(
        str(dep.id), "us-east", datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    dispatched = []

    class FakeTask:
        def delay(self, dependency_id, region):
            dispatched.append((dependency_id, region))

    async def should_dispatch_true(*args, **kwargs):
        return True

    monkeypatch.setattr(
        "app.modules.checks.tasks.execute_check", FakeTask()
    )
    monkeypatch.setattr(
        "app.core.circuit_breaker.circuit_breaker.should_dispatch",
        should_dispatch_true,
    )

    count = await scheduler.dispatch_due_checks()
    assert count == 1
    assert dispatched == [(str(dep.id), "us-east")]

    await db_session.refresh(dep)
    assert dep.next_check_at >= datetime.now(timezone.utc) + timedelta(seconds=55)


@pytest.mark.asyncio
async def test_dispatch_skipped_when_circuit_open(db_session, fake_redis, monkeypatch):
    """FIX 8 integration: open circuits are not dispatched."""
    dep_id = str(uuid.uuid4())
    await scheduler.enqueue_check(
        dep_id, "us-east", datetime.now(timezone.utc) - timedelta(seconds=1)
    )

    dispatched = []

    class FakeTask:
        def delay(self, dependency_id, region):
            dispatched.append((dependency_id, region))

    async def should_dispatch_false(*args, **kwargs):
        return False

    monkeypatch.setattr("app.modules.checks.tasks.execute_check", FakeTask())
    monkeypatch.setattr(
        "app.core.circuit_breaker.circuit_breaker.should_dispatch",
        should_dispatch_false,
    )

    count = await scheduler.dispatch_due_checks()
    assert count == 0
    assert dispatched == []
