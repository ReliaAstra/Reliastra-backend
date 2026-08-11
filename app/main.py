import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from app.config import settings
from app.core.exceptions import setup_exception_handlers
from app.db.session import get_engine
from app.infrastructure.redis_client import close_redis, get_redis
from app.modules.api_keys.router import router as api_keys_router
from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.checks.router import router as checks_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dependencies.router import router as dependencies_router
from app.modules.evidence.router import router as evidence_router
from app.modules.incidents.router import router as incidents_router
from app.modules.notifications.router import router as notifications_router
from app.modules.organizations.router import router as organizations_router
from app.modules.users.router import router as users_router
from app.modules.vendors.router import router as vendors_router

logger = logging.getLogger(__name__)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        idempotency_key = request.headers.get("idempotency-key")
        if not idempotency_key or request.method not in ["POST", "PATCH"]:
            return await call_next(request)

        try:
            redis = get_redis()
            cache_key = f"idempotency:{idempotency_key}"
            cached_resp = await redis.get(cache_key)
            if cached_resp:
                data = json.loads(cached_resp)
                return Response(
                    content=data["content"],
                    status_code=data["status_code"],
                    media_type=data.get("media_type", "application/json"),
                    headers=data.get("headers", {}),
                )

            response = await call_next(request)
            if 200 <= response.status_code < 300:
                body = [section async for section in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(body))  # type: ignore
                content = b"".join(body).decode("utf-8")

                await redis.setex(
                    cache_key,
                    86400,  # 24 hours TTL
                    json.dumps(
                        {
                            "status_code": response.status_code,
                            "content": content,
                            "media_type": response.media_type,
                        }
                    ),
                )
                return Response(
                    content=content,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    headers=dict(response.headers),
                )
            return response
        except Exception as exc:
            logger.warning("Idempotency cache fallback (Redis error): %s", exc)
            return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Reliastra backend starting up...")
    get_engine()
    yield
    logger.info("Reliastra backend shutting down...")
    await close_redis()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reliastra MVP API",
        version="0.1.0",
        description="External dependency intelligence platform API",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    setup_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(IdempotencyMiddleware)

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(organizations_router)
    app.include_router(dependencies_router)
    app.include_router(checks_router)
    app.include_router(incidents_router)
    app.include_router(evidence_router)
    app.include_router(vendors_router)
    app.include_router(notifications_router)
    app.include_router(dashboard_router)
    app.include_router(billing_router)
    app.include_router(api_keys_router)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, Any]:
        return {"status": "ok", "service": "reliastra-backend"}

    return app


app = create_app()
