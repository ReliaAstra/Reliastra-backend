"""Tests for FIX 5: automated check_results partition management."""

from datetime import datetime, timezone

import pytest

from app.modules.checks import partition_manager
from app.modules.checks.partition_manager import (
    create_partition_ddl,
    ensure_partitions,
    months_ahead,
    partition_name_for,
)


def test_months_ahead_generates_12_consecutive_months():
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    months = months_ahead(now, 12)
    assert len(months) == 12
    assert months[0] == datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert months[1] == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert months[2] == datetime(2027, 1, 1, tzinfo=timezone.utc)
    assert months[-1] == datetime(2027, 10, 1, tzinfo=timezone.utc)


def test_create_partition_ddl():
    month = datetime(2026, 8, 20, tzinfo=timezone.utc)
    ddl = create_partition_ddl(month)
    assert "CREATE TABLE IF NOT EXISTS check_results_2026_08" in ddl
    assert "PARTITION OF check_results" in ddl
    assert "FOR VALUES FROM ('2026-08-01" in ddl
    assert "TO ('2026-09-01" in ddl


def test_partition_name():
    assert (
        partition_name_for(datetime(2026, 8, 3, tzinfo=timezone.utc))
        == "check_results_2026_08"
    )


@pytest.mark.asyncio
async def test_ensure_partitions_creates_tables(db_session):
    created = await ensure_partitions(db_session, months_ahead_count=3)
    assert len(created) == 3

    from sqlalchemy import text

    rows = await db_session.execute(
        text(
            "SELECT relname FROM pg_class "
            "WHERE relname LIKE 'check_results_%' AND relkind = 'r'"
        )
    )
    names = {row[0] for row in rows}
    assert created[0] in names
    assert created[1] in names
    assert created[2] in names


@pytest.mark.asyncio
async def test_ensure_partitions_is_idempotent(db_session):
    first = await ensure_partitions(db_session, months_ahead_count=2)
    second = await ensure_partitions(db_session, months_ahead_count=2)
    assert first == second
