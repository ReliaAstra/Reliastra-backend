"""Automated partition management for ``check_results``.

``check_results`` is declared ``PARTITION BY RANGE (executed_at)``. The initial
migration only creates a DEFAULT partition, so every row older than any real
partition lands there and pruning/query performance degrades over time. This
module creates monthly partitions for the next ``MONTHS_AHEAD`` months and is
invoked:

* once by Alembic migration ``0012_production_hardening``, and
* monthly by the Celery beat task ``ensure_check_result_partitions``
  (``app/modules/checks/tasks.py``).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PARENT_TABLE = "check_results"
OBSERVATIONS_PARENT_TABLE = "observations"
MONTHS_AHEAD = 12


def _month_bounds(month: datetime) -> tuple[datetime, datetime]:
    """First instant of *month* and first instant of the following month."""
    start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def partition_name_for(month: datetime) -> str:
    return f"{PARENT_TABLE}_{month:%Y_%m}"


def create_partition_ddl(month: datetime) -> str:
    start, end = _month_bounds(month)
    name = partition_name_for(month)
    return (
        f"CREATE TABLE IF NOT EXISTS {name} "
        f"PARTITION OF {PARENT_TABLE} "
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
    )


def drop_partition_ddl(month: datetime) -> str:
    return f"DROP TABLE IF EXISTS {partition_name_for(month)}"


def months_ahead(now: datetime, count: int = MONTHS_AHEAD) -> list[datetime]:
    """The first day of the current month plus the next *count* months."""
    months: list[datetime] = []
    year, month = now.year, now.month
    for _ in range(count):
        months.append(datetime(year, month, 1, tzinfo=now.tzinfo))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


async def ensure_partitions(
    session: AsyncSession,
    months_ahead_count: int = MONTHS_AHEAD,
) -> list[str]:
    """Create the monthly partitions for the next *months_ahead_count* months.

    Returns the names of the partitions created or already present.
    """
    now = datetime.now(timezone.utc)
    names: list[str] = []
    for month in months_ahead(now, months_ahead_count):
        ddl = create_partition_ddl(month)
        try:
            await session.execute(text(ddl))
            names.append(partition_name_for(month))
        except Exception:
            logger.exception("Failed to create partition for %s", month)
            raise
    await session.commit()
    logger.info("Ensured %s check_results monthly partitions", len(names))
    return names


# ── Observations partition management ─────────────────────────────────


def observation_partition_name_for(month: datetime) -> str:
    """Return the partition table name for *month*."""
    return f"{OBSERVATIONS_PARENT_TABLE}_{month:%Y_%m}"


def create_observation_partition_ddl(month: datetime) -> str:
    """Return a ``CREATE TABLE ... PARTITION OF observations`` statement."""
    start, end = _month_bounds(month)
    name = observation_partition_name_for(month)
    return (
        f"CREATE TABLE IF NOT EXISTS {name} "
        f"PARTITION OF {OBSERVATIONS_PARENT_TABLE} "
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
    )


def drop_observation_partition_ddl(month: datetime) -> str:
    """Return a ``DROP TABLE`` statement for a single observation partition."""
    return f"DROP TABLE IF EXISTS {observation_partition_name_for(month)}"


async def ensure_observation_partitions(
    session: AsyncSession,
    months_ahead_count: int = MONTHS_AHEAD,
) -> list[str]:
    """Create observation monthly partitions for the next *months_ahead_count* months.

    Observations are partitioned by ``RANGE (timestamp)`` (defined in
    migration ``0003_add_observations.py``), but only a DEFAULT partition
    exists.  This function creates the real monthly partitions that enable
    partition pruning and fast ``DROP PARTITION``-based retention.

    Should be run monthly (via ``ensure_check_result_partitions`` beat task).
    """
    now = datetime.now(timezone.utc)
    names: list[str] = []
    for month in months_ahead(now, months_ahead_count):
        ddl = create_observation_partition_ddl(month)
        try:
            await session.execute(text(ddl))
            names.append(observation_partition_name_for(month))
        except Exception:
            logger.exception("Failed to create observation partition for %s", month)
            raise
    await session.commit()
    logger.info("Ensured %s observations monthly partitions", len(names))
    return names
