import logging
import uuid
from typing import Any

from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.checks.tasks.execute_check")
def execute_check(
    dependency_id: str, region: str, request_id: str | None = None
) -> dict[str, Any] | None:
    async def _run(session) -> dict[str, Any] | None:
        try:
            from app.modules.checks.service import check_service

            result = await check_service.execute_check(
                session, uuid.UUID(dependency_id), region
            )
            if not result:
                return None
            return {
                "id": str(result.id),
                "dependency_id": str(result.dependency_id),
                "org_id": str(result.org_id),
                "region": result.region,
                "is_up": result.is_up,
                "latency_ms": result.latency_ms,
                "quorum_confirmed": result.quorum_confirmed,
            }
        except Exception as exc:
            logger.exception(
                "Error in execute_check task for dep %s (request_id=%s): %s",
                dependency_id,
                request_id,
                exc,
            )
            return None

    return async_task_body(_run)


@celery_app.task(name="app.modules.checks.tasks.schedule_checks")
def schedule_checks(request_id: str | None = None) -> int:
    """Celery Beat task: scan and dispatch due dependency checks.

    Runs every 30s (configured in ``celery_app.conf.beat_schedule``).
    Delegates to ``CheckService.schedule_due_checks`` which reads at most
    500 due dependencies and fires one ``execute_check`` Celery task per
    dep/region pair — no Redis ZSET queue, no custom scheduler loop.
    """
    async def _run(session) -> int:
        from app.modules.checks.service import check_service
        return await check_service.schedule_due_checks(session)

    return async_task_body(_run)


@celery_app.task(name="app.modules.checks.tasks.ensure_check_result_partitions")
def ensure_check_result_partitions(months_ahead: int = 12) -> int:
    """Create monthly partitions for the next *months_ahead* months.

    Scheduled monthly by Celery beat; also runs once in migration
    ``0015_production_hardening``.

    Now also creates observation partitions to fix the gap where
    ``observations`` had no partition management (P0-3 finding).
    """

    async def _run(session) -> int:
        from app.modules.checks.partition_manager import (
            ensure_partitions,
            ensure_observation_partitions,
        )

        created = 0
        names = await ensure_partitions(session, months_ahead)
        created += len(names)
        obs_names = await ensure_observation_partitions(session, months_ahead)
        created += len(obs_names)
        return created

    return async_task_body(_run)
