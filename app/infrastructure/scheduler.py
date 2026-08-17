"""Reliastra check scheduler — a Redis ZSET-backed dispatch queue.

Replaces the old Celery Beat ``schedule_checks`` task (and the in-process
APScheduler clone) with a single lightweight async loop:

1. Every ``SCAN_INTERVAL_SECONDS`` (30s) the scheduler reads due dependencies
   from PostgreSQL (LIMIT 500, no HTTP, no long transaction) and adds an entry
   ``(next_check_timestamp, dependency_id, region)`` to the Redis sorted set
   ``reliastra:check_queue``.
2. Every ``POLL_INTERVAL_SECONDS`` (5s) it pops entries whose score is due and
   fires ``execute_check.delay(dependency_id, region)`` — Celery workers do
   the actual HTTP probe in their own transaction.
3. Only **after** a successful enqueue is ``dependencies.next_check_at``
   advanced, in a separate, fast single-statement transaction.

Claiming uses ``ZRANGEBYSCORE`` + ``ZREM`` (the ``ZREM`` return value is the
atomic claim), so any number of scheduler replicas can run without double
dispatch. The scheduler is deliberately runnable standalone:

    python -m app.infrastructure.scheduler

The FastAPI lifespan no longer starts it (it must not duplicate the worker
fleet), which is why docker-compose/Procfile run it as its own process.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

CHECK_QUEUE_KEY = "reliastra:check_queue"
POLL_INTERVAL_SECONDS = 5.0
SCAN_INTERVAL_SECONDS = 30.0
SCAN_BATCH_LIMIT = 500
DISPATCH_BATCH_LIMIT = 100
REDISPATCH_DELAY_SECONDS = 30.0

_scheduler_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None


def _member(dependency_id: str, region: str) -> str:
    return json.dumps({"d": str(dependency_id), "r": region})


def _parse_member(member: str) -> tuple[str, str] | None:
    try:
        data = json.loads(member)
        return str(data["d"]), str(data["r"])
    except (TypeError, KeyError, ValueError):
        logger.warning("Ignoring malformed check_queue member: %s", member)
        return None


async def enqueue_check(
    dependency_id: str, region: str, due_at: datetime
) -> bool:
    """Add a (dependency, region) pair to the Redis check queue.

    The sorted-set member is keyed only by (dependency, region), so
    re-enqueueing the same pair updates its score instead of duplicating it.
    """
    try:
        from app.infrastructure.redis_client import get_redis

        redis = get_redis()
        score = due_at.timestamp()
        await redis.zadd(CHECK_QUEUE_KEY, {_member(dependency_id, region): score})
        return True
    except Exception as exc:
        logger.warning("enqueue_check failed dep=%s region=%s: %s", dependency_id, region, exc)
        return False


async def pop_due_checks(
    now: datetime | None = None, limit: int = DISPATCH_BATCH_LIMIT
) -> list[tuple[str, str]]:
    """Atomically claim up to *limit* due (dependency, region) pairs.

    Returns [] when Redis is unavailable (the scan will re-add entries).
    """
    try:
        from app.infrastructure.redis_client import get_redis

        redis = get_redis()
        now_ts = (now or datetime.now(timezone.utc)).timestamp()
        members = await redis.zrangebyscore(
            CHECK_QUEUE_KEY, "-inf", now_ts, start=0, num=limit
        )
        claimed: list[tuple[str, str]] = []
        for member in members:
            removed = await redis.zrem(CHECK_QUEUE_KEY, member)
            if removed:  # we won the claim — no other instance will fire it
                parsed = _parse_member(member)
                if parsed:
                    claimed.append(parsed)
        return claimed
    except Exception as exc:
        logger.warning("pop_due_checks failed: %s", exc)
        return []


async def scan_due_dependencies(limit: int = SCAN_BATCH_LIMIT) -> int:
    """Read due dependencies from PostgreSQL and enqueue them into Redis.

    Purely a read + enqueue operation: no HTTP, no row updates, no long
    transaction. Returns the number of (dependency, region) pairs enqueued.
    """
    from app.db.session import get_session_maker
    from app.modules.dependencies.repository import DependencyRepository

    enqueued = 0
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            due_deps = await DependencyRepository.get_due_dependencies(
                session, limit=limit
            )
        except Exception:
            logger.exception("scan_due_dependencies failed to read due deps")
            return 0

        for dep in due_deps:
            regions = dep.regions or ["us-east", "eu-west"]
            due_at = dep.next_check_at or datetime.now(timezone.utc)
            for region in regions:
                if await enqueue_check(str(dep.id), region, due_at):
                    enqueued += 1
    if enqueued:
        logger.info("Scheduler: enqueued %s checks", enqueued)
    return enqueued


async def _advance_next_check_at(dependency_ids: list[str]) -> None:
    """Advance ``next_check_at`` for successfully-enqueued dependencies.

    Runs in its own short transaction — a single UPDATE statement that adds
    each dependency's own interval, filtered to still-active rows.
    """
    if not dependency_ids:
        return
    from app.db.session import get_session_maker

    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            stmt = text(
                """
                UPDATE dependencies
                SET next_check_at = now() + make_interval(secs => check_interval_seconds)
                WHERE id = ANY(:ids)
                  AND is_active = TRUE
                  AND is_deleted = FALSE
                """
            ).bindparams(ids=dependency_ids)
            await session.execute(stmt)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Failed to advance next_check_at for %s deps", len(dependency_ids))


async def dispatch_due_checks(
    now: datetime | None = None, limit: int = DISPATCH_BATCH_LIMIT
) -> int:
    """Fire due checks into Celery and advance their schedules.

    Returns the number of checks dispatched.
    """
    from app.core.circuit_breaker import circuit_breaker
    from app.modules.checks.tasks import execute_check

    due = await pop_due_checks(now=now, limit=limit)
    dispatched_ids: list[str] = []
    dispatched = 0
    for dependency_id, region in due:
        try:
            allowed = await circuit_breaker.should_dispatch(dependency_id)
            if not allowed:
                logger.info(
                    "Circuit open for dependency %s — skipping dispatch (region=%s)",
                    dependency_id,
                    region,
                )
                continue
            execute_check.delay(dependency_id, region)
            dispatched += 1
            if dependency_id not in dispatched_ids:
                dispatched_ids.append(dependency_id)
        except Exception as exc:
            logger.warning(
                "Failed to dispatch check dep=%s region=%s: %s — requeueing",
                dependency_id,
                region,
                exc,
            )
            requeue_at = datetime.now(timezone.utc).timestamp() + REDISPATCH_DELAY_SECONDS
            try:
                from app.infrastructure.redis_client import get_redis

                await get_redis().zadd(
                    CHECK_QUEUE_KEY,
                    {_member(dependency_id, region): requeue_at},
                )
            except Exception:
                pass  # next scan will re-enqueue it anyway

    if dispatched:
        logger.info("Scheduler: dispatched %s checks", dispatched)
    await _advance_next_check_at(dispatched_ids)
    return dispatched


async def _tick(now: datetime | None = None) -> None:
    """One scheduler tick: dispatch due entries from the ZSET queue."""
    current = now or datetime.now(timezone.utc)
    try:
        await dispatch_due_checks(now=current)
    except Exception:
        logger.exception("dispatch_due_checks failed")


async def run_scheduler(stop_event: asyncio.Event | None = None) -> None:
    """Run the scheduler loop until *stop_event* is set.

    * Every 5s (``POLL_INTERVAL_SECONDS``): pop due entries from the Redis
      ZSET and fire ``execute_check.delay(...)``.
    * Every 30s (``SCAN_INTERVAL_SECONDS``): scan PostgreSQL for newly due
      dependencies and refill the queue.
    """
    logger.info(
        "Check queue scheduler started (poll=%ss scan=%ss queue=%s)",
        POLL_INTERVAL_SECONDS,
        SCAN_INTERVAL_SECONDS,
        CHECK_QUEUE_KEY,
    )
    stop = stop_event or asyncio.Event()
    ticks = 0
    while not stop.is_set():
        await _tick()
        ticks += 1
        if ticks % 6 == 0:
            # Scan the DB roughly every SCAN_INTERVAL_SECONDS (6 ticks x 5s).
            try:
                await scan_due_dependencies()
            except Exception:
                logger.exception("scan_due_dependencies failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


def start_scheduler() -> asyncio.Task | None:
    """Start the scheduler as a background task on the running event loop.

    Used by tests and process entrypoints. The FastAPI lifespan deliberately
    does NOT call this (see module docstring).
    """
    global _scheduler_task, _stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("Scheduler already running, skipping start")
        return _scheduler_task
    _stop_event = asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("start_scheduler() requires a running event loop")
        return None
    _scheduler_task = loop.create_task(run_scheduler(_stop_event))
    return _scheduler_task


def stop_scheduler() -> None:
    """Stop the background scheduler task, if any."""
    global _scheduler_task, _stop_event
    if _scheduler_task is None:
        return
    if _stop_event is not None:
        _stop_event.set()
    _scheduler_task = None
    _stop_event = None


def main() -> None:
    """Standalone entrypoint: ``python -m app.infrastructure.scheduler``."""
    try:
        asyncio.run(run_scheduler())
    except KeyboardInterrupt:
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
