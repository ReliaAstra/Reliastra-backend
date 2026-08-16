"""In-process APScheduler that replaces Celery beat + worker.

On ZeVCloud (single-container PaaS) there is no way to run separate
Celery worker/beat processes.  This module runs all periodic tasks
inside the same asyncio event-loop as uvicorn via APScheduler's
``AsyncIOScheduler``.  It is started/stopped from the FastAPI
``lifespan`` context-manager in ``app.main``.

Tasks are deliberately thin wrappers around the existing async service
layer — no business logic lives here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Scheduled task implementations (all native async, no Celery)
# ---------------------------------------------------------------------------


async def _schedule_checks_job() -> None:
    """Periodic job: find dependencies due for probing and execute checks."""
    from app.db.session import get_session_maker
    from app.modules.checks.service import check_service

    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            count = await check_service.schedule_due_checks(session)
            await session.commit()
            if count:
                logger.info("Scheduler: dispatched %s checks", count)
        except Exception:
            await session.rollback()
            logger.exception("Scheduler: schedule_checks_job failed")


async def _execute_check_job(dependency_id: str, region: str) -> None:
    """Execute a single probe for a dependency in a given region."""
    import uuid

    from app.db.session import get_session_maker
    from app.modules.checks.service import check_service

    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            result = await check_service.execute_check(
                session, uuid.UUID(dependency_id), region
            )
            await session.commit()
            if result:
                logger.info(
                    "Scheduler: check %s dep=%s region=%s up=%s",
                    result.id,
                    dependency_id,
                    region,
                    result.is_up,
                )
        except Exception:
            await session.rollback()
            logger.exception(
                "Scheduler: execute_check failed dep=%s region=%s",
                dependency_id,
                region,
            )


async def _retention_cleanup_job() -> None:
    """Monthly job: prune observations older than retention period."""
    from datetime import datetime, timedelta, timezone

    from app.db.session import get_session_maker
    from app.modules.observations.repository import ObservationRepository

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            deleted = await ObservationRepository.delete_before(session, cutoff)
            await session.commit()
            logger.info("Scheduler: removed %s expired observations", deleted)
        except Exception:
            await session.rollback()
            logger.exception("Scheduler: retention_cleanup failed")


async def _daily_aggregation_job() -> None:
    """Daily job: log observation volume for capacity reporting."""
    from datetime import datetime, timedelta, timezone

    from app.db.session import get_session_maker
    from app.modules.observations.repository import ObservationRepository

    now = datetime.now(timezone.utc)
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=1)
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            count = await ObservationRepository.count_between(session, start, end)
            logger.info("Scheduler: observation volume for %s: %s", start.date(), count)
        except Exception:
            logger.exception("Scheduler: daily_aggregation failed")


# ---------------------------------------------------------------------------
# Scheduler lifecycle (called from FastAPI lifespan)
# ---------------------------------------------------------------------------


def start_scheduler() -> None:
    """Create and start the APScheduler instance.

    This is called once during FastAPI startup.  It registers all
    periodic jobs that previously lived in ``celery_app.conf.beat_schedule``.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running, skipping start")
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")

    # schedule-checks-periodic  (was every 30s via Celery beat)
    _scheduler.add_job(
        _schedule_checks_job,
        trigger=IntervalTrigger(seconds=30),
        id="schedule-checks-periodic",
        name="Schedule due dependency checks",
        max_instances=1,
        misfire_grace_time=60,
        replace_existing=True,
    )

    # retention-cleanup-monthly  (was crontab day 1 @ 03:00)
    _scheduler.add_job(
        _retention_cleanup_job,
        trigger=IntervalTrigger(days=30),  # approximate; exact day-of-month needs cron trigger
        id="retention-cleanup-monthly",
        name="Remove expired observations",
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # aggregate-observation-daily  (was crontab @ 04:00)
    _scheduler.add_job(
        _daily_aggregation_job,
        trigger=IntervalTrigger(days=1),  # approximate; exact time needs cron trigger
        id="aggregate-observation-daily",
        name="Daily observation volume aggregation",
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )

    _scheduler.start()
    logger.info("In-process APScheduler started with %s jobs", len(_scheduler.get_jobs()))


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler

    if _scheduler is None:
        return

    if _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("In-process APScheduler stopped")

    _scheduler = None


def get_scheduler() -> AsyncIOScheduler | None:
    """Return the running scheduler instance (for diagnostics)."""
    return _scheduler
