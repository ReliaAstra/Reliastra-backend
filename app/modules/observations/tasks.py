import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db.session import get_session_maker
from app.infrastructure.celery_app import celery_app
from app.modules.observations.models import Observation
from app.modules.checks.tasks import run_async

logger = logging.getLogger(__name__)

# Default retention: observations older than 90 days are purged.
DEFAULT_RETENTION_DAYS = 90


@celery_app.task(name="app.modules.observations.tasks.purge_old_observations")
def purge_old_observations(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Delete observations older than the retention window (Phase 8).

    Monthly partitions could also be DROPPED for cheap retention; this task
    provides a portable row-level fallback that works on any backend.
    """

    async def _run() -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        session_maker = get_session_maker()
        async with session_maker() as session:
            result = await session.execute(
                delete(Observation).where(Observation.timestamp < cutoff)
            )
            await session.commit()
            return result.rowcount or 0

    deleted = run_async(_run())
    logger.info("Purged %s observations older than %s days", deleted, retention_days)
    return deleted
