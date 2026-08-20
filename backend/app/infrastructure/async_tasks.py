"""Shared helpers for running async coroutines from synchronous Celery tasks.

Celery 5.x tasks are synchronous while the service layer is async
(SQLAlchemy async). The bridge must respect one hard constraint: asyncpg
connections are bound to the event loop that created them, and the engine
connection pool outlives individual tasks. Creating a fresh loop per task
(e.g. ``asyncio.run`` per call) therefore breaks on the *second* task that
reuses a pooled connection.

This module guarantees loop affinity in both execution contexts:

* **No running loop** (normal Celery prefork worker): every task runs on ONE
  process-cached event loop. One loop per process, so pooled connections
  never cross loops and memory stays flat.

* **A loop is already running** (eager task execution in tests/dev): all
  coroutines are handed to a single dedicated worker thread that owns one
  long-lived loop AND its own SQLAlchemy engine. The worker's engine is
  separate from the caller's, so its pooled connections are created on the
  worker's loop and never collide with the caller's loop.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Process-cached loop for the "no running loop" (Celery worker) context.
_process_loop: asyncio.AbstractEventLoop | None = None
_process_loop_lock = threading.Lock()

# Single worker thread (with its own loop + engine) for in-loop callers.
_worker: "_LoopWorker | None" = None
_worker_lock = threading.Lock()


class _LoopWorker:
    """One background thread owning one loop and one DB engine forever."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session_maker: Any = None
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, name="reliastra-async-worker", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=10)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        # The worker owns its engine so asyncpg connections are always
        # created (and reused) on THIS loop.
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

        from app.db.session import build_engine

        self._session_maker = async_sessionmaker(
            build_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        self._ready.set()
        loop.run_forever()

    def run(self, coro: Any) -> Any:
        if self._loop is None:
            raise RuntimeError("async worker loop failed to start")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def run_with_session(self, coro_factory: Any) -> Any:
        """Run ``await coro_factory(session)`` inside a worker-owned session.

        The coroutine is created on the worker's loop so the loop-bound
        asyncpg pool of the worker engine is used consistently.
        """
        if self._loop is None:
            raise RuntimeError("async worker loop failed to start")

        async def _run() -> Any:
            async with self._session_maker() as session:
                coro = coro_factory(session)
                try:
                    result = await coro
                    await session.commit()
                    return result
                except Exception:
                    await session.rollback()
                    raise

        future = asyncio.run_coroutine_threadsafe(_run(), self._loop)
        return future.result()


def _get_worker() -> _LoopWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = _LoopWorker()
        return _worker


def _get_process_loop() -> asyncio.AbstractEventLoop:
    """Return the process-cached event loop used by Celery tasks."""
    global _process_loop
    with _process_loop_lock:
        if _process_loop is None or _process_loop.is_closed():
            _process_loop = asyncio.new_event_loop()
        return _process_loop


def is_running_loop() -> bool:
    """True when called from inside a running event loop."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def run_async(coro: Any) -> Any:
    """Run *coro* to completion from synchronous code.

    * Outside a running loop → process-cached loop (Celery worker path).
    * Inside a running loop → shared single-thread loop worker (bounded
      memory; the caller is responsible for loop-affine resources).
    """
    if is_running_loop():
        return _get_worker().run(coro)
    return _get_process_loop().run_until_complete(coro)


def _run_managed_session(coro_factory: Any) -> Any:
    """Run ``coro_factory(session)`` with a self-managed session + commit."""

    async def _managed() -> Any:
        from app.db.session import get_session_maker

        session_maker = get_session_maker()
        async with session_maker() as session:
            coro = coro_factory(session)
            try:
                result = await coro
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    return _get_process_loop().run_until_complete(_managed())


def async_task_body(coro_factory: Any) -> Any:
    """Bridge helper for Celery task bodies.

    ``coro_factory`` is a sync callable ``(session) -> coroutine`` performing
    the task's work. Session lifecycle (commit/rollback) is handled here.

    * Inside a running loop (eager tests/dev): the body runs on the shared
      worker thread whose loop owns a dedicated engine — loop affinity for
      asyncpg connections is preserved.
    * Outside a loop (Celery workers): the body runs on the process-cached
      loop using the global engine.
    """
    if is_running_loop():
        return _get_worker().run_with_session(coro_factory)
    return _run_managed_session(coro_factory)
