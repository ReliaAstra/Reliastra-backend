"""Tests for FIX 22 (bulk stats), FIX 25 (due-dependency LIMIT) and
FIX 37 (is_deleted filters on check result queries)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.checks.repository import CheckRepository
from app.modules.dependencies.repository import DependencyRepository
from app.modules.organizations.repository import OrganizationRepository
from app.modules.users.repository import UserRepository
from app.core.security import get_password_hash


async def _make_org_and_deps(db_session, count: int = 1):
    user = await UserRepository.create(
        db_session,
        email=f"repo-{uuid.uuid4().hex}@example.com",
        password_hash=get_password_hash("password123"),
        full_name="Repo User",
    )
    org = await OrganizationRepository.create(
        db_session, name="Repo Org", slug=f"org-{uuid.uuid4().hex[:8]}", plan="free"
    )
    await OrganizationRepository.add_member(
        db_session, org_id=org.id, user_id=user.id, role="owner"
    )
    deps = []
    for i in range(count):
        deps.append(
            await DependencyRepository.create(
                db_session,
                org_id=org.id,
                application_id=None,
                name=f"dep-{i}",
                endpoint_url=f"https://example.com/{i}",
                method="GET",
                headers=None,
                expected_status_codes=[200],
                timeout_seconds=10,
                check_interval_seconds=300,
                regions=["us-east"],
            )
        )
    await db_session.commit()
    return org, deps


@pytest.mark.asyncio
async def test_get_due_dependencies_is_bounded(db_session):
    """FIX 25: the due query must respect the LIMIT parameter."""
    org, deps = await _make_org_and_deps(db_session, count=3)
    for dep in deps:
        dep.next_check_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    await db_session.commit()

    due = await DependencyRepository.get_due_dependencies(db_session, limit=2)
    assert len(due) == 2

    all_due = await DependencyRepository.get_due_dependencies(db_session, limit=500)
    assert len(all_due) == 3


@pytest.mark.asyncio
async def test_check_queries_exclude_soft_deleted_dependencies(db_session):
    """FIX 37: results of soft-deleted deps must not appear."""
    org, deps = await _make_org_and_deps(db_session, count=1)
    dep = deps[0]
    await CheckRepository.create(
        db_session,
        dependency_id=dep.id,
        org_id=org.id,
        region="us-east",
        latency_ms=10.0,
        is_up=True,
    )
    await db_session.commit()

    before = await CheckRepository.list_recent_for_dependency(
        db_session, dep.id, window_seconds=3600
    )
    assert len(before) == 1

    await DependencyRepository.soft_delete(db_session, dep)
    await db_session.commit()

    after = await CheckRepository.list_recent_for_dependency(
        db_session, dep.id, window_seconds=3600
    )
    assert after == []

    org_results = await CheckRepository.list_for_org(db_session, org.id)
    assert org_results == []

    stats = await CheckRepository.get_aggregated_stats(db_session, dep.id)
    assert stats["total_checks"] == 0


@pytest.mark.asyncio
async def test_get_aggregated_stats_bulk_single_query(db_session):
    """FIX 22: bulk stats return per-dependency aggregates."""
    org, deps = await _make_org_and_deps(db_session, count=2)
    for dep in deps:
        await CheckRepository.create(
            db_session,
            dependency_id=dep.id,
            org_id=org.id,
            region="us-east",
            latency_ms=25.0,
            is_up=True,
        )
        await CheckRepository.create(
            db_session,
            dependency_id=dep.id,
            org_id=org.id,
            region="eu-west",
            latency_ms=55.0,
            is_up=False,
        )
    await db_session.commit()

    stats_map = await CheckRepository.get_aggregated_stats_bulk(
        db_session, [d.id for d in deps], window_hours=24
    )
    assert set(stats_map.keys()) == {d.id for d in deps}
    for dep in deps:
        stats = stats_map[dep.id]
        assert stats["total_checks"] == 2
        assert stats["total_up"] == 1
        assert stats["total_down"] == 1
        assert stats["uptime_percentage"] == 50.0


@pytest.mark.asyncio
async def test_get_aggregated_stats_bulk_empty_input(db_session):
    assert await CheckRepository.get_aggregated_stats_bulk(db_session, []) == {}
