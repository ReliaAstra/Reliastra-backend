"""Asynchronous notification fan-out tasks."""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.infrastructure.celery_app import celery_app
from app.infrastructure.workers.runtime import worker_session
from app.modules.notifications.schemas import AlertPayload


@celery_app.task(  # type: ignore[untyped-decorator]
    name="notifications.dispatch", autoretry_for=(Exception,), retry_backoff=True, max_retries=5
)
def dispatch(payload: dict[str, object]) -> int:
    return asyncio.run(_dispatch(AlertPayload.model_validate(payload)))


async def _dispatch(payload: AlertPayload) -> int:
    from app.dependencies import build_notification_service

    settings = Settings()
    async with worker_session(settings) as session:
        results = await build_notification_service(session, settings).dispatch(payload)
        return sum(result.delivered for result in results)
