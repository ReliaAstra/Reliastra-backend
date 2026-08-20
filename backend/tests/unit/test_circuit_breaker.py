"""Tests for FIX 8: the Redis-backed dependency circuit breaker."""

import json
import uuid

import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    FAILURE_THRESHOLD,
    HALF_OPEN_INTERVAL_SECONDS,
    SUCCESS_THRESHOLD,
)


@pytest.mark.asyncio
async def test_breaker_opens_after_consecutive_failures(fake_redis):
    dep_id = uuid.uuid4()
    breaker = CircuitBreaker(fake_redis)

    for _ in range(FAILURE_THRESHOLD - 1):
        assert await breaker.should_dispatch(dep_id) is True
        await breaker.record_failure(dep_id)

    # One more failure reaches the threshold → the breaker opens.
    await breaker.record_failure(dep_id)
    assert await breaker.should_dispatch(dep_id) is False

    state = json.loads(await fake_redis.get(f"reliastra:circuit:{dep_id}"))
    assert state["state"] == "open"


@pytest.mark.asyncio
async def test_breaker_half_open_probe_rate_limited(fake_redis):
    dep_id = uuid.uuid4()
    breaker = CircuitBreaker(fake_redis)

    for _ in range(FAILURE_THRESHOLD):
        await breaker.record_failure(dep_id)

    # First probe within the half-open interval must not dispatch.
    assert await breaker.should_dispatch(dep_id) is False

    # Simulate elapsed time by rewriting the opened_at timestamp.
    import time

    state = json.loads(await fake_redis.get(f"reliastra:circuit:{dep_id}"))
    state["opened_at"] = time.time() - HALF_OPEN_INTERVAL_SECONDS - 1
    await fake_redis.set(f"reliastra:circuit:{dep_id}", json.dumps(state))

    # A half-open probe is now allowed exactly once (SETNX lease).
    assert await breaker.should_dispatch(dep_id) is True
    assert await breaker.should_dispatch(dep_id) is False


@pytest.mark.asyncio
async def test_breaker_closes_after_successes(fake_redis):
    dep_id = uuid.uuid4()
    breaker = CircuitBreaker(fake_redis)

    for _ in range(FAILURE_THRESHOLD):
        await breaker.record_failure(dep_id)
    assert await breaker.should_dispatch(dep_id) is False

    # Half-open probe succeeds twice → closed again.
    for _ in range(SUCCESS_THRESHOLD - 1):
        await breaker.record_success(dep_id)
    state = json.loads(await fake_redis.get(f"reliastra:circuit:{dep_id}"))
    assert state["state"] == "open"  # not enough successes yet

    await breaker.record_success(dep_id)
    state = json.loads(await fake_redis.get(f"reliastra:circuit:{dep_id}"))
    assert state["state"] == "closed"
    assert await breaker.should_dispatch(dep_id) is True


@pytest.mark.asyncio
async def test_breaker_fails_open_when_redis_unavailable():
    class BrokenRedis:
        async def get(self, *a, **k):
            raise ConnectionError("down")

        async def set(self, *a, **k):
            raise ConnectionError("down")

        async def delete(self, *a, **k):
            raise ConnectionError("down")

    breaker = CircuitBreaker(BrokenRedis())
    assert await breaker.should_dispatch(uuid.uuid4()) is True
    # record_* must not raise.
    await breaker.record_success(uuid.uuid4())
    await breaker.record_failure(uuid.uuid4())
