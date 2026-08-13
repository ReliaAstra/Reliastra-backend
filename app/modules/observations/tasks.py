import logging
from datetime import datetime, timedelta, timezone

from app.db.session import get_session_maker
from app.infrastructure.celery_app import celery_app
from app.modules.checks.tasks import run_async

logger = logging.getLogger(__name__)


@celery_app.task(name="app.modules.observations.tasks.retention_cleanup")
def retention_cleanup(retention_days: int = 365) -> int:
    async def _run() -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        from app.modules.observations.repository import ObservationRepository

        async with get_session_maker()() as session:
            try:
                deleted = await ObservationRepository.delete_before(session, cutoff)
                await session.commit()
                logger.info("Removed %s expired observations", deleted)
                return deleted
            except Exception:
                await session.rollback()
                logger.exception("Observation retention cleanup failed")
                raise

    return run_async(_run())


@celery_app.task(name="app.modules.observations.tasks.daily_aggregation")
def daily_aggregation() -> int:
    """Record the prior day's volume for operational capacity reporting.

    Read endpoints aggregate directly from the immutable observations. Keeping
    this task side-effect free avoids introducing a second source of truth.
    """

    async def _run() -> int:
        now = datetime.now(timezone.utc)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = end - timedelta(days=1)
        from app.modules.observations.repository import ObservationRepository

        async with get_session_maker()() as session:
            count = await ObservationRepository.count_between(session, start, end)
            logger.info("Observation volume for %s: %s", start.date(), count)
            return count

    return run_async(_run())
