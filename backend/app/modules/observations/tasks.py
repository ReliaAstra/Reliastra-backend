import logging
from datetime import datetime, timedelta, timezone

from app.infrastructure.async_tasks import async_task_body
from app.infrastructure.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.observations.tasks.process_outbox")
def process_outbox(batch_size: int = 100, request_id: str | None = None) -> int:
    """Drain pending observation outbox events (runs every 10s via beat)."""

    async def _run(session) -> int:
        try:
            from app.modules.observations.outbox import process_outbox_batch

            return await process_outbox_batch(session, batch_size)
        except Exception:
            logger.exception(
                "Observation outbox processing failed (request_id=%s)",
                request_id,
            )
            raise

    return async_task_body(_run)


@celery_app.task(name="app.modules.observations.tasks.retention_cleanup")
def retention_cleanup(retention_days: int = 365) -> int:
    async def _run(session) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        from app.modules.observations.repository import ObservationRepository

        try:
            deleted = await ObservationRepository.delete_before(session, cutoff)
            logger.info("Removed %s expired observations", deleted)
            return deleted
        except Exception:
            logger.exception("Observation retention cleanup failed")
            raise

    return async_task_body(_run)


@celery_app.task(name="app.modules.observations.tasks.daily_aggregation")
def daily_aggregation() -> int:
    """Record the prior day's volume for operational capacity reporting.

    Read endpoints aggregate directly from the immutable observations. Keeping
    this task side-effect free avoids introducing a second source of truth.
    """

    async def _run(session) -> int:
        now = datetime.now(timezone.utc)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        from app.modules.observations.repository import ObservationRepository

        count = await ObservationRepository.count_between(session, start, end)
        logger.info("Observation volume for %s: %s", start.date(), count)
        return count

    return async_task_body(_run)
