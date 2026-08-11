"""Celery incident lifecycle tasks."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.config import Settings
from app.infrastructure.celery_app import celery_app
from app.infrastructure.workers.runtime import worker_session


class CeleryDispatcher:
    def send(self, task: str, *args: object) -> None:
        celery_app.send_task(task, args=list(args))


@celery_app.task(  # type: ignore[untyped-decorator]
    name="incidents.create_incident", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def create_incident(dependency_id: str) -> str:
    return asyncio.run(_create(UUID(dependency_id)))


async def _create(dependency_id: UUID) -> str:
    from app.dependencies import build_incident_service

    settings = Settings()
    async with worker_session(settings) as session:
        result = await build_incident_service(
            session, settings, CeleryDispatcher()
        ).create_for_dependency(dependency_id)
        return str(result.id)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="incidents.resolve_incident", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def resolve_incident(dependency_id: str) -> str | None:
    return asyncio.run(_resolve(UUID(dependency_id)))


async def _resolve(dependency_id: UUID) -> str | None:
    from app.dependencies import build_incident_service

    settings = Settings()
    async with worker_session(settings) as session:
        result = await build_incident_service(
            session, settings, CeleryDispatcher()
        ).resolve_for_dependency(dependency_id)
        return str(result.id) if result else None
