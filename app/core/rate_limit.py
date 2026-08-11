"""Redis sliding-window rate limit and idempotency middleware."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import AsyncIterable, Awaitable, Callable
from typing import cast
from uuid import UUID

from fastapi import Request, Response
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.exceptions import error_body

logger = logging.getLogger(__name__)

_SLIDING_WINDOW = """
local key=KEYS[1]
local now=tonumber(ARGV[1])
local window=tonumber(ARGV[2])
local limit=tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now-window)
local count=redis.call('ZCARD', key)
if count >= limit then return 0 end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, window)
return 1
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path in {"/healthz", "/readyz", "/metrics", "/docs", "/openapi.json"}:
            return await call_next(request)
        redis: Redis = request.app.state.redis
        authorization = request.headers.get("authorization", "")
        is_api_key = authorization.startswith("ApiKey ")
        is_public = request.url.path.startswith("/v1/public/")
        limit = 1000 if is_api_key else (60 if is_public else 100)
        identity = (
            authorization if is_api_key else (request.client.host if request.client else "unknown")
        )
        digest = hashlib.sha256(identity.encode()).hexdigest()
        now_ms = int(time.time() * 1000)
        try:
            allowed = await cast(
                Awaitable[int],
                redis.eval(
                    _SLIDING_WINDOW,
                    1,
                    f"rate:{digest}",
                    str(now_ms),
                    "60000",
                    str(limit),
                    f"{now_ms}:{id(request)}",
                ),
            )
        except Exception:
            logger.warning("Rate limiter unavailable; failing open", exc_info=True)
            return await call_next(request)
        if not allowed:
            return JSONResponse(
                error_body("RATE_LIMITED", "Request rate limit exceeded"), status_code=429
            )
        return await call_next(request)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        key = request.headers.get("idempotency-key")
        if request.method != "POST" or not key:
            return await call_next(request)
        try:
            UUID(key)
        except ValueError:
            return JSONResponse(
                error_body("VALIDATION_ERROR", "Idempotency-Key must be a UUID"),
                status_code=422,
            )
        scope = hashlib.sha256(
            request.headers.get("authorization", "anonymous").encode()
        ).hexdigest()
        cache_key = f"idempotency:{scope}:{request.url.path}:{key}"
        redis: Redis = request.app.state.redis
        try:
            cached = await cast(Awaitable[str | None], redis.get(cache_key))
            if cached:
                value = json.loads(cached)
                return Response(
                    content=value["body"],
                    status_code=value["status"],
                    media_type=value.get("media_type"),
                    headers={"Idempotency-Replayed": "true"},
                )
        except Exception:
            logger.warning("Idempotency cache unavailable; continuing", exc_info=True)
            return await call_next(request)
        response = await call_next(request)
        iterator = getattr(response, "body_iterator", None)
        if iterator is None:
            return response
        body = b"".join([chunk async for chunk in cast(AsyncIterable[bytes], iterator)])
        if response.status_code < 500:
            payload = json.dumps(
                {
                    "status": response.status_code,
                    "body": body.decode(),
                    "media_type": response.media_type or response.headers.get("content-type"),
                }
            )
            await redis.set(cache_key, payload, ex=86_400, nx=True)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
