from __future__ import annotations

import time
import logging
from fastapi import Request
from app.core.exceptions import RateLimitExceededException

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int = 60,
        key_prefix: str = "rate_limit",
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    async def is_redis_available(self) -> bool:
        """Check if Redis is reachable without raising."""
        try:
            from app.infrastructure.redis_client import get_redis
            redis = get_redis()
            await redis.ping()
            return True
        except Exception:
            return False

    async def check(self, identifier: str) -> bool:
        """
        Check and record request for identifier.
        Raises RateLimitExceededException if limit is exceeded.
        Returns True if within limit.
        When Redis is unavailable, the request is allowed through (fail-open)
        to prevent Redis outages from blocking all public and auth endpoints.
        """
        try:
            from app.infrastructure.redis_client import get_redis
            redis = get_redis()
            now = time.time()
            window_start = now - self.window_seconds
            key = f"{self.key_prefix}:{identifier}"

            pipeline = redis.pipeline()
            pipeline.zremrangebyscore(key, 0, window_start)
            pipeline.zcard(key)
            pipeline.zadd(key, {f"{now}:{time.time_ns()}": now})
            pipeline.expire(key, self.window_seconds * 2)
            results = await pipeline.execute()

            current_count = results[1]
            if current_count >= self.limit:
                raise RateLimitExceededException(
                    message=f"Rate limit exceeded ({self.limit} req / {self.window_seconds}s)"
                )
            return True
        except RateLimitExceededException:
            raise
        except Exception as exc:
            # Fail-open: allow the request when Redis is unavailable.
            # This prevents a Redis outage from blocking all rate-limited
            # endpoints (auth, public vendors, etc.). Log for alerting.
            logger.warning(
                "Rate limiter unavailable (Redis error), allowing request through: %s",
                exc,
            )
            return True


# Pre-configured rate limiters
api_key_limiter = SlidingWindowRateLimiter(limit=1000, window_seconds=60, key_prefix="rl_apikey")
ip_limiter = SlidingWindowRateLimiter(limit=100, window_seconds=60, key_prefix="rl_ip")
public_vendor_limiter = SlidingWindowRateLimiter(limit=60, window_seconds=60, key_prefix="rl_vendor")


async def enforce_rate_limit(request: Request, limiter: SlidingWindowRateLimiter, identifier: str | None = None) -> None:
    if identifier is None:
        client = request.client
        identifier = client.host if client else "unknown_ip"
    await limiter.check(identifier)
