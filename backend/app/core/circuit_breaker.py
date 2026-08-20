"""Redis-backed circuit breaker for dependency checks.

Dead dependencies previously consumed worker capacity: every scheduled check
spent a full ``timeout_seconds`` waiting on an endpoint that never answers.
The breaker collapses that load:

* **closed**   — checks dispatch normally.
* **open**     — after ``FAILURE_THRESHOLD`` (3) consecutive failures, checks
  are no longer dispatched. A half-open probe is attempted at most once per
  ``HALF_OPEN_INTERVAL_SECONDS`` (60s).
* **half-open** — a probe succeeded; the breaker requires
  ``SUCCESS_THRESHOLD`` (2) consecutive successes before closing again.

State is a small JSON document per dependency under ``reliastra:circuit:<id>``.
The half-open probe uses a ``SETNX`` lease so multiple scheduler instances
never fire duplicate probes. Every operation fails open (dispatch is allowed)
when Redis is unavailable — a Redis outage must not silence all monitoring.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

FAILURE_THRESHOLD = 3
SUCCESS_THRESHOLD = 2
HALF_OPEN_INTERVAL_SECONDS = 60.0
PROBE_LEASE_SECONDS = 60

_STATE_KEY_PREFIX = "reliastra:circuit"
_PROBE_KEY_PREFIX = "reliastra:circuit:probe"


def _state_key(dependency_id: uuid.UUID | str) -> str:
    return f"{_STATE_KEY_PREFIX}:{dependency_id}"


def _probe_key(dependency_id: uuid.UUID | str) -> str:
    return f"{_PROBE_KEY_PREFIX}:{dependency_id}"


def _empty_state() -> dict[str, Any]:
    return {
        "state": "closed",
        "failures": 0,
        "successes": 0,
        "opened_at": None,
    }


class CircuitBreaker:
    """Dependency-scoped circuit breaker with Redis persistence."""

    def __init__(self, redis_client: Any | None = None) -> None:
        self._redis = redis_client

    def _client(self) -> Any:
        if self._redis is not None:
            return self._redis
        from app.infrastructure.redis_client import get_redis

        return get_redis()

    async def _load(self, dependency_id: uuid.UUID | str) -> dict[str, Any]:
        try:
            raw = await self._client().get(_state_key(dependency_id))
        except Exception:
            return _empty_state()
        if not raw:
            return _empty_state()
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return _empty_state()

    async def _save(self, dependency_id: uuid.UUID | str, state: dict[str, Any]) -> bool:
        try:
            await self._client().set(
                _state_key(dependency_id), json.dumps(state)
            )
            return True
        except Exception as exc:
            logger.debug("Circuit breaker state write failed: %s", exc)
            return False

    async def should_dispatch(self, dependency_id: uuid.UUID | str) -> bool:
        """Return True when a check for *dependency_id* may be dispatched.

        Open circuits only allow one half-open probe per
        ``HALF_OPEN_INTERVAL_SECONDS`` window (guarded by a Redis lease).
        Redis failures fail open.
        """
        try:
            state = await self._load(dependency_id)
        except Exception:
            return True  # fail open

        if state.get("state") != "open":
            return True

        opened_at = float(state.get("opened_at") or 0.0)
        if time.time() - opened_at < HALF_OPEN_INTERVAL_SECONDS:
            return False

        # Half-open probe: only one scheduler may fire the probe.
        try:
            acquired = await self._client().set(
                _probe_key(dependency_id),
                "1",
                nx=True,
                ex=PROBE_LEASE_SECONDS,
            )
            return bool(acquired)
        except Exception:
            return True  # fail open

    async def record_success(self, dependency_id: uuid.UUID | str) -> None:
        await self._record(dependency_id, success=True)

    async def record_failure(self, dependency_id: uuid.UUID | str) -> None:
        await self._record(dependency_id, success=False)

    async def _record(
        self, dependency_id: uuid.UUID | str, success: bool
    ) -> None:
        try:
            state = await self._load(dependency_id)
            if success:
                state["failures"] = 0
                state["successes"] = int(state.get("successes", 0)) + 1
                if state["successes"] >= SUCCESS_THRESHOLD:
                    state.update(
                        {
                            "state": "closed",
                            "successes": 0,
                            "opened_at": None,
                        }
                    )
                    try:
                        await self._client().delete(_probe_key(dependency_id))
                    except Exception:
                        pass
            else:
                state["successes"] = 0
                state["failures"] = int(state.get("failures", 0)) + 1
                if state["failures"] >= FAILURE_THRESHOLD:
                    state.update(
                        {
                            "state": "open",
                            "opened_at": time.time(),
                        }
                    )
            await self._save(dependency_id, state)
        except Exception as exc:
            logger.debug("Circuit breaker record failed: %s", exc)


circuit_breaker = CircuitBreaker()
