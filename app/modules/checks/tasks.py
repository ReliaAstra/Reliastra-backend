"""Celery scheduler and endpoint execution tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from app.config import Settings
from app.infrastructure.celery_app import celery_app
from app.infrastructure.workers.runtime import worker_session


class CeleryDispatcher:
    def send(self, task: str, *args: object) -> None:
        celery_app.send_task(task, args=list(args))


@celery_app.task(  # type: ignore[untyped-decorator]
    name="checks.schedule_checks", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def schedule_checks() -> int:
    return asyncio.run(_schedule_checks())


async def _schedule_checks() -> int:
    from app.dependencies import build_dependency_service

    settings = Settings()
    async with worker_session(settings) as session:
        service = build_dependency_service(session, settings)
        due = await service.claim_due(datetime.now(UTC))
        for dependency in due:
            for region in dependency.regions:
                celery_app.send_task("checks.execute_check", args=[str(dependency.id), region])
        return len(due)


@celery_app.task(  # type: ignore[untyped-decorator]
    name="checks.execute_check",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def execute_check(dependency_id: str, region: str) -> str:
    return asyncio.run(_execute_check(UUID(dependency_id), region))


async def _execute_check(dependency_id: UUID, region: str) -> str:
    from app.dependencies import build_check_service

    settings = Settings()
    async with worker_session(settings) as session:
        result = await build_check_service(session, settings, CeleryDispatcher()).execute(
            dependency_id, region
        )
        return str(result.id)
