"""Cached public vendor status service."""

from __future__ import annotations

import builtins
import json
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from redis.asyncio import Redis

from app.core.exceptions import NotFoundError
from app.modules.vendors.constants import PUBLIC_VENDOR_CACHE_TTL_SECONDS
from app.modules.vendors.repository import VendorRepository
from app.modules.vendors.schemas import VendorHistoryResponse, VendorResponse


class VendorService:
    def __init__(self, repository: VendorRepository, redis: Redis) -> None:
        self.repository = repository
        self.redis = redis

    async def list(self) -> list[VendorResponse]:
        key = "public:vendors:list"
        cached = await self._cached(key)
        if cached:
            return [VendorResponse.model_validate(item) for item in cached]
        result = [
            VendorResponse.model_validate(item) for item in await self.repository.list_public()
        ]
        await self._store(key, [item.model_dump(mode="json") for item in result])
        return result

    async def get(self, vendor_name: str) -> VendorResponse:
        model = await self.repository.get_public(vendor_name)
        if model is None:
            raise NotFoundError("Public vendor not found")
        return VendorResponse.model_validate(model)

    async def history(self, vendor_name: str) -> VendorHistoryResponse:
        await self.get(vendor_name)
        now = datetime.now(UTC)
        try:
            raw = await cast(
                Awaitable[builtins.list[str]],
                self.redis.lrange(f"public:vendors:{vendor_name}:history", 0, 999),
            )
        except Exception:
            raw = []
        points = [json.loads(item) for item in raw]
        up = sum(item["is_up"] for item in points)
        return VendorHistoryResponse(
            vendor_name=vendor_name,
            from_time=now - timedelta(hours=24),
            to_time=now,
            uptime_percent=(up / len(points) * 100 if points else 0),
            points=points,
        )

    async def _cached(self, key: str) -> builtins.list[dict[str, Any]] | None:
        try:
            value = await self.redis.get(key)
            return cast(builtins.list[dict[str, Any]], json.loads(value)) if value else None
        except Exception:
            return None

    async def _store(self, key: str, value: object) -> None:
        try:
            await self.redis.set(key, json.dumps(value), ex=PUBLIC_VENDOR_CACHE_TTL_SECONDS)
        except Exception:
            return
