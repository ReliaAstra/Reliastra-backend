"""Redis pool factory."""

from __future__ import annotations

from typing import cast

from redis.asyncio import Redis


def create_redis(url: str) -> Redis:
    return cast(Redis, Redis.from_url(url, decode_responses=True, health_check_interval=30))
