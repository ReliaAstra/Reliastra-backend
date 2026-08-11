import asyncio
import logging
import uuid
from typing import Any
from app.infrastructure.celery_app import celery_app
from app.db.session import get_session_maker

logger = logging.getLogger(__name__)


def run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@celery_app.task(name="app.modules.checks.tasks.schedule_checks")
def schedule_checks() -> int:
    async def _run() -> int:
        session_maker = get_session_maker()
        async with session_maker() as session:
            try:
                from app.modules.checks.service import check_service
                count = await check_service.schedule_due_checks(session)
                await session.commit()
                return count
            except Exception as exc:
                await session.rollback()
                logger.exception("Error in schedule_checks task: %s", exc)
                return 0

    return run_async(_run())


@celery_app.task(name="app.modules.checks.tasks.execute_check")
def execute_check(dependency_id: str, region: str) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any] | None:
        session_maker = get_session_maker()
        async with session_maker() as session:
            try:
                from app.modules.checks.service import check_service
                result = await check_service.execute_check(
                    session, uuid.UUID(dependency_id), region
                )
                await session.commit()
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
                await session.rollback()
                logger.exception(
                    "Error in execute_check task for dep %s: %s",
                    dependency_id,
                    exc,
                )
                return None

    return run_async(_run())
