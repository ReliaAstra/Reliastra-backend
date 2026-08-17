import hashlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from app.config import settings
from app.core.exceptions import setup_exception_handlers
from app.core.request_context import request_id_var, set_request_id
from app.db.session import get_engine
from app.infrastructure.redis_client import (
    close_redis,
    safe_redis_get,
    safe_redis_ping,
    safe_redis_setex,
)
from app.modules.agencies.router import router as agencies_router
from app.modules.ai_integration.router import router as ai_providers_router
from app.modules.api_keys.router import router as api_keys_router
from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.checks.router import router as checks_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.dependencies.router import router as dependencies_router
from app.modules.evidence.router import router as evidence_router
from app.modules.evidence_gate.router import router as evidence_gate_router
from app.modules.incidents.router import router as incidents_router
from app.modules.notifications.router import router as notifications_router
from app.modules.organizations.router import router as organizations_router
from app.modules.users.router import router as users_router
from app.modules.vendors.router import router as vendors_router
from app.modules.timeline_share.router import router as timeline_share_router
from app.modules.verification.router import router as verification_router
from app.modules.referrals.router import referrals_router
from app.modules.webhooks.router import webhooks_router as webhooks_router
from app.modules.badges.router import router as badges_router
from app.modules.vendor_submissions.router import submission_router, submission_admin_router
from app.modules.growth.router import growth_router
from app.modules.feed.router import feed_router
from app.modules.status_pages.router import status_router, status_page_router
from app.modules.admin.router import admin_router, public_announcements_router
from app.modules.admin.seed import seed_first_admin

logger = logging.getLogger(__name__)

# FIX 13: /health/ready results are cached for 5 seconds so K8s probe storms
# during an outage do not multiply DB/Redis load.
_READY_CACHE_TTL_SECONDS = 5.0
_ready_cache: dict[str, Any] = {"ts": 0.0, "payload": None}


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Injects a unique X-Request-ID into every incoming request for distributed tracing."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        # FIX 36: propagate the request id into the context var so Celery
        # task dispatches made from service code can pass it along.
        token = set_request_id(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    # Headers that must not be cached/replayed (hop-by-hop)
    _HOP_BY_HOP = {
        "connection", "keep-alive", "proxy-authenticate",
        "proxy-authorization", "te", "trailers",
        "transfer-encoding", "upgrade", "content-encoding",
    }

    # FIX 40: deterministic error responses are cacheable too (409 conflict,
    # 422 validation, 404 not found). 5xx responses are never cached so
    # transient infrastructure failures are not frozen for 24 hours.
    @staticmethod
    def _is_cacheable_status(status_code: int) -> bool:
        return 200 <= status_code < 300 or status_code in {404, 409, 422}

    @staticmethod
    def _identity(request: Request) -> str:
        """FIX 7: scope the idempotency cache by the authenticated principal.

        The middleware runs before auth dependencies, so the principal is
        derived from the credentials in the request itself (API key hash or
        JWT hash) — two different users can therefore never observe each
        other's cached responses.
        """
        api_key = request.headers.get("x-api-key", "").strip()
        if api_key:
            digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
            return f"apikey:{digest}"
        auth = request.headers.get("authorization", "").strip()
        if auth:
            digest = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:16]
            return f"jwt:{digest}"
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return f"user:{user_id}"
        return "anonymous"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        idempotency_key = request.headers.get("idempotency-key")
        if not idempotency_key or request.method not in ["POST", "PATCH"]:
            return await call_next(request)

        try:
            cache_key = f"idempotency:{self._identity(request)}:{idempotency_key}"
            cached_resp = await safe_redis_get(cache_key)
            if cached_resp:
                data = json.loads(cached_resp)
                return Response(
                    content=data["content"],
                    status_code=data["status_code"],
                    media_type=data.get("media_type", "application/json"),
                    headers=data.get("headers", {}),
                )

            response = await call_next(request)
            if self._is_cacheable_status(response.status_code):
                body = [section async for section in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(body))  # type: ignore
                content = b"".join(body).decode("utf-8")

                # Filter out hop-by-hop headers before caching
                safe_headers = {
                    k: v for k, v in response.headers.items()
                    if k.lower() not in self._HOP_BY_HOP
                }

                await safe_redis_setex(
                    cache_key,
                    86400,  # 24 hours TTL
                    json.dumps(
                        {
                            "status_code": response.status_code,
                            "content": content,
                            "media_type": response.media_type,
                            "headers": safe_headers,
                        }
                    ),
                )
                return Response(
                    content=content,
                    status_code=response.status_code,
                    media_type=response.media_type,
                    headers=safe_headers,
                )
            return response
        except Exception as exc:
            logger.warning("Idempotency cache fallback (Redis error): %s", exc)
            return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Reliastra backend starting up...")
    get_engine()
    # FIX 14: the in-process APScheduler was removed from the lifespan — it
    # duplicated Celery Beat. Check scheduling now lives in the standalone
    # Redis ZSET scheduler (python -m app.infrastructure.scheduler).
    await seed_first_admin()
    yield
    logger.info("Reliastra backend shutting down...")
    try:
        from app.core.ssrf_protection import close_pinned_transports
        await close_pinned_transports()
    except Exception:  # pragma: no cover - shutdown must never raise
        logger.debug("Error closing pinned transports", exc_info=True)
    try:
        from app.modules.checks.service import close_http_client
        await close_http_client()
    except Exception:  # pragma: no cover - shutdown must never raise
        logger.debug("Error closing check HTTP client", exc_info=True)
    try:
        from app.modules.notifications.service import close_notification_http_client
        await close_notification_http_client()
    except Exception:  # pragma: no cover - shutdown must never raise
        logger.debug("Error closing notification HTTP client", exc_info=True)
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

    # NOTE: Per the CORS spec, browsers reject allow_credentials=True when
    # allow_origins is "*". Use a specific origin list or set credentials=False.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "X-API-Key",
            "X-Organization-ID",
            "Content-Type",
            "Accept",
            "Accept-Language",
            "Idempotency-Key",
            "X-Request-ID",
            "x-paystack-signature",
        ],
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(IdempotencyMiddleware)

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(organizations_router)
    app.include_router(dependencies_router)
    app.include_router(checks_router)
    app.include_router(incidents_router)
    app.include_router(evidence_router)
    app.include_router(evidence_gate_router)
    app.include_router(vendors_router)
    app.include_router(timeline_share_router)
    app.include_router(notifications_router)
    app.include_router(dashboard_router)
    app.include_router(billing_router)
    app.include_router(api_keys_router)
    app.include_router(agencies_router)
    app.include_router(ai_providers_router)
    app.include_router(verification_router)
    app.include_router(referrals_router)
    app.include_router(webhooks_router)
    app.include_router(badges_router)
    app.include_router(submission_router)
    app.include_router(submission_admin_router)
    app.include_router(growth_router)
    app.include_router(feed_router)
    app.include_router(status_router)
    app.include_router(status_page_router)
    app.include_router(admin_router)
    app.include_router(public_announcements_router)

    async def _run_health_checks() -> tuple[dict[str, Any], int]:
        checks: dict[str, Any] = {}
        overall_status = "ok"

        # Database connectivity check
        try:
            engine = get_engine()
            from sqlalchemy import text
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            msg = str(exc)
            # Truncate long connection error messages for cleanliness
            if "Connect call failed" in msg:
                msg = "connection refused"
            checks["database"] = f"unavailable: {msg}"
            overall_status = "degraded"

        # Redis connectivity check
        if await safe_redis_ping():
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable: connection refused"
            overall_status = "degraded"

        status_code = 200 if overall_status == "ok" else 503
        payload = {
            "status": overall_status,
            "service": "reliastra-backend",
            "version": "0.1.0",
            "checks": checks,
        }
        return payload, status_code

    async def _ready_response() -> Response:
        now = time.monotonic()
        if (
            _ready_cache["payload"] is None
            or now - _ready_cache["ts"] > _READY_CACHE_TTL_SECONDS
        ):
            payload, status_code = await _run_health_checks()
            _ready_cache["payload"] = (payload, status_code)
            _ready_cache["ts"] = now
        payload, status_code = _ready_cache["payload"]
        return Response(
            content=json.dumps(payload),
            status_code=status_code,
            media_type="application/json",
        )

    @app.get("/health", tags=["Health"])
    async def health_check() -> Response:
        """Full health check (DB + Redis), cached for 5s (FIX 13)."""
        return await _ready_response()

    @app.get("/health/live", tags=["Health"])
    async def liveness_check() -> dict[str, Any]:
        """FIX 13: cheap liveness probe — no DB/Redis access."""
        return {
            "status": "ok",
            "service": "reliastra-backend",
            "version": "0.1.0",
        }

    @app.get("/health/ready", tags=["Health"])
    async def readiness_check() -> Response:
        """FIX 13: readiness probe — DB + Redis, cached for 5s."""
        return await _ready_response()

    @app.get("/metrics", tags=["Observability"])
    async def metrics() -> PlainTextResponse:
        """FIX 12: Prometheus exposition endpoint."""
        from app.core.metrics import metrics_content_type, render_metrics

        return PlainTextResponse(
            content=render_metrics(), media_type=metrics_content_type()
        )

    return app


app = create_app()
