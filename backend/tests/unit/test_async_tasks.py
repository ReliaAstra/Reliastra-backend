"""Tests for FIX 6: bounded run_async bridging sync Celery tasks to async."""

import asyncio
import threading

from app.infrastructure import async_tasks


def test_run_async_outside_loop():
    async def coro():
        return 42

    assert async_tasks.run_async(coro()) == 42


def test_run_async_inside_loop_uses_shared_worker():
    """Calls made from a running loop must reuse ONE worker thread/loop."""
    observed: list[tuple[int, int]] = []

    async def probe():
        observed.append(
            (threading.get_ident(), id(asyncio.get_running_loop()))
        )
        return "ok"

    async def main():
        # run_async is invoked SYNCHRONOUSLY while this loop is running,
        # which is exactly how eager Celery tasks execute inside tests/dev.
        first = async_tasks.run_async(probe())
        second = async_tasks.run_async(probe())
        return first, second

    first, second = asyncio.run(main())
    assert first == second == "ok"
    # Both probes ran on the same worker thread AND the same event loop —
    # no per-call thread/loop churn (the old ThreadPoolExecutor-per-call bug).
    assert len(observed) == 2
    assert observed[0] == observed[1]
    assert observed[0][0] != threading.get_ident()


def test_run_async_worker_thread_is_bounded():
    """The worker must be a single shared daemon thread."""
    worker = async_tasks._get_worker()
    again = async_tasks._get_worker()
    assert worker is again
    assert worker._thread.daemon is True
