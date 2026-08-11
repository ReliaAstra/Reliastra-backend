"""Redis-backed refresh-token allowlist and revocation repository."""

from __future__ import annotations

from redis.asyncio import Redis


class AuthRepository:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def allow_refresh(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        await self.redis.set(f"refresh:{jti}", user_id, ex=ttl_seconds)

    async def is_refresh_allowed(self, jti: str) -> bool:
        return bool(await self.redis.exists(f"refresh:{jti}"))

    async def revoke_refresh(self, jti: str) -> None:
        await self.redis.delete(f"refresh:{jti}")
