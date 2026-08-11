"""Reliastra FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from app.config import Settings
from app.core.exceptions import install_exception_handlers
from app.core.rate_limit import IdempotencyMiddleware, RateLimitMiddleware
from app.db.session import DatabaseManager
from app.infrastructure.redis_client import create_redis
from app.modules.api_keys import router as api_keys_router
from app.modules.auth import router as auth_router
from app.modules.billing import router as billing_router
from app.modules.checks import router as checks_router
from app.modules.dashboard import router as dashboard_router
from app.modules.dependencies import router as dependencies_router
from app.modules.evidence import router as evidence_router
from app.modules.incidents import router as incidents_router
from app.modules.notifications import router as notifications_router
from app.modules.organizations import router as organizations_router
from app.modules.users import router as users_router
from app.modules.vendors import router as vendors_router


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or Settings()
    logging.basicConfig(
        level=getattr(logging, configuration.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = configuration
        app.state.database = DatabaseManager(
            configuration.database_url, configuration.database_replica_url
        )
        app.state.redis = create_redis(configuration.redis_url)
        yield
        await app.state.redis.aclose()
        await app.state.database.dispose()

    application = FastAPI(
        title=configuration.app_name,
        version="1.0.0",
        description="External dependency intelligence and SLA evidence API",
        lifespan=lifespan,
    )
    application.add_middleware(IdempotencyMiddleware)
    application.add_middleware(RateLimitMiddleware)
    if configuration.cors_origin_list:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=configuration.cors_origin_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    install_exception_handlers(application)
    for router in (
        auth_router,
        users_router,
        organizations_router,
        dependencies_router,
        checks_router,
        incidents_router,
        evidence_router,
        notifications_router,
        dashboard_router,
        api_keys_router,
        vendors_router,
        billing_router,
    ):
        application.include_router(router)
    Instrumentator(excluded_handlers=["/metrics", "/healthz", "/readyz"]).instrument(
        application
    ).expose(application, endpoint="/metrics", include_in_schema=False)

    @application.get("/healthz", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/readyz", include_in_schema=False)
    async def ready(request: Request) -> JSONResponse:
        try:
            async with request.app.state.database.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            await request.app.state.redis.ping()
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ready"})

    return application
